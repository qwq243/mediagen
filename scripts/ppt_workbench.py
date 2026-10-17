"""V3 workbench HTTP adapter. No browser endpoint invokes an image model."""
import json
import uuid
from pathlib import Path
from urllib.parse import quote
from flask import jsonify, request, send_file
import ppt_assets as assets
import ppt_cart as cart
import ppt_studio as studio
import ppt_workflow as wf
import ppt_progress as progress
import ppt_coding as coding
import ppt_annotation_io as annotation_io
import ppt_fragments as fragments
import ppt_content_sources as content_sources
from ppt_read_cache import hash_snapshot


def representative_recommendations(rows, removed, library):
    """One version-bound entrance per work; preserve curator priority, max six."""
    result, seen = [], set()
    for row in rows:
        if not row.get("id") or row["id"] in removed:
            continue
        try:
            record = assets.get(row["id"], row.get("version") or row.get("asset_version"), library)
        except ValueError:
            continue  # never replace a missing pinned version with a different image
        group = record.get("deck_code") or record.get("work") or record["id"]
        if group in seen:
            continue
        seen.add(group)
        result.append({**row, "deck_code": record.get("deck_code"),
                       "version": record["version"]})
        if len(result) == 6:
            break
    return result


def material_previews(p, recommendations, library):
    """Only project-related, version-pinned library images; viewing is not adoption."""
    rows, seen = [], {}

    def append(ident, version, origin, expand=False):
        if not ident or not version:
            return
        if (ident, version) in seen:
            return seen[(ident, version)]
        try:
            record = assets.get(ident, version, library)
        except ValueError:
            return
        row = {"id": ident, "version": record["version"], "title": record["title"],
               "kind": record["kind"], "origin": origin,
               "url": f"/api/assets/{quote(ident)}/download?version={quote(record['version'])}"}
        seen[(ident, version)] = row
        rows.append(row)
        if expand:
            context = coding.bundle_context(record, library) or {}
            for member in context.get("members", []):
                if member.get("available") and not member.get("archived"):
                    append(member["id"], member["version"], "related")
        return row

    for row in p.get("asset_selection", []):
        append(row.get("id"), row.get("version") or row.get("asset_version"), "selected", True)
    component = p.get("design", {}).get("component_proposal", {})
    append(component.get("preview_id"), component.get("preview_version"), "proposal")
    for ref in p.get("references", []):
        row = append(ref.get("asset_id"), ref.get("asset_version"), "reference")
        if row is not None:
            bound = row.setdefault("page_ids", [])
            for pg in p.get("pages", []):
                if ref["id"] in pg.get("reference_ids", []) and pg["page_id"] not in bound:
                    bound.append(pg["page_id"])
    for row in recommendations:
        append(row.get("id"), row.get("version") or row.get("asset_version"), "recommended", True)
    return rows


def register(app, root, token, library):
    library = Path(library)
    import ppt_knowledge_http
    ppt_knowledge_http.register(app, root, token, library)

    def mutation():
        body = request.get_json(silent=True) if request.is_json else request.form.to_dict()
        if not isinstance(body, dict):
            raise ValueError("JSON object required")
        p = wf.load(root)
        if str(body.get("revision")) != str(p["revision"]):
            raise ValueError("页面版本已更新，请刷新后重试；未覆盖其他修改")
        return p, body

    def image_summary(p, pg, value, candidate=False):
        if not value:
            return None
        result = {k: value.get(k) for k in ("id", "kind", "status", "at", "provenance", "technical")}
        result["sha256"] = wf.file_sha(wf.local(root, value["path"]))
        result["url"] = (f"/api/v3/pages/{pg['page_id']}/images/" +
                         (value["id"] if candidate else "selected"))
        expected = (studio.candidate_subject(root, p, pg["page_id"], value) if candidate
                    else wf.subject(root, p, "visual", pg["page_id"]))
        audit = value.get("audit") if candidate else p["audits"].get("visual:" + pg["page_id"])
        result["audit_status"] = "passed" if wf.valid(audit, expected) else ("stale" if audit else "pending")
        result["audit"] = audit
        result["subject_hash"] = expected
        return result

    @app.get("/api/v3/workbench")
    @hash_snapshot()
    def state():
        p = wf.load(root)
        inspection = wf.check(root, p)
        channels = cart.site_catalog(library)
        with assets.database(library) as db:
            db.execute("CREATE TABLE IF NOT EXISTS site_favorites_v1(id TEXT PRIMARY KEY)")
            favorites = {x[0] for x in db.execute("SELECT id FROM site_favorites_v1")}
            removed = {x[0] for x in db.execute("SELECT id FROM asset_removals_v3")}
        for site in channels["items"]:
            site["favorite"] = site["id"] in favorites
            site["icon_url"] = (f"/api/v3/site-icons/{site['id']}" if
                (library / "site-icons" / (site["id"] + ".png")).is_file() else None)
        approvals = {stage: wf.valid(p["approvals"].get(stage), inspection["subject_hashes"].get(stage))
                     for stage in ("stage1", "stage2", "samples")}
        pages = []
        for pg in p["pages"]:
            row = {k: v for k, v in pg.items() if k in studio.PAGE_FIELDS}
            row["selected"] = image_summary(p, pg, pg.get("selected_output"))
            row["candidates"] = [image_summary(p, pg, x, True) for x in pg["output_candidates"]]
            row["script_sources"] = content_sources.page_script_sources(root, p, pg["page_id"])
            pages.append(row)
        recommendations = representative_recommendations(
            p.get("asset_recommendations", []), removed, library)
        return jsonify(project=p.get("project_name", "图片演示工作台"), revision=p["revision"],
                       job_id=wf.sha(str(Path(root).resolve()))[:24], proposal_hash=wf.sha(studio.proposal(p)),
                       csrf=token, proposal=studio.proposal(p), pages=pages, approvals=approvals,
                       candidates=p.get("design_candidates", []),
                       recommendations=recommendations,
                       reference_assets=material_previews(p, recommendations, library),
                       cart=p["resource_cart"], production_assets=p["asset_selection"],
                       pending=[x for x in p["revision_requests"] if x["status"] in ("draft", "submitted")],
                       history=studio.history(root), sites=channels["items"],
                       site_categories=channels["categories"], site_collections=channels["collections"],
                       check=inspection,
                       progress=progress.state(root, p),
                       annotations=p["annotations"], feedback=p.get("feedback", []),
                       exports=p.get("deliveries") or p.get("deliverables", []), bundles=p["asset_exports"],
                       sources=assets.source_roots(library),
                       content_sources=content_sources.summaries(root, p),
                       reference_decks=content_sources.reference_summaries(root, p),
                       inference_performed=False)

    @app.get("/api/v3/content-sources/<source_id>/preview")
    def content_preview(source_id):
        return jsonify(content_sources.preview(root, wf.load(root), source_id))

    @app.get("/api/v3/content-sources/<source_id>/original")
    def content_original(source_id):
        path, name = content_sources.original(root, wf.load(root), source_id)
        return send_file(path, as_attachment=True, download_name=name)

    @app.get("/api/v3/reference-decks/<source_id>/preview")
    def reference_deck_preview(source_id):
        return jsonify(content_sources.reference_preview(root, wf.load(root), source_id))

    @app.get("/api/v3/reference-decks/<source_id>/pages/<int:number>/image")
    def reference_deck_image(source_id, number):
        path = content_sources.reference_image(root, wf.load(root), source_id, number)
        return send_file(path)

    @app.get("/api/v3/pages/<pid>/evidence/<int:index>")
    def page_evidence(pid, index):
        return jsonify(content_sources.evidence_preview(root, wf.load(root), pid, index))

    @app.get("/api/v3/assets")
    def search():
        filters = {k: request.args[k] for k in assets.FILTER_FIELDS if request.args.get(k)}
        if request.args.get("favorite") == "1":
            filters["favorite"] = True
        filters["archived"] = request.args.get("archived") == "1"
        return jsonify(assets.search(request.args.get("q", ""), filters,
                                    request.args.get("offset", 0), request.args.get("limit", 30),
                                    distinct=request.args.get("distinct") == "1", library=library))

    @app.get("/api/v3/assets/<rid>")
    def asset_detail(rid):
        record = assets.get(rid, request.args.get("version"), library)
        record["preview_url"] = f"/api/assets/{rid}/preview?version={record['version']}"
        record["archived"] = rid in assets.archived_ids(library)
        record["bundle_context"] = coding.bundle_context(record, library)
        return jsonify(record)

    @app.post("/api/v3/assets/visibility")
    def asset_visibility():
        _, body = mutation()
        return jsonify(assets.set_archived(body.get("id", ""), body.get("archived"),
                                          body.get("version"), library))

    @app.post("/api/v3/assets/crop")
    def crop_asset():
        p, body = mutation()
        # Saving a derived reference neither confirms a stage nor starts generation.
        return jsonify(fragments.crop(root, p, body, library))

    def recipe_record():
        p = wf.load(root)
        if request.args.get("asset_id"):
            value = assets.get(request.args["asset_id"], request.args.get("version"), library)
            pointer = value.get("original_metadata", {}).get("generation_recipe")
            allowed = library / "generation-records"
        else:
            value = studio._image_target(p, request.args.get("page_id"), request.args.get("candidate_id") or None)
            pointer = value.get("metadata", {}).get("generation_recipe")
            allowed = Path(root) / "generation-records"
        if not pointer:
            return None
        path = Path(pointer["path"]).resolve()
        if not path.is_relative_to(allowed.resolve()) or wf.file_sha(path) != pointer["sha256"]:
            raise ValueError("生成记录已变化或不在登记目录")
        return wf.read(path)

    @app.get("/api/v3/recipe")
    def recipe():
        record = recipe_record()
        return jsonify(record or {"status": "unavailable", "message": "这张图没有完整生成记录；不会猜测模型或历史参数。"})

    @app.get("/api/v3/recipe/input/<int:index>")
    def recipe_input(index):
        record = recipe_record()
        if not record or not 0 <= index < len(record.get("inputs", [])):
            return jsonify(error="unknown recipe input"), 404
        row = record["inputs"][index]
        path = Path(row["path"]).resolve()
        if not path.is_relative_to(Path(record["recipe_path"]).parent.resolve()) or wf.file_sha(path) != row["sha256"]:
            raise ValueError("生成输入快照已变化")
        return send_file(path)

    @app.get("/api/v3/coding")
    def coding_coverage():
        return jsonify(coding.coverage(library))

    @app.get("/api/v3/coding/examples")
    def coding_examples():
        return jsonify(coding.examples(library, request.args.get("group", "layout"),
                                       request.args.get("code"), request.args.get("limit", 3)))

    @app.post("/api/v3/components/request")
    def component_request():
        import ppt_components
        p, body = mutation()
        return jsonify(ppt_components.request_selection(root, p, body, library))

    @app.post("/api/v3/regions")
    def region_request():
        import ppt_regions
        p, body = mutation()
        return jsonify(ppt_regions.request_region(root, p, body, library))

    @app.get("/api/v3/regions/<rid>/<kind>")
    def region_file(rid, kind):
        wf.safe_id(rid)
        if kind not in ("mask", "original", "record"):
            raise ValueError("unknown region artifact")
        record = next((x["details"] for x in wf.load(root)["revision_requests"]
                       if x.get("details", {}).get("id") == rid and
                       x.get("kind") in ("region_edit", "reserved_region")), None)
        if not record:
            raise ValueError("unknown registered region")
        if kind == "record":
            return jsonify(record)
        item = record.get(kind)
        if not item or wf.file_sha(wf.local(root, item["path"])) != item["sha256"]:
            raise ValueError("region artifact missing or changed")
        return send_file(wf.local(root, item["path"]), as_attachment=True)

    @app.get("/api/v3/presentation")
    def presentation():
        code = request.args.get("deck_code", "")
        if code:
            with assets.database(library) as db:
                rows = assets.current_records(db)
            rows = sorted([r for r in rows if r.get("deck_code") == code], key=lambda x: (x.get("order", 0), x["id"]))
            bundle = rows[0].get("deck_coding", {}).get("reference_bundle") if rows else None
            if bundle:
                context = coding.bundle_context(rows[0], library)
                rows = [assets.get(m["id"], m["version"], library) for m in context["members"]
                        if m["role"] == "main" and m["available"]]
            return jsonify(title=rows[0]["work"] if rows else "未找到整套参考",
                kind="reference", pages=[{"id": r["id"], "page_code": r["page_code"], "title": r["title"],
                    "order": r["order"], "version": r["version"], "sha256": r["sha256"],
                    "url": f"/api/assets/{r['id']}/download?version={r['version']}"} for r in rows])
        p = wf.load(root)
        return jsonify(title=p.get("project_name"), kind="project",
            pages=[{"id": x["page_id"], "title": x.get("title") or x.get("page_text", "").split("\n")[0],
                    "url": f"/api/v3/pages/{x['page_id']}/images/selected" if x.get("selected_output") else None}
                   for x in p["pages"]])

    @app.get("/api/v3/site-icons/<sid>")
    def site_icon(sid):
        wf.safe_id(sid)
        path = library / "site-icons" / (sid + ".png")
        if not path.is_file():
            return jsonify(error="icon not cached"), 404
        return send_file(path, mimetype="image/png")

    @app.post("/api/v3/sites/favorite")
    def site_favorite():
        p, body = mutation()
        if body["id"] not in {s["id"] for s in cart.site_catalog(library)["items"]}:
            raise ValueError("unknown site")
        with assets.database(library) as db:
            db.execute("CREATE TABLE IF NOT EXISTS site_favorites_v1(id TEXT PRIMARY KEY)")
            db.execute("INSERT OR IGNORE INTO site_favorites_v1 VALUES(?)" if body.get("enabled") else
                       "DELETE FROM site_favorites_v1 WHERE id=?", (body["id"],))
        return jsonify(id=body["id"], favorite=bool(body.get("enabled")))

    @app.get("/api/assets/<rid>/<mode>")
    def asset_file(rid, mode):
        if mode not in ("preview", "download"):
            return jsonify(error="unknown asset endpoint"), 404
        record = assets.get(rid, request.args.get("version"), library)
        path = assets.thumbnail(record, library) if mode == "preview" else assets.path_for(record, library)
        return send_file(path, as_attachment=mode == "download")

    @app.post("/api/v3/assets/refresh")
    def refresh():
        p, body = mutation()
        roots = assets.source_roots(library)
        # Never accept arbitrary local directories from a browser.
        paths = [Path(x) for x in roots] or [assets.DEFAULT_SOURCE]
        return jsonify(results=[assets.scan(path, library) for path in paths])

    @app.post("/api/v3/assets/favorite")
    def favorite():
        p, body = mutation()
        assets.get(body["id"], library=library)
        return jsonify(assets.favorite(body["id"], bool(body.get("enabled")), library))

    @app.post("/api/v3/cart/choose")
    def choose():
        p, body = mutation()
        return jsonify(assets.choose(root, p, body["id"], body.get("version"), body.get("usage", "structure"), library))

    @app.post("/api/v3/cart/link")
    def link():
        p, body = mutation()
        return jsonify(cart.add_link(root, p, body["url"], body.get("title", ""),
                                     body.get("usage", "structure"), body.get("comment", "")))

    @app.post("/api/v3/cart/update")
    def update_cart():
        p, body = mutation()
        return jsonify(cart.update(root, p, body["id"], body.get("patch"), body.get("remove", False)))

    @app.post("/api/v3/cart/submit")
    def submit_cart():
        p, body = mutation()
        progress.require_stage(root, p, body.get("stage", "stage1"))
        return jsonify(cart.submit(root, p, body.get("stage", "stage1"), body.get("comment", "")))

    @app.get("/api/v3/public-search")
    def public_search():
        return jsonify(cart.public_search(request.args.get("q", "")))

    @app.post("/api/v3/upload")
    def upload():
        p, body = mutation()
        file = request.files.get("file")
        if not file or not file.filename:
            raise ValueError("请选择 PNG/JPEG/WebP 图片")
        suffix = Path(file.filename).suffix.lower()
        if suffix not in assets.EXTENSIONS:
            raise ValueError("只接收 PNG/JPEG/WebP；其他资料请将路径交给 Agent")
        path = root / "imports" / (uuid.uuid4().hex + suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        file.save(path)
        try:
            assets.image_info(path)
            if body.get("page_id"):
                progress.require_stage(root, p, "samples")
                return jsonify(studio.add_candidate(root, p, body["page_id"], path))
            record = assets.import_image(path, {"title": body.get("title") or Path(file.filename).stem,
                                                "kind": body.get("kind", "slide"),
                                                  "role": "evidence" if body.get("role") == "evidence" else "reference",
                                                "source_url": body.get("source_url", ""),
                                                "tags": ["用户补充"]}, library)
            chosen = assets.choose(root, p, record["id"], record["version"], body.get("usage", "structure"), library)
            return jsonify(chosen)
        except Exception:
            # Only this freshly allocated upload file; never delete user originals.
            path.unlink(missing_ok=True)
            raise

    @app.post("/api/v3/draft")
    def draft():
        p, body = mutation()
        progress.require_stage(root, p, body.get("stage", "stage2"))
        return jsonify(studio.create_draft(root, p, body.get("patch", {}), body.get("comment", ""),
                                           body.get("stage", "stage2"), bool(body.get("submit"))))

    @app.post("/api/v3/form-draft")
    def form_draft():
        p, body = mutation()
        stage = body.get("stage", "stage1")
        progress.require_stage(root, p, stage)
        record = studio.autosave_form(
            root, p, stage, body.get("patch", {}), body.get("comment", ""),
            body.get("form_values"), body.get("draft_id"), body.get("draft_version", 0),
            bool(body.get("submit")), bool(body.get("clear")))
        return jsonify(record=record, revision=p["revision"], progress=progress.state(root, p))

    @app.post("/api/v3/restore")
    def restore():
        p, body = mutation()
        return jsonify(studio.restore(root, p, body["id"], body.get("comment", "")))

    @app.get("/api/v3/history/<hid>")
    def historical(hid):
        wf.safe_id(hid)
        path = root / "revisions" / (hid + ".json")
        if not path.is_file():
            return jsonify(error="historical version not found"), 404
        return jsonify(proposal=studio.proposal(wf.upgrade(wf.read(path))))

    @app.post("/api/v3/confirm")
    def confirm_v3():
        p, body = mutation()
        progress.require_stage(root, p, body["stage"])
        return jsonify(wf.confirm(root, p, body["stage"], "用户在分阶段工作台明确确认当前版本", "web"))

    @app.get("/api/v3/pages/<pid>/images/<cid>")
    def page_image(pid, cid):
        p = wf.load(root)
        value = studio._image_target(p, pid, None if cid == "selected" else cid)
        return send_file(wf.local(root, value["path"]))

    @app.post("/api/v3/annotations")
    def annotations():
        p, body = mutation()
        if body.get("target_kind") == "reference":
            return jsonify(annotation_io.reference(root, p, body["asset_id"], body["asset_version"],
                body["sha256"], body["shapes"], body.get("comment", ""), library,
                bool(body.get("submit", True)), body.get("stage", "stage1")))
        return jsonify(studio.annotate(root, p, body["page_id"], body["sha256"], body["shapes"],
                                        body.get("comment", ""), body.get("candidate_id"), bool(body.get("submit", True))))

    @app.get("/api/v3/annotations/<aid>/<mode>")
    def annotation_file(aid, mode):
        p = wf.load(root)
        record = next((x for x in p["annotations"] if x["id"] == aid), None)
        key = {"overlay": "overlay_path", "record": "handoff_path"}.get(mode)
        if not record or not key or not record.get(key):
            return jsonify(error="annotation handoff not found"), 404
        path = Path(record[key]).resolve()
        if not path.is_relative_to((root / "annotations").resolve()):
            raise ValueError("annotation path outside project")
        return send_file(path, as_attachment=mode == "record")

    @app.post("/api/v3/adopt")
    def adopt():
        p, body = mutation()
        return jsonify(studio.adopt(root, p, body["page_id"], body["id"], "用户在工作台采纳已审核图片"))

    @app.post("/api/v3/bundle")
    def bundle():
        p, body = mutation()
        return jsonify(studio.export_bundle(root, p, body.get("ids", []), body.get("page_ids", []),
                                            bool(body.get("include_current"))))

    @app.get("/api/bundles/<eid>")
    def download_bundle(eid):
        p = wf.load(root)
        record = next((x for x in p["asset_exports"] if x["id"] == eid), None)
        if not record:
            return jsonify(error="unknown export"), 404
        return send_file(record["path"], as_attachment=True)
