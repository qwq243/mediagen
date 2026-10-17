#!/usr/bin/env python3
"""Shared local asset catalogue. Source folders are read-only; selections are pinned.

Both the workbench and CLI call this module. Scanning/searching never calls a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageOps

import ppt_workflow as wf
import ppt_coding as coding

DEFAULT_SOURCE = Path(r"D:\00\项目\日常\学校\PPT素材\汇总-PPT参考库-2026-10-15")
KINDS = ("deck", "slide", "webpage", "header", "footer", "navigation", "brand", "icon",
         "background", "decoration", "illustration")
USAGES = ("structure", "style", "layout", "material")
EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


@contextmanager
def database(library=wf.LIBRARY):
    folder = Path(library)
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / "index.sqlite3", timeout=20)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS assets_v3 (
          id TEXT NOT NULL, version TEXT NOT NULL, payload TEXT NOT NULL,
          current INTEGER NOT NULL, PRIMARY KEY(id,version));
        CREATE TABLE IF NOT EXISTS asset_sources_v3 (
          root TEXT PRIMARY KEY, refreshed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS asset_favorites_v3 (id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS asset_structure_v3 (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS asset_removals_v3 (
          id TEXT PRIMARY KEY, version TEXT NOT NULL, removed_at TEXT NOT NULL);
    """)
    coding.tables(db)
    try:
        yield db
        db.commit()
    finally:
        db.close()


def image_info(path):
    path = Path(path)
    if path.suffix.lower() not in EXTENSIONS:
        raise ValueError("asset must be a PNG/JPEG/WebP image")
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        w, h = im.size
        alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
    return {"width": w, "height": h, "ratio": round(w / h, 5), "alpha": alpha}


def inferred_structure(row):
    """A suggestion layer, never an overwrite of original human labels."""
    text = " ".join(str(row.get(k, "")) for k in ("pageType", "layout", "summary"))
    relations = [label for label, terms in {
        "对比": ("对比", "对照", "比较"), "因果": ("因果", "原因", "影响"),
        "并列": ("并列", "三栏", "四栏"), "递进": ("递进", "阶梯"),
        "流程": ("流程", "步骤", "时间轴"), "层级": ("层级", "金字塔", "分层"),
        "总分": ("总分", "放射", "分支"),
    }.items() if any(t in text for t in terms)]
    roles = [label for label, terms in {
        "提出问题": ("痛点", "背景", "需求"), "解释机制": ("技术", "机制", "原理", "方案"),
        "提供证据": ("验证", "成果", "成效", "案例", "实验"),
        "承接演示": ("演示", "实操"), "总结收束": ("总结", "尾页", "展望"),
    }.items() if any(t in text for t in terms)]
    return {"status": "suggested", "method": "source-label heuristic; agent/user may correct",
            "page_roles": roles, "relationships": relations}


def _store(db, record):
    correction = db.execute("SELECT payload FROM asset_structure_v3 WHERE id=?", (record["id"],)).fetchone()
    if correction:
        record["structure_suggestions"] = json.loads(correction[0])
    record["version"] = wf.sha({k: v for k, v in record.items()
                                if k not in ("version", "indexed_at", "object_path")})
    record["indexed_at"] = wf.now()
    db.execute("UPDATE assets_v3 SET current=0 WHERE id=?", (record["id"],))
    db.execute("INSERT INTO assets_v3 VALUES(?,?,?,1) ON CONFLICT(id,version) "
               "DO UPDATE SET current=1,payload=excluded.payload",
               (record["id"], record["version"], json.dumps(record, ensure_ascii=False)))
    return record


def scan(root=DEFAULT_SOURCE, library=wf.LIBRARY):
    root = Path(root).resolve()
    manifest = root / "pages.jsonl"
    if not manifest.is_file():
        raise ValueError("registered source needs pages.jsonl")
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    works_path = root / "works.json"
    works = json.loads(works_path.read_text(encoding="utf-8-sig")) if works_path.is_file() else []
    work_by_name = {w["work"]: w for w in works}
    known = {str(Path(row.get("file", ""))).casefold() for row in rows}
    # New single-page files can arrive before the human-maintained manifest is refreshed.
    for path in sorted((root / "pages").rglob("*")):
        if path.is_file() and path.suffix.lower() in EXTENSIONS:
            relative = str(path.relative_to(root / "pages"))
            if relative.casefold() not in known:
                rows.append({"file": relative, "work": path.parent.name if path.parent != root / "pages" else "待整理",
                             "summary": path.stem, "tags": [], "metadataStatus": "awaiting_human_tags"})
    # Keep source chapter/page order rather than assuming filenames imply a narrative.
    sequences = {}
    for row in rows:
        sequences.setdefault(row.get("work", ""), []).append({
            "source_id": row.get("id"), "page_type": row.get("pageType", ""),
            "title": row.get("summary", ""), "file": row.get("file", "")})
    result = {"indexed": 0, "unchanged": 0, "errors": [], "source": str(root)}
    seen = set()
    orders = {}
    with database(library) as db:
        for ordinal, row in enumerate(rows):
            work = row.get("work", "")
            orders[work] = orders.get(work, 0) + 1
            name = row.get("file", "")
            src = (root / "pages" / name).resolve()
            if not src.is_relative_to(root / "pages"):
                result["errors"].append({"file": name, "error": "source path escapes pages folder"})
                continue
            try:
                info = image_info(src)
                rid = "a-" + wf.sha([str(root), name])[:24]
                record = {
                    "id": rid, "title": row.get("summary") or Path(name).stem,
                    "kind": "deck" if "总览" in row.get("pageType", "") else "slide",
                    "source_root": str(root), "source_path": str(src), "sha256": wf.file_sha(src),
                    "work": work, "order": orders[work],
                    "page_type": row.get("pageType", ""), "category": row.get("category", ""),
                    "layout": row.get("layout", ""), "colors": row.get("colors", ""),
                    "style": row.get("style") or work_by_name.get(work, {}).get("style", ""), "density": row.get("density", ""),
                    "tags": row.get("tags", []), "deck_tags": row.get("deckTags", []),
                    "structure": row.get("structure", {}),
                    "structure_suggestions": inferred_structure(row),
                    "deck_structure": row.get("deckStructure", {}),
                    "observed_sequence": sequences.get(row.get("work", ""), []),
                    "original_metadata": row, "technical": info,
                    "deck_metadata": work_by_name.get(work, {}),
                    "status": "reference", "parent": None,
                }
                declared = work_by_name.get(work, {}).get("pages", [])
                if name in declared:
                    record["order"] = declared.index(name) + 1
                record["deck_identity_key"] = str(root) + "|" + (row.get("workFolder") or work)
                coding.enrich(db, record, record["deck_identity_key"])
                old = db.execute("SELECT version FROM assets_v3 WHERE id=? AND current=1", (rid,)).fetchone()
                record = _store(db, record)
                seen.add(rid)
                result["unchanged" if old and old[0] == record["version"] else "indexed"] += 1
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                result["errors"].append({"file": name, "error": str(exc)})
        # A removed source entry disappears from current search, not from pinned projects/history.
        for saved in db.execute("SELECT id,payload FROM assets_v3 WHERE current=1").fetchall():
            if json.loads(saved["payload"]).get("source_root") == str(root) and saved["id"] not in seen:
                db.execute("UPDATE assets_v3 SET current=0 WHERE id=?", (saved["id"],))
        db.execute("INSERT OR REPLACE INTO asset_sources_v3 VALUES(?,?)", (str(root), wf.now()))
    return result


def source_roots(library=wf.LIBRARY):
    with database(library) as db:
        return [r[0] for r in db.execute("SELECT root FROM asset_sources_v3 ORDER BY root")]


def get(rid, version=None, library=wf.LIBRARY):
    wf.safe_id(rid)
    with database(library) as db:
        row = db.execute("SELECT payload FROM assets_v3 WHERE id=? AND " +
                         ("version=?" if version else "current=1"),
                         (rid, version) if version else (rid,)).fetchone()
    if not row:
        raise ValueError("asset/version not found; refresh or choose a registered asset")
    return json.loads(row[0])


def archived_ids(library=wf.LIBRARY):
    with database(library) as db:
        return {row[0] for row in db.execute("SELECT id FROM asset_removals_v3")}


def current_records(db, archived=False):
    """Discovery visibility only; version retrieval and pinned files remain intact."""
    rows = db.execute(
        "SELECT a.payload,d.removed_at FROM assets_v3 a "
        "LEFT JOIN asset_removals_v3 d ON d.id=a.id "
        "WHERE a.current=1 AND d.id IS " + ("NOT NULL" if archived else "NULL"))
    return [{**json.loads(row[0]), "archived": bool(row[1]),
             "archived_at": row[1]} for row in rows]


def set_archived(rid, archived, version, library=wf.LIBRARY):
    """Soft-remove the logical asset across refreshes; never delete image bytes."""
    wf.safe_id(rid)
    if not isinstance(archived, bool):
        raise ValueError("archived 必须为布尔值")
    with database(library) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT version FROM assets_v3 WHERE id=? AND current=1", (rid,)).fetchone()
        if not row:
            raise ValueError("素材不存在，请刷新素材库")
        if not version or row[0] != version:
            raise ValueError("素材版本已更新，请刷新后重试；未修改素材")
        if archived:
            db.execute("INSERT OR IGNORE INTO asset_removals_v3 VALUES(?,?,?)", (rid, version, wf.now()))
        else:
            db.execute("DELETE FROM asset_removals_v3 WHERE id=?", (rid,))
        removed = db.execute("SELECT removed_at FROM asset_removals_v3 WHERE id=?", (rid,)).fetchone()
    return {"id": rid, "version": version, "archived": bool(removed),
            "archived_at": removed[0] if removed else None, "inference_performed": False}


def path_for(record, library=wf.LIBRARY):
    obj = Path(library) / "objects" / (record["sha256"] + Path(record["source_path"]).suffix.lower())
    path = obj if obj.is_file() else Path(record["source_path"])
    if not path.is_file() or wf.file_sha(path) != record["sha256"]:
        raise ValueError("asset source changed/missing; refresh index (existing pinned project files remain valid)")
    return path


def pin(record, library=wf.LIBRARY):
    src = path_for(record, library)
    dest = Path(library) / "objects" / (record["sha256"] + src.suffix.lower())
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copyfile(src, dest)
    return dest


def import_image(path, metadata, library=wf.LIBRARY):
    src = Path(path).resolve()
    info = image_info(src)
    wf.reject_secrets(metadata)
    metadata = dict(metadata)
    import image_recipe
    recipe = image_recipe.bundle_to(src, Path(library) / "generation-records")
    if recipe:
        metadata["generation_recipe"] = recipe
    if metadata.get("kind", "illustration") not in KINDS:
        raise ValueError("unsupported asset kind")
    parent = metadata.get("parent")
    if parent:
        parent_record = get(parent["id"], parent.get("version"), library)
        parent = {"id": parent_record["id"], "version": parent_record["version"]}
    content = wf.file_sha(src)
    rid = metadata.get("id") or "a-" + wf.sha([content, metadata.get("title", src.stem)])[:24]
    wf.safe_id(rid)
    record = {
        "id": rid, "title": metadata.get("title") or src.stem, "kind": metadata.get("kind", "illustration"),
        "source_root": "", "source_path": str(src), "sha256": content, "technical": info,
        "status": metadata.get("status", "candidate"), "parent": parent, "work": metadata.get("work", ""),
        "order": metadata.get("order", 0), "tags": metadata.get("tags", []),
        "page_type": metadata.get("page_type", ""), "category": metadata.get("category", ""),
        "colors": metadata.get("colors", ""), "style": metadata.get("style", ""),
        "layout": metadata.get("layout", ""), "density": metadata.get("density", ""),
        "structure": metadata.get("structure", {}), "deck_structure": metadata.get("deck_structure", {}),
        "structure_suggestions": {}, "observed_sequence": [], "original_metadata": metadata,
    }
    with database(library) as db:
        record["deck_identity_key"] = "import|" + (metadata.get("work") or rid)
        coding.enrich(db, record, record["deck_identity_key"])
        record = _store(db, record)
    pin(record, library)
    return record


def favorite(rid, enabled=True, library=wf.LIBRARY):
    get(rid, library=library)
    with database(library) as db:
        if enabled:
            db.execute("INSERT OR IGNORE INTO asset_favorites_v3 VALUES(?)", (rid,))
        else:
            db.execute("DELETE FROM asset_favorites_v3 WHERE id=?", (rid,))
    return {"id": rid, "favorite": bool(enabled)}


def annotate_structure(rid, analysis, library=wf.LIBRARY):
    """Correctable project-independent analysis; never overwrite source author tags."""
    allowed = {"deck_narrative", "suitable_purposes", "chapter_order", "page_roles",
               "relationships", "rationale", "status", "author", "evidence"}
    if not isinstance(analysis, dict) or set(analysis) - allowed:
        raise ValueError("unknown structure-analysis field")
    if not analysis.get("author") or not analysis.get("evidence"):
        raise ValueError("structure analysis needs author and supporting observations")
    if analysis.get("status", "suggested") not in ("suggested", "user_confirmed"):
        raise ValueError("analysis is a suggestion unless explicitly confirmed by the user")
    wf.reject_secrets(analysis)
    record = get(rid, library=library)
    analysis = {"status": "suggested", **analysis}
    with database(library) as db:
        db.execute("INSERT OR REPLACE INTO asset_structure_v3 VALUES(?,?)",
                   (rid, json.dumps(analysis, ensure_ascii=False)))
        record = _store(db, record)
    return record


SEARCH_FIELDS = ("id", "title", "tag", "work", "category", "page_type", "colors", "style",
                 "density", "role", "relation", "layout", "component", "font", "palette", "narrative")
FILTER_FIELDS = ("family", "kind", "category", "work", "page_type", "colors", "style", "density",
                 "role", "relation", "layout", "component", "font", "palette", "ratio", "coding_status")
FAMILY_NAMES = {"pages": "PPT参考", "webpages": "网页设计参考", "branding": "品牌素材",
                "components": "固定组件", "materials": "背景与插图"}


def search_fields(r):
    """Only author-facing content and coded design traits; never serialized metadata/paths."""
    fields = {k: [] for k in SEARCH_FIELDS + FILTER_FIELDS}
    def add(key, values):
        if isinstance(values, (list, tuple)):
            for v in values:
                add(key, v)
        elif isinstance(values, (str, int)) and str(values).strip():
            fields[key].append(str(values).strip())
    def markers(key, values, group):
        for v in values or []:
            if isinstance(v, dict):
                add(key, [v.get("code"), v.get("label") or coding.VOCAB.get(group, {}).get(v.get("code"))])
    for k in ("title", "work", "category", "page_type", "colors", "style", "density", "kind"):
        add(k, r.get(k))
    add("id", [r.get("id"), r.get("page_code"), r.get("deck_code")])
    add("tag", [r.get("tags", []), r.get("deck_tags", [])])
    add("layout", r.get("layout"))
    c = r.get("coding", {})
    markers("role", [c["role"]] if c.get("role") else [], "role")
    for key, vals, group in (
        ("relation", c.get("relations"), "relation"),
        ("layout", c.get("layout", {}).get("types"), "layout"),
        ("component", c.get("components"), "component"),
        ("font", c.get("typography"), "font_style"),
        ("density", [c["density"]] if c.get("density") else [], "density"),
        ("narrative", r.get("deck_coding", {}).get("narrative"), "narrative")):
        markers(key, vals, group)
    # Existing structure labels are searchable, but evidence text and method/status are not.
    for structure in (r.get("structure", {}), r.get("structure_suggestions", {})):
        if isinstance(structure, dict):
            add("role", [structure.get("page_role"), structure.get("page_roles", [])])
            add("relation", structure.get("relationships", []))
            add("narrative", structure.get("deck_narrative"))
    for key in ("component_refs", "typography_refs"):
        add("component" if key == "component_refs" else "font", c.get(key, []))
    add("palette", c.get("palette_ref"))
    for d in c.get("definitions", {}).values():
        # Only verified exact font names and sampled hex are treated as precise properties.
        if d.get("status") != "reviewed":
            continue
        code = d.get("code", "")
        key = "font" if code.startswith("TYP-") else "palette" if code.startswith("PAL-") else "component"
        add(key, [code, d.get("name")])
        if key == "font":
            add(key, d.get("family"))
            for spec in d.get("roles", {}).values():
                add(key, spec.get("family"))
        if key == "palette":
            add("colors", [s.get("hex") for s in d.get("swatches", [])])
    add("family", "pages" if r.get("kind") in ("deck", "slide") else
        "webpages" if r.get("kind") == "webpage" else
        "branding" if r.get("kind") == "brand" else
        "components" if r.get("kind") in ("header", "footer", "navigation", "icon", "decoration") else "materials")
    add("coding_status", c.get("status", "unclassified"))
    ratio = r.get("technical", {}).get("ratio", 1)
    add("ratio", "16:9" if abs(ratio - 16/9) < .03 else "4:3" if abs(ratio - 4/3) < .03 else
        "square" if abs(ratio - 1) < .03 else "portrait" if ratio < 1 else "wide")
    return {k: list(dict.fromkeys(v)) for k, v in fields.items()}


from ppt_read_cache import SQLiteReadIndex
_search_index = SQLiteReadIndex()


def _indexed_search_rows(library, archived):
    def build(db):
        # The repeated observed deck sequence dominates the old payload. It is
        # not searchable content. Full records are still returned for page hits.
        sql = ("SELECT json_remove(a.payload,'$.observed_sequence','$.original_metadata',"
               "'$.deck_metadata'),d.removed_at FROM assets_v3 a "
               "LEFT JOIN asset_removals_v3 d ON d.id=a.id "
               "WHERE a.current=1 AND d.id IS " + ("NOT NULL" if archived else "NULL"))
        indexed = []
        for payload, removed_at in db.execute(sql):
            record = json.loads(payload)
            fields = search_fields(record)
            light = {k: record[k] for k in ("id", "version", "work", "order", "technical") if k in record}
            light.update(archived=bool(removed_at), archived_at=removed_at)
            indexed.append((light, fields))
        facets = {key: sorted({v for _, fields in indexed for v in fields[key]})
                  for key in FILTER_FIELDS}
        favorites = {r[0] for r in db.execute("SELECT id FROM asset_favorites_v3")}
        return indexed, facets, favorites
    return _search_index.get(Path(library) / "index.sqlite3", archived, build)


def search(query="", filters=None, offset=0, limit=36, distinct=False, library=wf.LIBRARY):
    filters = filters or {}
    if set(filters) - set(FILTER_FIELDS) - {"favorite", "alpha", "archived"}:
        raise ValueError("unknown asset-search filter")
    if not isinstance(filters.get("archived", False), bool):
        raise ValueError("archived 必须为布尔值")
    aliases = {"标签": "tag", "标题": "title", "布局": "layout", "关系": "relation",
               "字体": "font", "组件": "component", "色卡": "palette", "编号": "id"}
    tokens = []
    for term in shlex.split(query):
        key, colon, text = term.partition(":")
        if colon and key not in ("http", "https"):
            key = aliases.get(key, key)
            if key not in SEARCH_FIELDS or not text:
                raise ValueError("搜索字段无效；可用 title/tag/id/layout/relation/component/font/palette 等")
            tokens.append((key, text.casefold()))
        else:
            tokens.append((None, term.casefold()))
    with database(library):
        pass  # Retain first-use schema initialization; the cache is strictly read-only.
    indexed, facets, favorites = _indexed_search_rows(library, filters.get("archived", False))
    hits = []
    for source, fields in indexed:
        r = dict(source)  # Never decorate the shared cached index.
        r["favorite"] = r["id"] in favorites
        if any(str(v).casefold() not in [x.casefold() for x in fields[k]]
               for k, v in filters.items() if k in facets and v):
            continue
        if filters.get("favorite") and not r["favorite"]:
            continue
        if filters.get("alpha") and not r["technical"]["alpha"]:
            continue
        score, matches = 0, []
        for key, term in tokens:
            best = None
            is_code = bool(re.fullmatch(r"(?:a-|pg-|dk-|nt-|rl-|ir-|ly-|cp-|ft-|dn-|mt-|cmp-|typ-|pal-)[\w-]+", term))
            for field in ((key,) if key else SEARCH_FIELDS):
                for value in fields[field]:
                    text = value.casefold()
                    exact = text == term
                    if not exact and (is_code or term not in text):
                        continue
                    weight = (100 if exact else 10) + {"id": 30, "title": 20, "tag": 15}.get(field, 0)
                    if best is None or weight > best[0]:
                        best = (weight, field, value)
            if best is None:
                break
            score += best[0]
            matches.append({"field": best[1], "value": best[2]})
        if len(matches) != len(tokens):
            continue
        r["search_matches"] = matches
        r["search_score"] = score
        r["family"] = fields["family"][0]
        r["preview_url"] = f"/api/assets/{r['id']}/preview?version={r['version']}"
        hits.append(r)
    hits.sort(key=lambda r: (-r["search_score"], not r["favorite"], r.get("work", ""), r.get("order", 0), r["id"]))
    if distinct:
        # 每套作品只保留第一张（相同 work 去重），供「只看固定版式」快速浏览
        seen_works = set()
        deduped = []
        for r in hits:
            key = r.get("work") or ("id:" + r["id"])  # 无套系归属的不去重
            if key in seen_works:
                continue
            seen_works.add(key)
            deduped.append(r)
        hits = deduped
    offset, limit = max(0, int(offset)), min(100, max(1, int(limit)))
    has_more = offset + limit < len(hits)
    items = []
    with database(library) as db:
        for hit in hits[offset:offset + limit]:
            row = db.execute("SELECT payload FROM assets_v3 WHERE id=? AND version=?",
                             (hit["id"], hit["version"])).fetchone()
            if row:
                items.append({**json.loads(row[0]), **hit})
    return {"items": items, "total": len(hits), "facets": {k: list(v) for k, v in facets.items()},
            "offset": offset, "limit": limit, "has_more": has_more,
            "next_offset": offset + limit if has_more else None, "inference_performed": False}


def thumbnail(record, library=wf.LIBRARY):
    # Version the alpha preview cache; old convert("RGB") thumbnails had black mattes.
    alpha = record.get("technical", {}).get("alpha", False)
    dest = Path(library) / "previews" / (record["sha256"] + ("-alpha-white-v2" if alpha else "") + ".jpg")
    if not dest.exists():
        src = path_for(record, library)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            if alpha:
                rgba = im.convert("RGBA")
                im = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("RGB")
            else:
                im = im.convert("RGB")
            im.thumbnail((1100, 800), Image.Resampling.LANCZOS)
            im.save(dest, quality=86)
    return dest


def choose(root, p, rid, version=None, usage="structure", library=wf.LIBRARY):
    if usage not in USAGES:
        raise ValueError("unknown asset usage")
    if rid in archived_ids(library):
        raise ValueError("素材已移除；请先在「已移除」中恢复，再加入购物车")
    record = get(rid, version, library)
    src = pin(record, library)
    dest = Path(root).resolve() / "assets/pinned" / (rid + "-" + record["version"][:12] + src.suffix.lower())
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copyfile(src, dest)
    entry = {
        "id": rid, "version": record["version"], "sha256": record["sha256"], "path": str(dest),
        "title": record["title"], "kind": record["kind"], "usage": usage,
        "model_allowed": False, "structure": record.get("structure", {}),
        "structure_suggestions": record.get("structure_suggestions", {}),
        "deck_structure": record.get("deck_structure", {}),
        "observed_sequence": record.get("observed_sequence", []),
        "deck_code": record.get("deck_code"), "page_code": record.get("page_code"),
        "coding": record.get("coding", {}), "deck_coding": record.get("deck_coding", {}),
        "protected_evidence": bool(record.get("original_metadata", {}).get("role") == "evidence"),
    }
    entry.update(source_kind="local", comment="", collected_at=wf.now())
    p["resource_cart"] = [x for x in p.get("resource_cart", []) if x["id"] != rid] + [entry]
    wf.save(root, p)
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=wf.LIBRARY)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("scan"); c.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    c = sub.add_parser("search"); c.add_argument("--query", default="")
    for key in FILTER_FIELDS:
        c.add_argument("--" + key.replace("_", "-"), dest=key)
    c.add_argument("--offset", type=int, default=0); c.add_argument("--limit", type=int, default=36)
    c.add_argument("--archived", action="store_true", help="只检索已移除素材")
    c = sub.add_parser("import"); c.add_argument("--image", required=True); c.add_argument("--metadata", required=True)
    c = sub.add_parser("choose"); c.add_argument("--job", required=True); c.add_argument("--id", required=True)
    c.add_argument("--version"); c.add_argument("--usage", choices=USAGES, default="structure")
    c = sub.add_parser("annotate"); c.add_argument("--id", required=True); c.add_argument("--analysis", required=True)
    for command in ("remove", "restore"):
        c = sub.add_parser(command); c.add_argument("--id", required=True); c.add_argument("--version", required=True)
    args = parser.parse_args()
    try:
        if args.cmd == "scan":
            result = scan(args.source, args.library)
        elif args.cmd == "search":
            result = search(args.query, {**{k: getattr(args, k) for k in FILTER_FIELDS}, "archived": args.archived},
                            args.offset, args.limit, library=args.library)
        elif args.cmd == "import":
            result = import_image(args.image, wf.read(args.metadata), args.library)
        elif args.cmd == "annotate":
            result = annotate_structure(args.id, wf.read(args.analysis), args.library)
        elif args.cmd in ("remove", "restore"):
            result = set_archived(args.id, args.cmd == "remove", args.version, args.library)
        else:
            result = choose(args.job, wf.load(args.job), args.id, args.version, args.usage, args.library)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
