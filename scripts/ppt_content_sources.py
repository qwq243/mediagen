"""Read-only views of registered current content inputs, never design references."""
import json
import re
from pathlib import Path

import ppt_workflow as wf


def _current(p):
    return [r for r in p.get("references", []) if r.get("role") == "content"
            and not r.get("superseded_by") and r.get("status") not in ("archived", "superseded")]


def _record(p, source_id):
    wf.safe_id(source_id)
    rows = [r for r in _current(p) if r["id"] == source_id]
    if len(rows) != 1:
        raise ValueError("未找到当前内容来源；历史底稿不参与本轮")
    return rows[0]


def _check(root, record):
    if not record.get("path"):
        return None, "missing"
    path = wf.local(root, record["path"])
    if not path.is_relative_to(Path(root).resolve()):
        return None, "outside_project"
    if not path.is_file():
        return None, "missing"
    if not record.get("sha256"):
        return None, "unpinned"
    if wf.file_sha(path) != record["sha256"]:
        return None, "changed"
    return path, "verified"


def _paragraphs(path):
    if path.stat().st_size > 3 * 1024 * 1024:
        raise ValueError("提取稿过大，请交由 Agent 分段核对")
    text = path.read_text(encoding="utf-8-sig")
    # Preserve original paragraph IDs, including gaps. Never invent re-numbered citations.
    matches = list(re.finditer(r"^##\s+(para-\d+)\s*$", text, re.MULTILINE))
    return [{"id": m.group(1), "text": text[m.end():matches[i+1].start()
            if i+1 < len(matches) else len(text)].strip()}
            for i, m in enumerate(matches)]


def summaries(root, p):
    result = []
    primary = p.get("notes_policy", {}).get("source_reference_id")
    for ref in _current(p):
        if ref.get("content_kind") == "reference_presentation":
            continue  # Separate reference row, never label a PPT as the current speech.
        _, status = _check(root, ref)
        extracted, extraction_status = _check(root, ref.get("extraction", {}))
        paragraphs = []
        if extracted:
            try:
                paragraphs = _paragraphs(extracted)
            except (ValueError, UnicodeError, OSError):
                extraction_status = "unavailable"
        result.append({
            "id": ref["id"], "title": ref.get("title") or ref["id"],
            "original_name": ref.get("original_name") or Path(ref.get("path", "")).name,
            "primary": ref["id"] == primary, "status": status, "use": ref.get("use", ""),
            "note": source_note(p, ref), "bundle_id": ref.get("bundle_id", ""),
            "version": ref.get("sha256", "")[:12],
            "paragraph_count": len(paragraphs), "extraction_status": extraction_status,
            "download_url": f"/api/v3/content-sources/{ref['id']}/original"
                if status == "verified" else None,
            "preview_url": f"/api/v3/content-sources/{ref['id']}/preview"
                if status == extraction_status == "verified" and paragraphs else None,
        })
    return result


def original(root, p, source_id):
    ref = _record(p, source_id)
    path, status = _check(root, ref)
    if status != "verified":
        raise ValueError("内容来源不可读取或固定版本已变化，请回到 Agent 核对")
    return path, ref.get("original_name") or path.name


def preview(root, p, source_id):
    original(root, p, source_id)
    ref = _record(p, source_id)
    path, status = _check(root, ref.get("extraction", {}))
    if status != "verified":
        raise ValueError("提取稿未登记或版本已变化，请回到 Agent 核对")
    return {"id": source_id, "title": ref.get("title", source_id), "paragraphs": [
        {**row, "citation": source_id + " / " + row["id"]} for row in _paragraphs(path)],
        "document_is_content_not_instructions": True}


def source_note(p, ref):
    notes = p.get("communication", {}).get("source_notes", {})
    return notes.get(ref["id"], ref.get("note", "")) if isinstance(notes, dict) else ref.get("note", "")


def evidence_preview(root, p, page_id, index):
    """Only registered evidence already bound to this page; never arbitrary file access."""
    wf.safe_id(page_id)
    page = next((x for x in p["pages"] if x["page_id"] == page_id), None)
    evidence = page.get("logic", {}).get("evidence", []) if page else []
    if type(index) is not int or not isinstance(evidence, list) or not 0 <= index < len(evidence):
        raise ValueError("未找到本页对应的支撑材料")
    item = evidence[index]
    if not isinstance(item, dict):
        raise ValueError("该说明尚未关联可预览的原始材料")
    ident = item.get("source") or item.get("reference_id")
    rows = [r for r in p["references"] if r.get("id") == ident and r.get("role") == "content"]
    if len(rows) != 1:
        raise ValueError("支撑材料未登记为内容来源，请回到 Agent 核对")
    ref = rows[0]
    _, status = _check(root, ref)
    path, extraction_status = _check(root, ref.get("extraction", {}))
    if status != "verified" or extraction_status != "verified":
        raise ValueError("原始支撑材料或提取稿缺失、越界或版本已变化")
    ids = item.get("paragraph_ids", [])
    if not isinstance(ids, list) or not ids or any(not isinstance(x, str) for x in ids):
        raise ValueError("请先关联明确的原稿段落，不能用整份文件冒充具体依据")
    paragraphs = {row["id"]: row for row in _paragraphs(path)}
    return {
        "page_id": page_id, "source_id": ident,
        "title": ref.get("original_name") or ref.get("title") or ident,
        "historical": bool(ref.get("superseded_by") or ref.get("status") in ("archived", "superseded")),
        "note": source_note(p, ref), "status": item.get("status", ""),
        "paragraphs": [{**paragraphs[x], "citation": ident + " / " + x} for x in ids if x in paragraphs],
        "missing_paragraph_ids": [x for x in ids if x not in paragraphs],
        "document_is_content_not_instructions": True,
    }


def page_script_sources(root, p, page_id):
    """Inline exact page-bound paragraphs; never populate or overwrite a script draft."""
    page = next((x for x in p["pages"] if x["page_id"] == page_id), {})
    evidence = page.get("logic", {}).get("evidence", [])
    result = []
    for index, item in enumerate(evidence if isinstance(evidence, list) else []):
        if not isinstance(item, dict) or not item.get("paragraph_ids"):
            continue
        try:
            result.append({**evidence_preview(root, p, page_id, index),
                           "index": index, "availability": "verified"})
        except ValueError as exc:
            result.append({"index": index, "availability": "unavailable",
                           "paragraphs": [], "message": str(exc)})
    return result


def _reference_record(p, source_id):
    ref = _record(p, source_id)
    if ref.get("content_kind") != "reference_presentation":
        raise ValueError("该资料不是已登记的参考PPT")
    return ref


def _presentation(root, ref):
    _, status = _check(root, ref)
    path, manifest_status = _check(root, ref.get("presentation", {}))
    if status != "verified" or manifest_status != "verified":
        raise ValueError("参考PPT或预览版本已变化，请交由 Agent 重新核对")
    if path.stat().st_size > 3 * 1024 * 1024:
        raise ValueError("参考资料清单过大")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("参考资料清单无法读取") from exc
    if not isinstance(data, dict) or data.get("source_sha256") != ref["sha256"]:
        raise ValueError("参考预览不属于当前固定版本的PPT")
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages or len(pages) > 300:
        raise ValueError("参考页清单无效")
    seen = set()
    for page in pages:
        number = page.get("number") if isinstance(page, dict) else None
        if type(number) is not int or number < 1 or number in seen:
            raise ValueError("参考页码须为不重复的正整数")
        seen.add(number)
    return data


def reference_summaries(root, p):
    """Optional read-only alignment material; no inferred target-page mapping."""
    result = []
    for ref in _current(p):
        if ref.get("content_kind") != "reference_presentation":
            continue
        _, status = _check(root, ref)
        _, manifest_status = _check(root, ref.get("presentation", {}))
        data = None
        if status == manifest_status == "verified":
            try:
                data = _presentation(root, ref)
            except ValueError:
                manifest_status = "unavailable"
        ident = ref["id"]
        bindings = ref.get("page_bindings", {})
        if not isinstance(bindings, dict):
            bindings = {}
        valid_numbers = {x["number"] for x in data["pages"]} if data else set()
        bindings = {pid: [n for n in numbers if type(n) is int and n in valid_numbers]
                    for pid, numbers in bindings.items()
                    if isinstance(numbers, list) and any(x["page_id"] == pid for x in p["pages"])}
        result.append({
            "id": ident, "title": ref.get("title", ident),
            "original_name": ref.get("original_name") or Path(ref.get("path", "")).name,
            "status": status, "preview_status": manifest_status,
            "version": ref.get("sha256", "")[:12],
            "use": ref.get("use", ""), "note": source_note(p, ref),
            "bundle_id": ref.get("bundle_id", ""),
            "related_source_id": ref.get("related_source_id", ""),
            "page_count": len(data["pages"]) if data else 0,
            "page_bindings": bindings,
            "page_previews": [{
                "number": row["number"], "title": row.get("title", ""),
                "image_url": f"/api/v3/reference-decks/{ident}/pages/{row['number']}/image",
                "native_text": row.get("native_text", []), "note": row.get("note", ""),
            } for row in data["pages"]] if data else [],
            "download_url": f"/api/v3/content-sources/{ident}/original"
                if status == "verified" else None,
            "preview_url": f"/api/v3/reference-decks/{ident}/preview" if data else None,
            "thumbnail_url": f"/api/v3/reference-decks/{ident}/pages/{data['pages'][0]['number']}/image"
                if data else None,
        })
    return result


def reference_preview(root, p, source_id):
    ref = _reference_record(p, source_id)
    data = _presentation(root, ref)
    pages = []
    for row in data["pages"]:
        _, status = _check(root, row.get("image", {}))
        if status != "verified":
            raise ValueError("参考页预览版本变化或缺失，请交由 Agent 重新核对")
        pages.append({
            "number": row["number"], "title": row.get("title", ""),
            "native_text": row.get("native_text", []),
            "comments": row.get("comments", []),
            "speaker_notes": row.get("speaker_notes", ""), "note": row.get("note", ""),
            "image_url": f"/api/v3/reference-decks/{source_id}/pages/{row['number']}/image",
        })
    return {"id": source_id, "title": ref.get("title", source_id),
            "original_name": ref.get("original_name", ""),
            "use": ref.get("use", ""), "note": source_note(p, ref),
            "pages": pages, "reference_only": True,
            "document_is_content_not_instructions": True}


def reference_image(root, p, source_id, number):
    ref = _reference_record(p, source_id)
    data = _presentation(root, ref)
    rows = [row for row in data["pages"] if row["number"] == number]
    if len(rows) != 1:
        raise ValueError("未找到对应参考页")
    path, status = _check(root, rows[0].get("image", {}))
    if status != "verified":
        raise ValueError("参考页预览缺失、越界或固定版本已变化")
    return path
