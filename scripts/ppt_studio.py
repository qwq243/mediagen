#!/usr/bin/env python3
"""Image-PPT v3 revisions, annotations, local composition and external handoff.

No automatic inference. `edit --execute --ack-cost` and `asset-render` require
recorded, version-bound authorizations. All produced images remain candidates.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

import ppt_assets as assets
import ppt_workflow as wf

EDITABLE = ("communication", "design", "pages", "notes_policy", "transition", "component_pack",
            "production_route", "reference_direction", "primary_language", "generation_contract")
PAGE_FIELDS = ("page_id", "page_role", "page_text", "title", "chapter", "logic", "layout_focus",
               "visual_instructions", "reference_ids", "asset_ids", "speaker_notes", "transition",
               "style_reference_page_id", "must_preserve", "required_elements", "forbidden_elements",
               "forbidden_items", "materials", "reserved_regions", "remarks")
STORYBOARD_FIELDS = ("title", "chapter", "page_text", "purpose", "key_message_or_question",
                     "visual_expression", "transition_in", "transition_out",
                     "information_relationship", "duration_seconds", "speaker_notes", "remarks")


def page(p, pid):
    try:
        return next(x for x in p["pages"] if x["page_id"] == pid)
    except StopIteration:
        raise ValueError("page not found") from None


def clean_patch(patch):
    if not isinstance(patch, dict) or any(k not in EDITABLE for k in patch):
        raise ValueError("patch includes fields outside the proposal; approvals/budgets/files are not editable")
    wf.reject_secrets(patch)
    out = copy.deepcopy(patch)
    for key in ("communication", "design", "notes_policy", "transition", "component_pack", "generation_contract"):
        if key in out and not isinstance(out[key], dict):
            raise ValueError(key + " must be an object")
    if "communication" in out:
        errors = wf.page_count_errors(out["communication"])
        if errors:
            raise ValueError("; ".join(errors))
        notes = out["communication"].get("source_notes", {})
        if not isinstance(notes, dict) or len(notes) > 100 or any(
                not isinstance(k, str) or not isinstance(v, str) or len(v) > 16000
                for k, v in notes.items()):
            raise ValueError("source notes must be individual text remarks")
    if "pages" in out:
        if not isinstance(out["pages"], list):
            raise ValueError("pages must be a list")
        for pg in out["pages"]:
            wf.safe_id(pg["page_id"])
            if any(k not in PAGE_FIELDS for k in pg):
                raise ValueError("page patch cannot contain output paths, receipts or arbitrary fields")
            if "reserved_regions" in pg:
                from ppt_regions import validate
                validate(pg["reserved_regions"])
        ids = [pg["page_id"] for pg in out["pages"]]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate page IDs")
    if "production_route" in out and out["production_route"] not in ("full_image", "agent_composite", "external"):
        raise ValueError("unknown production route")
    return out


def proposal(p):
    result = {k: copy.deepcopy(p[k]) for k in EDITABLE if k in p}
    result["pages"] = [{k: v for k, v in pg.items() if k in PAGE_FIELDS} for pg in p["pages"]]
    return result


def history(root):
    result = []
    for path in sorted((Path(root) / "revisions").glob("r*.json"), reverse=True):
        old = wf.read(path)
        result.append({"id": path.stem, "revision": old.get("revision", 0),
                       "project_name": old.get("project_name"), "page_count": len(old.get("pages", [])),
                       "message": old.get("last_change", "")})
    return result


def create_draft(root, p, patch=None, comment="", stage="stage2", submit=False,
                 kind="proposal", details=None):
    patch = clean_patch(patch or {})
    if not patch and not str(comment).strip() and not details:
        raise ValueError("empty modification request")
    if stage not in ("stage1", "stage2", "samples", "deck"):
        raise ValueError("unknown stage")
    record = {"id": "rev-" + uuid.uuid4().hex[:16], "base_revision": p["revision"],
              "base_proposal_hash": wf.sha(proposal(p)), "at": wf.now(), "stage": stage,
              "status": "submitted" if submit else "draft", "kind": kind, "patch": patch,
              "comment": str(comment), "details": details or {}}
    p["revision_requests"].append(record)
    p["last_change"] = "保存修改意见；尚未确认"
    wf.save(root, p)
    return record


def restore(root, p, history_id, comment):
    wf.safe_id(history_id)
    old_path = Path(root) / "revisions" / (history_id + ".json")
    if not old_path.is_file():
        raise ValueError("unknown historical version")
    return create_draft(root, p, proposal(wf.upgrade(wf.read(old_path))),
                        comment or "请对齐此历史方案与当前内容", submit=True, kind="restore",
                        details={"history_id": history_id})


def autosave_form(root, p, stage, patch, comment="", form_values=None,
                  draft_id=None, draft_version=0, submit=False, clear=False):
    """Upsert a versioned working draft; incomplete fields are retained, not applied."""
    if stage not in ("stage1", "stage2"):
        raise ValueError("unknown form stage")
    fields = form_values or {}
    allowed = {
        "stage1": {"audience", "communication_intent", "audience_outcome", "core_message",
                   "delivery_context", "artifact_afterlife", "content_divergence",
                   "duration_seconds", "page-count-mode", "page-count-exact",
                   "page-count-min", "page-count-max", "stage-comment"},
        "stage2": {"icons", "material", "grid", "human_policy", "font-display", "font-heading",
                   "font-body", "text_in_image", "reading_mode", "production_route",
                   "notes_mode", "transition-enabled", "transition-duration",
                   "components-enabled", "chapters", "stage-comment"}}
    individual_notes = {"source-note-" + r["id"] for r in p["references"] if r.get("role") == "content"}
    storyboard = {"story-" + pg["page_id"] + "-" + key for pg in p["pages"] for key in STORYBOARD_FIELDS}
    limit = 100 + (len(storyboard) if stage == "stage2" else len(individual_notes))
    if not isinstance(fields, dict) or len(fields) > limit or any(
            not isinstance(k, str) or
            not (k in allowed[stage] or stage == "stage1" and k in individual_notes or
                 stage == "stage2" and (k in storyboard or re.fullmatch(r"(palette|size)-[\w-]+", k))) or
            not isinstance(v, (str, bool)) or len(str(v)) > 16000 for k, v in fields.items()):
        raise ValueError("invalid form fields")
    if len(str(comment)) > 16000:
        raise ValueError("comment too long")
    wf.reject_secrets(fields)
    # Never retain arbitrary untrusted proposal/approval fields, even as an incomplete draft.
    if not isinstance(patch, dict) or any(k not in EDITABLE for k in patch):
        raise ValueError("patch includes fields outside the proposal")
    errors = []
    try:
        patch = clean_patch(patch)
    except ValueError as error:
        errors = [str(error)]
        patch = {}
    if submit and errors:
        raise ValueError("incomplete form; finish invalid fields before submitting")
    record = None
    if draft_id:
        record = next((x for x in p["revision_requests"] if x["id"] == draft_id), None)
        if not record or record["kind"] != "form_autosave" or record["stage"] != stage or record["status"] != "draft":
            raise ValueError("form draft is no longer editable; keep local changes and reload")
        if record["details"].get("autosave_version") != draft_version:
            raise ValueError("draft version changed; keep local changes and reload")
        if record["base_proposal_hash"] != wf.sha(proposal(p)):
            raise ValueError("proposal changed; align the local draft with Agent before replacing")
    if clear and not record:
        return None
    details = {"form_values": copy.deepcopy(fields), "validation_errors": errors,
               "autosave_version": (record["details"]["autosave_version"] if record else 0) + 1}
    if not record:
        return create_draft(root, p, patch, comment, stage, submit,
                            kind="form_autosave", details=details)
    record.update(patch=patch, comment=str(comment), at=wf.now(), details=details,
                  status="discarded" if clear else "submitted" if submit else "draft")
    p["last_change"] = "提交表单草稿待对齐" if submit else "自动保存表单草稿；尚未确认"
    wf.save(root, p)
    return record


def resolve(root, p, request_id, summary, action="apply", replacement=None, cart_review=False):
    request = next((x for x in p["revision_requests"] if x["id"] == request_id), None)
    if not request or request["status"] not in ("draft", "submitted"):
        raise ValueError("request is not pending")
    if not summary.strip():
        raise ValueError("agent alignment summary is required")
    if action not in ("apply", "discard"):
        raise ValueError("resolution must be apply or discard")
    if action == "discard":
        request.update(status="discarded", resolution=summary, resolved_at=wf.now())
        wf.save(root, p)
        return request
    if request.get("kind") == "form_autosave" and request.get("details", {}).get("validation_errors") and replacement is None:
        raise ValueError("incomplete form draft; Agent must align and supply a valid replacement")
    if request.get("kind") == "resource_cart" and not cart_review:
        raise ValueError("resolve cart submissions through ppt_cart apply with per-item decisions")
    if request.get("kind") in ("fixed_component", "region_edit") and replacement is None:
        raise ValueError("组件/蒙版请求必须先由 Agent 明确适配或编辑方案，不能以空补丁视为完成")
    if request["base_proposal_hash"] != wf.sha(proposal(p)) and replacement is None:
        raise ValueError("proposal changed since the request; agent must explicitly provide a rebased patch")
    patch = clean_patch(replacement if replacement is not None else request["patch"])
    before = {pg["page_id"]: wf.page_design_hash(root, p, pg) for pg in p["pages"]}
    old_stage1 = wf.subject(root, p, "stage1")
    for key, value in patch.items():
        if key == "pages":
            existing = {pg["page_id"]: pg for pg in p["pages"]}
            p["pages"] = [{**existing.get(pg["page_id"], {}), **pg} for pg in value]
        elif isinstance(value, dict) and isinstance(p.get(key), dict):
            # Design objects are authored as full subobjects; omitted top-level values are preserved.
            p[key] = {**p[key], **value}
        else:
            p[key] = value
    normalized = wf.upgrade(p)
    p.clear(); p.update(normalized)
    request = next(x for x in p["revision_requests"] if x["id"] == request_id)
    affected = [pg["page_id"] for pg in p["pages"]
                if before.get(pg["page_id"]) != wf.page_design_hash(root, p, pg)]
    removed = [pid for pid in before if pid not in {pg["page_id"] for pg in p["pages"]}]
    request.update(status="applied", resolution=summary, resolved_at=wf.now(),
                   impact={"affected_pages": affected, "removed_pages": removed,
                           "communication_changed": old_stage1 != wf.subject(root, p, "stage1"),
                           "preserved_pages": [pid for pid in before if pid not in affected + removed]})
    p["last_change"] = summary
    wf.save(root, p)
    return request


def _image_target(p, pid, candidate_id=None):
    pg = page(p, pid)
    image = next((x for x in pg["output_candidates"] if x["id"] == candidate_id), None) if candidate_id else pg.get("selected_output")
    if not image:
        raise ValueError("choose an existing image version")
    return image


def annotate(root, p, pid, image_hash, shapes, comment="", candidate_id=None, submit=True):
    import ppt_annotation_io as annotation_io
    target = _image_target(p, pid, candidate_id)
    path = wf.local(root, target["path"])
    if wf.file_sha(path) != image_hash:
        raise ValueError("image changed; annotation cannot be applied to another version")
    if not isinstance(shapes, list) or len(shapes) > 300:
        raise ValueError("invalid annotation list")
    for shape in shapes:
        if shape.get("tool") not in ("pen", "rect", "ellipse", "arrow", "text"):
            raise ValueError("unknown annotation tool")
        points = shape.get("points", [])
        if not points or len(points) > 6000:
            raise ValueError("annotation points missing/too many")
        if any(not isinstance(pt, list) or len(pt) != 2 or
               any(not isinstance(v, (float, int)) or not math.isfinite(v) or not 0 <= v <= 1 for v in pt)
               for pt in points):
            raise ValueError("annotation coordinates must be normalized to the original image")
        if len(str(shape.get("text", ""))) > 4000:
            raise ValueError("annotation text too long")
    record = {"id": "ann-" + uuid.uuid4().hex[:16], "target_kind": "page", "page_id": pid, "candidate_id": candidate_id,
              "base_path": str(path), "base_sha256": image_hash, "shapes": shapes,
              "comment": comment, "at": wf.now(), "status": "submitted" if submit else "draft"}
    annotation_io.handoff(root, record)
    p["annotations"].append(record)
    wf.save(root, p)
    if submit:
        create_draft(root, p, comment=comment or "请理解图上标注并对齐修改范围", stage="deck",
                     submit=True, kind="image", details={"annotation_id": record["id"], "page_id": pid,
                                                       "base_sha256": image_hash})
    return record


def candidate_subject(root, p, pid, candidate):
    return wf.sha({"page_design": wf.page_design_hash(root, p, page(p, pid)),
                   "file": wf.asset(root, candidate["path"]), "kind": candidate["kind"],
                   "candidate_id": candidate["id"]})


def add_candidate(root, p, pid, source, kind="user_import", provenance="用户回传图片", metadata=None):
    pg = page(p, pid)
    src = wf.local(root, source)
    info = assets.image_info(src)
    sw, sh = map(int, p["generation_contract"]["size"].split("x"))
    if abs(info["ratio"] - sw / sh) > 0.025:
        raise ValueError("candidate aspect ratio differs; do not stretch the imported page")
    if kind not in ("generated", "agent_composite", "user_import"):
        raise ValueError("candidate kind must describe actual production")
    if kind == "generated":
        if not any(c.get("output_path") == str(src) and c.get("output_sha256") == wf.file_sha(src)
                   and c.get("status") == "completed" for c in p["generation_calls"]):
            raise ValueError("generated candidate requires a completed controlled call")
    if kind == "agent_composite":
        if not any(c.get("output_path") == str(src) and c.get("output_sha256") == wf.file_sha(src)
                   for c in p["composition_records"]):
            raise ValueError("composite candidate requires a composition record")
    cid = "img-" + uuid.uuid4().hex[:16]
    dest = Path(root).resolve() / "outputs/candidates" / (pid + "-" + cid + src.suffix.lower())
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    metadata = dict(metadata or {})
    import image_recipe
    recipe = image_recipe.bundle_to(src, Path(root) / "generation-records")
    if recipe:
        metadata["generation_recipe"] = recipe
    if metadata.get("generation_recipe"):
        kept = wf.read(metadata["generation_recipe"]["path"])
        if any(x.get("sha256") == wf.file_sha(dest) for x in kept.get("outputs", [])):
            wf.write(str(dest) + ".recipe.json", kept)
    record = {"id": cid, "path": str(dest), "sha256": wf.file_sha(dest), "kind": kind,
              "provenance": provenance, "at": wf.now(), "technical": info, "metadata": metadata or {},
              "page_design_hash": wf.page_design_hash(root, p, pg), "status": "candidate"}
    # Generated path copies are tracked as aliases, not forged into separate inference calls.
    if kind == "generated":
        call = next(c for c in reversed(p["generation_calls"]) if c.get("output_path") == str(src))
        call.setdefault("candidate_paths", []).append(str(dest))
    pg["output_candidates"].append(record)
    wf.save(root, p)
    return {**record, "subject_hash": candidate_subject(root, p, pid, record)}


def audit_candidate(root, p, pid, cid, report):
    candidate = _image_target(p, pid, cid)
    if report.get("subject_hash") != candidate_subject(root, p, pid, candidate):
        raise ValueError("candidate audit is stale")
    if not report.get("independent") or not report.get("reviewer") or not report.get("evidence"):
        raise ValueError("candidate audit requires an actual separate review pass and evidence")
    if report.get("status") not in ("passed", "failed", "pending"):
        raise ValueError("invalid audit status")
    if report["status"] == "passed" and any(x.get("severity") in ("major", "blocker")
                                           and x.get("resolution") != "fixed" for x in report.get("findings", [])):
        raise ValueError("unresolved candidate issues cannot pass")
    candidate["audit"] = {**report, "at": wf.now()}
    wf.save(root, p)
    return candidate["audit"]


def adopt(root, p, pid, cid, evidence):
    if not evidence:
        raise ValueError("explicit adoption evidence required")
    if any(x["status"] in ("draft", "submitted") for x in p["revision_requests"]):
        raise ValueError("align pending revisions before adopting an image")
    pg = page(p, pid)
    candidate = _image_target(p, pid, cid)
    if candidate["page_design_hash"] != wf.page_design_hash(root, p, pg):
        raise ValueError("candidate belongs to an older page design")
    if not wf.valid(candidate.get("audit"), candidate_subject(root, p, pid, candidate)):
        raise ValueError("candidate needs a current visual audit before adoption")
    if candidate["sha256"] != wf.file_sha(candidate["path"]):
        raise ValueError("candidate image changed")
    pg["selected_output"] = {
        "path": candidate["path"], "sha256_at_selection": candidate["sha256"],
        "kind": candidate["kind"], "provenance": candidate["provenance"],
        "candidate_id": cid, "selected_at": wf.now(), "adoption_evidence": evidence,
        "metadata": copy.deepcopy(candidate.get("metadata", {}))}
    candidate["status"] = "adopted"
    p["audits"]["visual:" + pid] = {**candidate["audit"], "phase": "visual", "page_id": pid,
                                   "subject_hash": wf.subject(root, p, "visual", pid)}
    wf.save(root, p)
    return pg["selected_output"]


def export_bundle(root, p, ids, page_ids=None, include_current=False):
    selected_pages = [page(p, pid) for pid in (page_ids or [])]
    embedded = [r["embedded_asset"] for pg in selected_pages for r in pg.get("reserved_regions", [])
                if r.get("mode") == "image"]
    if not ids and not include_current and not embedded:
        raise ValueError("select assets or an existing page image; the whole library is never exported by default")
    chosen = {x["id"]: x for x in p["asset_selection"] + p.get("resource_cart", []) if x.get("path")}
    if len(ids) != len(set(ids)) or any(rid not in chosen for rid in ids):
        raise ValueError("export only explicitly selected project assets")
    eid = "bundle-" + uuid.uuid4().hex[:16]
    folder = Path(root).resolve() / "exports/assets" / eid
    folder.mkdir(parents=True)
    entries = []
    for rid in ids:
        item = chosen[rid]
        src = wf.local(root, item["path"])
        if wf.file_sha(src) != item["sha256"]:
            raise ValueError("pinned asset changed")
        filename = rid + src.suffix.lower()
        shutil.copyfile(src, folder / filename)
        entries.append({"id": rid, "file": filename, "version": item["version"],
                        "sha256": item["sha256"], "title": item["title"], "usage": item["usage"]})
    for item in embedded:
        src = wf.local(root, item["path"])
        if wf.file_sha(src) != item["sha256"]:
            raise ValueError("嵌入图片已变化，不能导出")
        filename = item["id"] + "-" + item["version"][:12] + src.suffix.lower()
        if not any(x["file"] == filename for x in entries):
            shutil.copyfile(src, folder / filename)
            entries.append({"id": item["id"], "file": filename, "version": item["version"],
                "sha256": item["sha256"], "title": item["title"], "usage": "embedded_image"})
    if include_current:
        for pg in selected_pages:
            if pg.get("selected_output"):
                src = wf.local(root, pg["selected_output"]["path"])
                filename = pg["page_id"] + "-current" + src.suffix.lower()
                shutil.copyfile(src, folder / filename)
                entries.append({"id": pg["page_id"], "file": filename, "sha256": wf.file_sha(src),
                                "title": "当前页面底图"})
    manifest = {"id": eid, "project": p.get("project_name"), "canvas": p["generation_contract"]["size"],
                "assets": entries, "pages": [{"page_id": pg["page_id"], "page_text": pg.get("page_text", ""),
                    "layout": pg.get("layout_focus", ""), "components": wf.component_values(p, pg),
                    "materials": pg.get("materials", []),
                    "reserved_regions": pg.get("reserved_regions", [])} for pg in selected_pages],
                "design": p["design"], "created_at": wf.now()}
    wf.write(folder / "manifest.json", manifest)
    (folder / "制作说明.md").write_text(
        "# 本机合成素材包\n\n画布：" + p["generation_contract"]["size"] +
        "\n\n保留原素材比例；具体页面文字、色卡、固定栏和摆放信息见 manifest.json。"
        "\n完成后导出 PNG/JPEG/WebP，在工作台选择对应页上传，或将本机路径交给 Agent 导入。"
        "\n回传只是新候选，需要核对内容与视觉后采纳。\n", encoding="utf-8")
    archive = folder.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in folder.iterdir():
            z.write(path, path.name)
    result = {"id": eid, "path": str(archive), "folder": str(folder), "at": wf.now(),
              "asset_ids": ids, "page_ids": [pg["page_id"] for pg in selected_pages],
              "download_url": f"/api/bundles/{eid}"}
    p["asset_exports"].append(result)
    wf.save(root, p)
    return result


def _box(value, width, height):
    if not isinstance(value, list) or len(value) != 4 or any(
            not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError("box must be [x,y,w,h] normalized")
    x, y, w, h = value
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1.00001 or y + h > 1.00001:
        raise ValueError("box outside canvas")
    return round(x * width), round(y * height), max(1, round(w * width)), max(1, round(h * height))


def compose(root, p, pid, recipe):
    """Deterministic Pillow composition, invoked by the agent, not a browser layer editor."""
    pg = page(p, pid)
    selected = {x["id"]: x for x in p["asset_selection"]}
    selected.update({x["id"]: x for x in p["references"] if x.get("path")})
    w, h = map(int, p["generation_contract"]["size"].split("x"))
    canvas = Image.new("RGBA", (w, h), recipe.get("background", p["design"]["palette"]["background"]))
    inputs = []
    contains_evidence = False
    if recipe.get("base_candidate"):
        base = _image_target(p, pid, recipe["base_candidate"])
        contains_evidence = bool(base.get("metadata", {}).get("contains_evidence"))
        with Image.open(base["path"]) as im:
            if abs(im.width / im.height - w / h) > .025:
                raise ValueError("base image ratio mismatch")
            canvas = im.convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
        inputs.append(wf.asset(root, base["path"]))
    for layer in recipe.get("layers", []):
        x, y, bw, bh = _box(layer["box"], w, h)
        if layer.get("type", "asset") == "text":
            values = wf.component_values(p, pg)
            text = str(values.get(layer.get("slot"), layer.get("text", "")))
            font_path = Path(layer.get("font_path", r"C:\Windows\Fonts\msyh.ttc"))
            font = ImageFont.truetype(str(font_path), int(layer.get("size", 36)))
            draw = ImageDraw.Draw(canvas)
            bounds = draw.multiline_textbbox((0, 0), text, font=font, spacing=8)
            if bounds[2] - bounds[0] > bw or bounds[3] - bounds[1] > bh:
                raise ValueError("text does not fit its declared box; adjust before composing")
            draw.multiline_text((x, y), text, font=font, fill=layer.get("color", p["design"]["palette"]["text"]), spacing=8)
        elif layer.get("type") == "progress":
            progress = wf.component_values(p, pg).get("progress", 0)
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((x, y, x + bw, y + bh), fill=layer.get("background", "#E0E5EB"))
            draw.rectangle((x, y, x + round(bw * progress), y + bh),
                           fill=layer.get("color", p["design"]["palette"]["primary"]))
        else:
            item = selected.get(layer.get("asset_id"))
            if not item:
                raise ValueError("composition asset must be selected/registered")
            contains_evidence = contains_evidence or bool(item.get("protected_evidence") or item.get("role") == "evidence")
            src = wf.local(root, item["path"])
            if item.get("sha256") and wf.file_sha(src) != item["sha256"]:
                raise ValueError("composition input changed")
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im).convert("RGBA")
                if layer.get("crop"):
                    cx, cy, cw, ch = _box(layer["crop"], im.width, im.height)
                    im = im.crop((cx, cy, cx + cw, cy + ch))
                if layer.get("fit", "contain") == "cover":
                    im = ImageOps.fit(im, (bw, bh), method=Image.Resampling.LANCZOS)
                else:
                    im.thumbnail((bw, bh), Image.Resampling.LANCZOS)
                canvas.alpha_composite(im, (x + (bw - im.width) // 2, y + (bh - im.height) // 2))
            inputs.append(wf.asset(root, src))
    out = Path(root).resolve() / "outputs/composites" / (pid + "-" + uuid.uuid4().hex[:12] + ".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out)
    record = {"id": "cmp-" + uuid.uuid4().hex[:16], "page_id": pid, "recipe": recipe,
              "inputs": inputs, "output_path": str(out), "output_sha256": wf.file_sha(out), "at": wf.now()}
    p["composition_records"].append(record)
    wf.save(root, p)
    return add_candidate(root, p, pid, out, "agent_composite", "确定性素材合成",
                         {"composition_id": record["id"], "contains_evidence": contains_evidence})


def prepare_edit(root, p, pid, instruction, candidate_id=None, mask=None, preserve=None):
    pg = page(p, pid)
    base = _image_target(p, pid, candidate_id)
    if pg.get("materials") or base.get("metadata", {}).get("contains_evidence"):
        raise ValueError("flattened evidence must not enter the model; regenerate the clean body then composite originals")
    if not instruction.strip():
        raise ValueError("explicit edit instruction required")
    record = {"id": "edit-" + uuid.uuid4().hex[:16], "page_id": pid, "base": wf.asset(root, base["path"]),
              "instruction": instruction, "preserve": preserve or [], "at": wf.now(),
              "page_design_hash": wf.page_design_hash(root, p, pg)}
    if mask:
        src = wf.local(root, mask)
        with Image.open(src) as im, Image.open(base["path"]) as original:
            if im.size != original.size or im.mode != "RGBA":
                raise ValueError("edit mask must be RGBA and match the clean base image dimensions")
        dest = Path(root) / "assets/masks" / (wf.file_sha(src) + ".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        record["mask"] = wf.asset(root, dest)
    p["edit_plans"].append(record)
    wf.save(root, p)
    return record


def edit(root, p, edit_id, execute=False, ack_cost=False):
    plan = next((x for x in p["edit_plans"] if x["id"] == edit_id), None)
    if not plan:
        raise ValueError("unknown edit plan")
    pg = page(p, plan["page_id"])
    if plan["page_design_hash"] != wf.page_design_hash(root, p, pg):
        raise ValueError("edit plan belongs to an older page design")
    for key in ("base", "mask"):
        if plan.get(key) and wf.file_sha(plan[key]["path"]) != plan[key]["sha256"]:
            raise ValueError("edit input changed")
    inspection = wf.check(root, p, "samples")
    if not inspection["ok"]:
        raise ValueError("; ".join(inspection["errors"]))
    prompt = (wf.prompts(root, p)[pg["page_id"]] +
              "\nEDIT THE SUPPLIED CLEAN IMAGE. Apply only these requested changes:\n" + plan["instruction"] +
              "\nPreserve everything else, particularly: " + json.dumps(plan["preserve"], ensure_ascii=False) +
              "\nDo not reproduce annotations, circles or reviewer comments.")
    prompt_hash = wf.sha({"page_design": plan["page_design_hash"], "prompt": prompt,
                          "base": plan["base"], "mask": plan.get("mask")})
    authorization_hash = wf.sha({"design": wf.design_hash(root, p), "prompt_hash": prompt_hash})
    if not execute:
        return {"dry_run": True, "authorization_hash": authorization_hash, "edit_id": edit_id,
                "prompt_subject_hash": prompt_hash,
                "prompt": prompt, "base": plan["base"], "mask": plan.get("mask"), "inference_performed": False}
    if not wf.valid(plan.get("prompt_audit"), prompt_hash):
        raise ValueError("edit-specific prompt needs an independent current review before execution")
    auth = p["generation_authorization"]
    used = sum(c.get("authorization_id") == auth.get("id") for c in p["generation_calls"])
    if (not ack_cost or not auth.get("user_evidence") or auth.get("edit_hash") != authorization_hash
            or used >= auth.get("max_calls", 0)):
        raise ValueError("edit requires its own current hash-bound authorization and remaining call budget")
    prompt_path = Path(root) / "prompts" / (edit_id + ".txt")
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    out = Path(root).resolve() / "outputs/edits" / (pg["page_id"] + "-" + uuid.uuid4().hex[:12] + ".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(wf.HERE / "newapi_image.py"), "edit", "--image", plan["base"]["path"],
           "--prompt-file", str(prompt_path), "--model", p["generation_contract"]["model"],
           "--size", p["generation_contract"]["size"], "--quality", p["generation_contract"]["quality"],
           "--output-format", "png", "--retries", "0", "--out", str(out)]
    if plan.get("mask"):
        cmd += ["--mask", plan["mask"]["path"]]
    for item in p.get("asset_selection", []):
        if (item.get("model_allowed") and item["usage"] != "structure"
                and wf.uses_asset(p, pg, item)):
            cmd += ["--image", str(wf.local(root, item["path"]))]
    call = {"page_id": pg["page_id"], "edit_id": edit_id, "authorization_id": auth["id"],
            "started_at": wf.now(), "status": "started", "output_path": str(out)}
    p["generation_calls"].append(call); wf.save(root, p)
    completed = subprocess.run(cmd, capture_output=True)
    call["status"] = "completed" if completed.returncode == 0 and out.is_file() else "failed"
    call["return_code"] = completed.returncode
    if call["status"] == "completed":
        call["output_sha256"] = wf.file_sha(out)
    wf.save(root, p)
    if call["status"] != "completed":
        raise ValueError("edit failed; stopped without additional calls or model switch")
    return add_candidate(root, p, pg["page_id"], out, "generated", "图片编辑模型输出", {"edit_id": edit_id})


def asset_request(spec, library=wf.LIBRARY):
    """Independent assets do not need a deck. A request is not an authorization."""
    wf.reject_secrets(spec)
    if not spec.get("prompt", "").strip() or spec.get("kind") not in assets.KINDS:
        raise ValueError("asset request needs prompt and kind")
    refs = []
    for ref in spec.get("references", []):
        item = assets.get(ref["id"], ref.get("version"), library)
        if item.get("original_metadata", {}).get("role") == "evidence":
            raise ValueError("evidence cannot be used as an image-model reference")
        refs.append({"id": item["id"], "version": item["version"], "path": str(assets.pin(item, library)),
                     "sha256": item["sha256"]})
    jid = "asset-" + uuid.uuid4().hex[:16]
    request = {"id": jid, "spec": {**spec, "references": refs}, "at": wf.now(), "calls": [],
               "authorization": {}, "status": "pending"}
    wf.write(Path(library) / "asset-jobs" / (jid + ".json"), request)
    return request


def asset_render(job_id, execute=False, ack_cost=False, library=wf.LIBRARY):
    wf.safe_id(job_id)
    if not execute:
        return _asset_render(job_id, execute, ack_cost, library)
    lock = Path(library) / "asset-jobs" / (job_id + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("asset generation already running; do not issue a concurrent call")
    try:
        return _asset_render(job_id, execute, ack_cost, library)
    finally:
        os.close(fd)
        lock.unlink()


def _asset_render(job_id, execute=False, ack_cost=False, library=wf.LIBRARY):
    wf.safe_id(job_id)
    path = Path(library) / "asset-jobs" / (job_id + ".json")
    job = wf.read(path)
    spec = job["spec"]
    for ref in spec["references"]:
        if wf.file_sha(ref["path"]) != ref["sha256"]:
            raise ValueError("asset generation reference changed")
    digest = wf.sha(spec)
    if not execute:
        return {"id": job_id, "spec_hash": digest, "inference_performed": False}
    auth = job["authorization"]
    if (not ack_cost or not auth.get("evidence") or auth.get("spec_hash") != digest or
            len(job["calls"]) >= auth.get("max_calls", 0)):
        raise ValueError("independent asset generation needs explicit current authorization and budget")
    folder = path.parent / job_id
    folder.mkdir(exist_ok=True)
    prompt = folder / "prompt.txt"
    prompt.write_text(spec["prompt"], encoding="utf-8")
    out = folder / ("result-" + uuid.uuid4().hex[:12] + ".png")
    cmd = [sys.executable, str(wf.HERE / "newapi_image.py"), "edit" if spec["references"] else "generate",
           "--prompt-file", str(prompt), "--model", spec.get("model", "gpt-image-2"),
           "--size", spec.get("size", "1024x1024"), "--quality", "high", "--output-format", "png",
           "--retries", "0", "--out", str(out)]
    for ref in spec["references"]:
        cmd += ["--image", ref["path"]]
    if spec.get("transparent"):
        cmd += ["--transparent"]
    call = {"at": wf.now(), "status": "started", "out": str(out)}
    job["calls"].append(call); wf.write(path, job)
    completed = subprocess.run(cmd, capture_output=True)
    call["status"] = "completed" if completed.returncode == 0 and out.is_file() else "failed"
    job["status"] = call["status"]; wf.write(path, job)
    if call["status"] != "completed":
        raise ValueError("asset generation failed; no retry or model switch")
    if spec.get("transparent") and not assets.image_info(out)["alpha"]:
        job["status"] = "needs_review"
        job["issue"] = "requested transparent asset lacks an alpha channel"
        wf.write(path, job)
        raise ValueError(job["issue"] + "; no automatic regeneration")
    result = assets.import_image(out, {k: spec[k] for k in ("title", "kind", "tags", "parent") if k in spec} |
                                 {"provenance": {"asset_job": job_id}, "status": "candidate"}, library)
    job["result"] = {"id": result["id"], "version": result["version"]}
    wf.write(path, job)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path)
    parser.add_argument("--library", type=Path, default=wf.LIBRARY)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("history")
    c = sub.add_parser("draft"); c.add_argument("--patch", type=Path); c.add_argument("--comment", default="")
    c.add_argument("--stage", default="stage2"); c.add_argument("--submit", action="store_true")
    c = sub.add_parser("resolve"); c.add_argument("--id", required=True); c.add_argument("--summary", required=True)
    c.add_argument("--action", choices=("apply", "discard"), default="apply"); c.add_argument("--patch", type=Path)
    c = sub.add_parser("restore"); c.add_argument("--id", required=True); c.add_argument("--comment", default="")
    c = sub.add_parser("import-page"); c.add_argument("--page", required=True); c.add_argument("--image", required=True)
    c = sub.add_parser("candidate-audit"); c.add_argument("--page", required=True); c.add_argument("--id", required=True)
    c.add_argument("--report", type=Path, required=True)
    c = sub.add_parser("adopt"); c.add_argument("--page", required=True); c.add_argument("--id", required=True)
    c.add_argument("--evidence", required=True)
    c = sub.add_parser("compose"); c.add_argument("--page", required=True); c.add_argument("--recipe", type=Path, required=True)
    c = sub.add_parser("bundle"); c.add_argument("--ids", nargs="*", default=[]); c.add_argument("--pages", nargs="*", default=[])
    c.add_argument("--include-current", action="store_true")
    c = sub.add_parser("prepare-edit"); c.add_argument("--page", required=True); c.add_argument("--instruction", required=True)
    c.add_argument("--candidate"); c.add_argument("--mask")
    c = sub.add_parser("authorize-edit"); c.add_argument("--id", required=True); c.add_argument("--calls", type=int, required=True)
    c.add_argument("--evidence", required=True)
    c = sub.add_parser("edit-audit"); c.add_argument("--id", required=True); c.add_argument("--report", type=Path, required=True)
    c = sub.add_parser("edit"); c.add_argument("--id", required=True); c.add_argument("--execute", action="store_true")
    c.add_argument("--ack-cost", action="store_true")
    c = sub.add_parser("asset-request"); c.add_argument("--spec", type=Path, required=True)
    c = sub.add_parser("asset-authorize"); c.add_argument("--id", required=True); c.add_argument("--calls", type=int, required=True)
    c.add_argument("--evidence", required=True)
    c = sub.add_parser("asset-render"); c.add_argument("--id", required=True); c.add_argument("--execute", action="store_true")
    c.add_argument("--ack-cost", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "asset-request":
            result = asset_request(wf.read(args.spec), args.library)
        elif args.cmd == "asset-render":
            result = asset_render(args.id, args.execute, args.ack_cost, args.library)
        elif args.cmd == "asset-authorize":
            wf.safe_id(args.id)
            path = args.library / "asset-jobs" / (args.id + ".json")
            job = wf.read(path)
            if args.calls < 1 or not args.evidence.strip():
                raise ValueError("explicit positive call budget and evidence required")
            job["authorization"] = {"spec_hash": wf.sha(job["spec"]), "max_calls": args.calls,
                                     "evidence": args.evidence, "at": wf.now()}
            wf.write(path, job); result = job["authorization"]
        else:
            if not args.job:
                raise ValueError("--job required")
            p = wf.load(args.job)
            if args.cmd == "history": result = history(args.job)
            elif args.cmd == "draft":
                result = create_draft(args.job, p, wf.read(args.patch) if args.patch else {},
                                      args.comment, args.stage, args.submit)
            elif args.cmd == "resolve":
                result = resolve(args.job, p, args.id, args.summary, args.action, wf.read(args.patch) if args.patch else None)
            elif args.cmd == "restore": result = restore(args.job, p, args.id, args.comment)
            elif args.cmd == "import-page": result = add_candidate(args.job, p, args.page, args.image)
            elif args.cmd == "candidate-audit": result = audit_candidate(args.job, p, args.page, args.id, wf.read(args.report))
            elif args.cmd == "adopt": result = adopt(args.job, p, args.page, args.id, args.evidence)
            elif args.cmd == "compose": result = compose(args.job, p, args.page, wf.read(args.recipe))
            elif args.cmd == "bundle": result = export_bundle(args.job, p, args.ids, args.pages, args.include_current)
            elif args.cmd == "prepare-edit":
                result = prepare_edit(args.job, p, args.page, args.instruction, args.candidate, args.mask)
            elif args.cmd == "edit": result = edit(args.job, p, args.id, args.execute, args.ack_cost)
            elif args.cmd == "edit-audit":
                dry = edit(args.job, p, args.id)
                report = wf.read(args.report)
                if (report.get("subject_hash") != dry["prompt_subject_hash"] or
                    not report.get("independent") or not report.get("reviewer") or not report.get("evidence") or
                    report.get("status") not in ("passed", "failed", "pending") or
                    (report.get("status") == "passed" and any(f.get("severity") in ("major", "blocker")
                     and f.get("resolution") != "fixed" for f in report.get("findings", [])))):
                    raise ValueError("edit prompt audit requires current hash, evidence and resolved issues")
                plan = next(x for x in p["edit_plans"] if x["id"] == args.id)
                plan["prompt_audit"] = {**report, "at": wf.now()}
                wf.save(args.job, p); result = plan["prompt_audit"]
            elif args.cmd == "authorize-edit":
                dry = edit(args.job, p, args.id)
                if args.calls < 1 or not args.evidence.strip(): raise ValueError("explicit budget/evidence required")
                p["generation_authorization"] = {"id": uuid.uuid4().hex, "max_calls": args.calls,
                    "edit_hash": dry["authorization_hash"], "user_evidence": args.evidence, "at": wf.now()}
                wf.save(args.job, p); result = p["generation_authorization"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, KeyError, ValueError, StopIteration) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
