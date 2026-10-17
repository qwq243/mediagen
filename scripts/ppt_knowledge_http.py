"""Local-only knowledge and design-spec adapters, registered behind the existing CSRF gate."""
import copy
import io
import json
import sqlite3
from pathlib import Path
from flask import jsonify, request, send_file
import ppt_knowledge as k
import ppt_design_spec as ds
import ppt_workflow as wf


def default_spec(p):
    """Explicit proposal only: never silently migrate/approve an already delivered project."""
    tokens = {}
    palette = p["design"].get("palette", {})
    if isinstance(palette, dict):
        for name, color in palette.items():
            if isinstance(color, str) and color.startswith("#") and len(color) == 7:
                tokens[name] = {"type": "color", "value": color}
    return {"version": 1, "canvas": [1280, 720],
            "global": {"tokens": tokens}, "templates": {},
            "hard_constraints": {"no_fake_evidence": True, "exact_text": True, "protect_identity_and_brands": True},
            "tolerances": copy.deepcopy(ds.TOLERANCES),
            "pages": {pg["page_id"]: {"elements": [
                {"id": "title", "kind": "title", "bbox": [.05, .05, .9, .12],
                 "text": pg.get("page_text", "").split("\n")[0], "geometry_status": "proposed"},
                {"id": "body", "kind": "text", "bbox": [.05, .22, .9, .68],
                 "text": "\n".join(pg.get("page_text", "").split("\n")[1:]), "geometry_status": "proposed"}
            ]} for pg in p["pages"]}}


def register(app, root, token, library):
    root, library = Path(root), Path(library)

    def current_rows():
        rows = k.load(library)
        dbfile = library / "index.sqlite3"
        if not dbfile.exists():
            return []
        ids = sorted({a["asset_id"] for a in rows})
        if not ids:
            return []
        with sqlite3.connect(dbfile.as_uri() + "?mode=ro", uri=True) as db:
            originals = {}
            # Only validate candidate source identities; never parse the entire
            # legacy library (including repeated deck sequences) for a 64-page pilot.
            for start in range(0, len(ids), 500):
                batch = ids[start:start + 500]
                query = ("SELECT id,version,json_extract(payload,'$.version'),json_extract(payload,'$.sha256') "
                         "FROM assets_v3 WHERE current=1 AND id IN (" +
                         ",".join("?" for _ in batch) + ")")
                originals.update({id: {"version": version, "sha256": sha}
                                  for id, version, payload_version, sha in db.execute(query, batch)
                                  if version == payload_version})
            try:
                removed = {r[0] for r in db.execute("SELECT id FROM asset_removals_v3")}
            except sqlite3.OperationalError:
                removed = set()
        # Old annotation remains in history but cannot silently attach to a new source version.
        return [a for a in rows if a["asset_id"] in originals and a["asset_id"] not in removed and
                originals[a["asset_id"]]["version"] == a["source"]["version"] and
                originals[a["asset_id"]]["sha256"] == a["source"]["sha256"]]

    def current_annotation(id):
        a = next((a for a in current_rows() if a["asset_id"] == id), None)
        if not a:
            raise ValueError("没有与当前原图版本匹配的原子化标注")
        return a

    @app.get("/api/v3/knowledge")
    def knowledge_search():
        allowed = {"q", "offset", "limit", "deck", "role", "layout", "relation", "font", "status", "usage", "alpha", "kind"}
        if set(request.args) - allowed:
            raise ValueError("unknown search argument")
        filters = {key: request.args[key] for key in allowed - {"q", "offset", "limit"} if request.args.get(key)}
        if "alpha" in filters:
            if filters["alpha"] not in ("true", "false"):
                raise ValueError("alpha must be true/false")
            filters["alpha"] = filters["alpha"] == "true"
        rows = current_rows()
        result = k.rank(rows, request.args.get("q", ""), filters,
                        request.args.get("offset", 0), request.args.get("limit", 36))
        result["coverage_summary"] = {
            "decks": len({a["deck_id"] for a in rows}), "pages": len(rows),
            "detailed_candidates": sum(a["coverage"]["complete"] for a in rows),
            "inventory_only": sum(not a["coverage"]["complete"] for a in rows),
            "independently_reviewed": sum(a["review"]["status"] == "reviewed" for a in rows),
            "scope": "pilot_atomic_annotations_not_entire_legacy_library",
        }
        # List payloads stay small; full atom trees are loaded on demand.
        for a in result["items"]:
            a["element_count"] = len(a.pop("elements"))
            a.pop("relations")
            a.pop("definitions")
        result["csrf"] = token
        return jsonify(result)

    @app.get("/api/v3/knowledge/schema")
    def knowledge_schema():
        return jsonify(k.schema())

    @app.get("/api/v3/knowledge/taxonomy")
    def knowledge_taxonomy():
        return jsonify(k.taxonomy())

    @app.get("/api/v3/knowledge/<id>")
    def knowledge_detail(id):
        a = copy.deepcopy(current_annotation(id))
        a["preview_url"] = f"/api/assets/{id}/download?version={a['source']['version']}"
        return jsonify(a)

    @app.get("/api/v3/knowledge/<id>/history")
    def annotation_history(id):
        a = current_annotation(id)
        return jsonify(current=a["annotation_hash"], versions=k.history(library, id, a["source"]["version"]))

    @app.post("/api/v3/knowledge/<id>/select-version")
    def select_annotation(id):
        a = current_annotation(id)
        body = request.get_json(silent=True) or {}
        wf.reject_secrets(body)
        result = k.select_version(library, id, a["source"]["version"], body.get("expected_hash"),
                                  body.get("annotation_hash"), body.get("reason"))
        return jsonify(result)

    @app.post("/api/v3/knowledge/<id>/borrow")
    def borrow(id):
        a = current_annotation(id)
        body = request.get_json(silent=True) or {}
        p = wf.load(root)
        if body.get("revision") != p["revision"]:
            raise ValueError("页面版本已变化，刷新后重试")
        if body.get("annotation_hash") != a["annotation_hash"]:
            raise ValueError("标注版本已变化")
        purpose = body.get("purpose")
        if purpose not in ("structure", "typography_appearance", "palette", "component"):
            raise ValueError("unknown borrowing purpose")
        id = body.get("element_id")
        el = next((e for e in a["elements"] if e["id"] == id), None)
        if not el or el["kind"] == "contamination":
            raise ValueError("请选择设计元素，不可借用截图污染")
        entry = {"asset_id": a["asset_id"], "source_version": a["source"]["version"],
                 "source_sha256": a["source"]["sha256"], "annotation_hash": a["annotation_hash"],
                 "element_id": id, "bbox": el["bbox"], "purpose": purpose,
                 "status": "pending_user_and_agent_review", "send_to_model": False}
        # A selection is a request, not an approved design or permission to upload.
        requests = p.setdefault("knowledge_requests", [])
        if entry not in requests:
            requests.append(entry)
            wf.save(root, p)
        return jsonify(entry=entry, revision=p["revision"], inference_performed=False)

    @app.get("/api/v3/design-spec")
    def design_spec():
        p = wf.load(root)
        spec = p["design"].get("atomic_spec")
        return jsonify(spec=spec or default_spec(p), active=bool(spec), revision=p["revision"], csrf=token,
                       validation_notice=p.get("validation_notice"),
                       pages=[{"id": pg["page_id"], "title": pg.get("title", pg["page_id"]),
                               "has_output": bool(pg.get("selected_output"))} for pg in p["pages"]],
                       knowledge_requests=p.get("knowledge_requests", []),
                       warning=None if spec else "这是待确认草案：仅迁入色卡和原文，位置为提案；尚未迁入的字体、组件、背景需确认后填写。启用后，量化参数以此规格为唯一真值，不再同时发送旧字号/色卡/网格。当前项目尚未改变。")

    def borrowing_proposal(body):
        wf.reject_secrets(body)
        p = wf.load(root)
        if body.get("revision") != p["revision"]:
            raise ValueError("页面版本已变化")
        if not p["design"].get("atomic_spec"):
            raise ValueError("请先补齐并确认项目设计规格；借鉴操作不会替你激活整套默认草案")
        index = body.get("request_index")
        entries = p.get("knowledge_requests", [])
        if type(index) is not int or not 0 <= index < len(entries):
            raise ValueError("unknown borrowing request")
        entry = entries[index]
        if entry["status"] != "pending_user_and_agent_review":
            raise ValueError("该请求已处理；请重新选择参考或刷新")
        a = current_annotation(entry["asset_id"])
        if entry["annotation_hash"] != a["annotation_hash"]:
            raise ValueError("候选标注版本已变化，重新查看后选择")
        proposal = ds.borrow_proposal(p["design"]["atomic_spec"], body.get("page_id"),
                                      body.get("target_element_id"), a, entry["element_id"], entry["purpose"])
        ds.validate_project_spec(proposal["spec"], p["pages"])
        return p, entry, proposal

    @app.post("/api/v3/knowledge/borrow-preview")
    def preview_borrowing():
        _, _, proposal = borrowing_proposal(request.get_json(silent=True) or {})
        return jsonify(**proposal, saved=False, inference_performed=False)

    @app.post("/api/v3/knowledge/borrow-apply")
    def apply_borrowing():
        body = request.get_json(silent=True) or {}
        p, entry, proposal = borrowing_proposal(body)
        reason = body.get("confirmation_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("需明确确认提案内容及依据")
        if body.get("proposal_hash") != proposal["proposal_hash"]:
            raise ValueError("借鉴提案已变化，请重新预览")
        if entry["purpose"] == "component":
            component_id = proposal["changes"]["component"]["proposed"]
            proposal["spec"]["pages"][body["page_id"]]["components"][component_id]["status"] = "user_confirmed_parameters"
        p["design"]["atomic_spec"] = proposal["spec"]
        entry.update(status="applied_parameters_only", applied_page=body["page_id"],
                     applied_element=body["target_element_id"], confirmation_reason=reason,
                     accepted_proposal_hash=proposal["proposal_hash"], applied_at=wf.now())
        wf.save(root, p)
        return jsonify(revision=p["revision"], affected_pages=[body["page_id"]],
                       approved_for_generation=False, image_uploaded=False, inference_performed=False)

    @app.post("/api/v3/design-spec")
    def save_spec():
        body = request.get_json(silent=True) or {}
        p = wf.load(root)
        if body.get("revision") != p["revision"]:
            raise ValueError("页面版本已变化，未覆盖其他修改")
        spec = body.get("spec")
        if not isinstance(spec, dict):
            raise ValueError("spec must be an object")
        wf.reject_secrets(spec)
        ds.validate_project_spec(spec, p["pages"])
        expected = {pg["page_id"] for pg in p["pages"]}
        if set(spec.get("pages", {})) != expected:
            raise ValueError("设计规格必须覆盖本项目全部页面")
        resolved = {id: ds.compile_spec(spec, id) for id in expected}
        old = p["design"].get("atomic_spec")
        changed = [id for id in sorted(expected) if old is None or ds.compile_spec(old, id) != resolved[id]]
        if old and old.get("tolerances", ds.TOLERANCES) != spec.get("tolerances", ds.TOLERANCES):
            # A fresh explicit project confirmation is required; never loosen after a failure through UI.
            raise ValueError("验收阈值已冻结；请另行确认阈值变更，不可在此静默放宽")
        p["design"]["atomic_spec"] = spec
        # Old receipts remain for traceability; existing hashes make them stale, not silently passed.
        wf.save(root, p)
        return jsonify(revision=p["revision"], affected_pages=changed, approvals="需重新按流程确认", inference_performed=False)

    @app.post("/api/v3/design-spec/preview")
    def preview_spec():
        p = wf.load(root)
        body = request.get_json(silent=True) or {}
        if body.get("revision") != p["revision"]:
            raise ValueError("页面版本已变化")
        wf.reject_secrets(body)
        ds.validate_project_spec(body.get("spec", {}), p["pages"])
        return jsonify(resolved={pg["page_id"]: ds.compile_spec(body["spec"], pg["page_id"]) for pg in p["pages"]},
                       saved=False, inference_performed=False)

    @app.get("/api/v3/design-spec/<page_id>/export")
    def export_package(page_id):
        p = wf.load(root)
        if page_id not in {pg["page_id"] for pg in p["pages"]}:
            raise ValueError("unknown page")
        lane = request.args.get("lane", "samples")
        if lane not in ("samples", "deck"):
            raise ValueError("invalid generation lane")
        raw = ds.package_zip(root, p, page_id, lane == "samples")
        return send_file(io.BytesIO(raw), mimetype="application/zip", as_attachment=True,
                         download_name=page_id + "-" + lane + "-reproducibility.zip")

    @app.get("/api/v3/design-spec/<page_id>/compiled")
    def compiled(page_id):
        p = wf.load(root)
        if page_id not in {pg["page_id"] for pg in p["pages"]}:
            raise ValueError("unknown page")
        lane = request.args.get("lane", "samples")
        if lane not in ("samples", "deck"):
            raise ValueError("invalid generation lane")
        package = ds.request_package(root, p, page_id, lane == "samples")
        for item in package["inputs"]:
            item["preview_url"] = f"/api/v3/design-spec/{page_id}/reference/{item['order']}?lane={lane}&hash={item['sha256']}"
        pg = next(x for x in p["pages"] if x["page_id"] == page_id)
        package["output_url"] = f"/api/v3/pages/{page_id}/images/selected" if pg.get("selected_output") else None
        package["output_sha256"] = wf.file_sha(wf.local(root, pg["selected_output"]["path"])) if pg.get("selected_output") else None
        report = copy.deepcopy(p.get("design_deviation_reports", {}).get(page_id))
        if report and (package["spec"] is None or report.get("target_hash") != package["spec"]["spec_hash"] or
                       not pg.get("selected_output") or report.get("output_sha256") != wf.file_sha(wf.local(root, pg["selected_output"]["path"]))):
            report["status"] = "stale"
        package["audit"] = report
        return jsonify(package)

    @app.get("/api/v3/design-spec/<page_id>/reference/<int:order>")
    def reference_image(page_id, order):
        p = wf.load(root)
        if page_id not in {pg["page_id"] for pg in p["pages"]}:
            raise ValueError("unknown page")
        if request.args.get("lane", "samples") not in ("samples", "deck"):
            raise ValueError("invalid generation lane")
        pg = next(x for x in p["pages"] if x["page_id"] == page_id)
        refs = ds.reference_inputs(root, p, pg, request.args.get("lane", "samples") == "samples")
        if not 1 <= order <= len(refs):
            raise ValueError("reference order out of range")
        item = refs[order - 1]
        if request.args.get("hash") != item["sha256"]:
            raise ValueError("reference image version changed")
        return send_file(item["path"])

    @app.post("/api/v3/design-spec/<page_id>/audit")
    def design_audit(page_id):
        body = request.get_json(silent=True) or {}
        wf.reject_secrets(body)
        p = wf.load(root)
        if page_id not in {pg["page_id"] for pg in p["pages"]}:
            raise ValueError("unknown page")
        if body.get("revision") != p["revision"]:
            raise ValueError("页面版本已变化")
        target = ds.compile_spec(p["design"].get("atomic_spec", {}), page_id)
        pg = next(x for x in p["pages"] if x["page_id"] == page_id)
        selected = pg.get("selected_output")
        if not selected:
            raise ValueError("尚无采用成品")
        sha = wf.file_sha(wf.local(root, selected["path"]))
        if body.get("output_sha256") != sha or body.get("target_hash") != target["spec_hash"]:
            raise ValueError("审核必须绑定当前目标及当前成品哈希")
        measured = body.get("measured", {})
        if not measured.get("reviewer") or not measured.get("evidence"):
            raise ValueError("需测量者及原图复核依据")
        report = ds.audit(target, measured)
        report["output_sha256"] = sha
        p.setdefault("design_deviation_reports", {})[page_id] = report
        wf.save(root, p)
        return jsonify(report=report, revision=p["revision"])
