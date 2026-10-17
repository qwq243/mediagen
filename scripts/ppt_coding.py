"""Stable resource identities and reviewable design coding; never invent font names/colors."""
from __future__ import annotations
import argparse
import copy
import json
import re
from pathlib import Path
import ppt_workflow as wf

VOCAB = {
    "narrative": {
        "NT-ARG": "问题—方案—验证—价值", "NT-STORY": "情境—行动—变化—启示",
        "NT-TEACH": "目标—讲解—练习—反馈", "NT-DECIDE": "选项—标准—比较—建议",
        "NT-MECHANISM": "输入—机制—输出—边界", "NT-REPORT": "目标—进展—问题—计划",
        "NT-MIXED": "混合叙事"},
    "role": {
        "RL-COVER": "封面", "RL-AGENDA": "目录", "RL-SECTION": "章节过渡",
        "RL-CONTEXT": "背景情境", "RL-PROBLEM": "提出问题", "RL-CLAIM": "核心主张",
        "RL-SOLUTION": "解决方案", "RL-MECHANISM": "机制原理", "RL-PROCESS": "实施过程",
        "RL-EVIDENCE": "证据成效", "RL-COMPARE": "比较判断", "RL-DEMO": "承接演示",
        "RL-TEAM": "团队能力", "RL-MODEL": "商业或服务模式", "RL-PLAN": "未来计划",
        "RL-SUMMARY": "总结反思", "RL-CLOSING": "尾页", "RL-REFERENCE": "参考资料",
        "RL-EXPLORATION": "探索提问", "RL-ASSET": "组件或骨架参考"},
    "relation": {
        "IR-PARALLEL": "并列", "IR-COMPARE": "对比", "IR-CAUSE": "因果", "IR-PROGRESS": "递进",
        "IR-FLOW": "流程", "IR-HIERARCHY": "层级", "IR-PART": "总分", "IR-CYCLE": "循环",
        "IR-TIMELINE": "时间演进", "IR-NETWORK": "网络关系", "IR-SPATIAL": "空间位置"},
    "layout": {
        "LY-HERO": "单一主视觉", "LY-SPLIT-2": "双栏", "LY-COLS-3": "三栏", "LY-QUADRANT": "四象限",
        "LY-STACK": "上下分区", "LY-GRID": "网格矩阵", "LY-RADIAL": "中央放射", "LY-RING": "环形",
        "LY-AXIS": "时间轴", "LY-STAIRS": "阶梯", "LY-PYRAMID": "金字塔", "LY-DASHBOARD": "数据看板",
        "LY-FULLBLEED": "满版图像", "LY-MIXED": "复合布局"},
    "component": {
        "CP-TOPBAR": "顶部标题栏", "CP-NAV": "章节导航", "CP-PROGRESS": "章节进度",
        "CP-FOOTER": "页脚", "CP-PAGENUM": "页码", "CP-BRAND": "品牌标识",
        "CP-RIBBON": "飘带装饰", "CP-CARD": "信息卡片", "CP-QUOTE": "引言/结论条",
        "CP-ICON": "图标家族", "CP-BACKGROUND": "背景", "CP-ILLUSTRATION": "插图"},
    "font_style": {
        "FT-SANS": "无衬线黑体", "FT-SERIF": "衬线宋体", "FT-BRUSH": "毛笔书法",
        "FT-DISPLAY": "艺术展示字", "FT-HAND": "手写字", "FT-GEOMETRIC": "几何数字",
        "FT-UNKNOWN": "字型待识别"},
    "density": {"DN-LOW": "简洁讲述", "DN-MEDIUM": "讲读兼顾", "DN-HIGH": "高信息阅读"},
    "material": {"MT-FLAT": "平面", "MT-PAPER": "纸张", "MT-GLASS": "玻璃",
                 "MT-INK": "水墨", "MT-WATERCOLOR": "水彩", "MT-METAL": "金属", "MT-PHOTO": "实景"},
}
STATUSES = ("unclassified", "suggested", "reviewed")


def tables(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS coding_ids_v1(
        serial INTEGER PRIMARY KEY AUTOINCREMENT, family TEXT, source_key TEXT,
        UNIQUE(family,source_key));
      CREATE TABLE IF NOT EXISTS coding_pages_v1(asset_id TEXT PRIMARY KEY,payload TEXT);
      CREATE TABLE IF NOT EXISTS coding_decks_v1(code TEXT PRIMARY KEY,payload TEXT);
      CREATE TABLE IF NOT EXISTS coding_definitions_v1(code TEXT PRIMARY KEY,payload TEXT);
    """)


def identity(db, family, key):
    row = db.execute("SELECT serial FROM coding_ids_v1 WHERE family=? AND source_key=?", (family, key)).fetchone()
    if not row:
        db.execute("INSERT OR IGNORE INTO coding_ids_v1(family,source_key) VALUES(?,?)", (family, key))
        row = db.execute("SELECT serial FROM coding_ids_v1 WHERE family=? AND source_key=?", (family, key)).fetchone()
    value = row[0]
    return f"{family}-{value:06d}"


def marker(group, code, **extra):
    return {"code": code, "label": VOCAB[group][code], "status": "suggested", **extra}


def suggest(record):
    """Only explicit source labels, clearly separated from human-reviewed coding."""
    page_type = record.get("page_type", "")
    layout = record.get("layout", "")
    text = " ".join((page_type, layout, record.get("colors", ""), record.get("style", ""),
                     " ".join(record.get("tags", []))))
    role = None
    for code, words in [
        ("RL-ASSET", ("组件库", "骨架")), ("RL-SECTION", ("章节", "过渡")),
        ("RL-COVER", ("封面",)), ("RL-CLOSING", ("尾页",)), ("RL-AGENDA", ("目录",)),
        ("RL-PROBLEM", ("痛点", "问题", "需求")), ("RL-CONTEXT", ("背景", "政策", "情境")),
        ("RL-TEAM", ("团队", "成员", "专家", "负责人")), ("RL-PLAN", ("计划", "规划", "展望")),
        ("RL-COMPARE", ("对比", "竞品")), ("RL-MECHANISM", ("技术", "机制", "架构", "原理")),
        ("RL-MODEL", ("模式", "财务", "融资")), ("RL-EVIDENCE", ("成果", "成效", "验证", "数据", "案例", "荣誉")),
        ("RL-SOLUTION", ("方案", "策略", "举措")), ("RL-PROCESS", ("过程", "实施", "历程")),
        ("RL-SUMMARY", ("总结", "反思"))]:
        if any(w in page_type for w in words):
            role = marker("role", code, evidence=f"原页面类型：{page_type}")
            break
    relations = [marker("relation", code) for code, words in {
        "IR-COMPARE": ("对比", "对照"), "IR-PARALLEL": ("并列",),
        "IR-FLOW": ("流程", "步骤"), "IR-PART": ("总分", "放射"),
        "IR-TIMELINE": ("时间轴", "历程"), "IR-CYCLE": ("循环",),
        "IR-HIERARCHY": ("层级", "分层"), "IR-CAUSE": ("因果",), "IR-PROGRESS": ("递进",),
    }.items() if any(w in text for w in words)]
    layouts = [marker("layout", code) for code, words in {
        "LY-SPLIT-2": ("双栏", "左字右图", "左图右字"), "LY-COLS-3": ("三栏",),
        "LY-QUADRANT": ("四象限",), "LY-STACK": ("上下",), "LY-GRID": ("网格", "矩阵"),
        "LY-RADIAL": ("放射",), "LY-RING": ("环形",), "LY-AXIS": ("时间轴",),
        "LY-STAIRS": ("阶梯",), "LY-PYRAMID": ("金字塔",), "LY-FULLBLEED": ("全图", "满版"),
    }.items() if any(w in layout for w in words)]
    components = [marker("component", code, bbox=None) for code, words in {
        "CP-TOPBAR": ("顶栏", "页眉", "顶部标题", "顶标题带", "顶标题"),
        "CP-NAV": ("导航",), "CP-PROGRESS": ("进度",), "CP-FOOTER": ("页脚", "脚线"),
        "CP-PAGENUM": ("页码",), "CP-BRAND": ("徽标", "标识", "logo", "Logo"),
        "CP-RIBBON": ("飘带",), "CP-CARD": ("卡片", "图卡", "胶囊"),
    }.items() if any(w in layout for w in words)]
    fonts = [marker("font_style", code, family=None, role="display", identification="style_only")
             for code, words in {"FT-BRUSH": ("书法", "毛笔"), "FT-SERIF": ("宋体", "衬线"),
                                 "FT-SANS": ("黑体",), "FT-DISPLAY": ("艺术字",),
                                 "FT-HAND": ("手写",)}.items() if any(w in text for w in words)]
    return {"schema_version": 1, "status": "suggested", "role": role, "relations": relations,
            "layout": {"types": layouts, "description": layout, "regions": []},
            "components": components, "typography": fonts,
            "palette": {"description": record.get("colors", ""), "swatches": [], "status": "unclassified"},
            "density": None, "component_refs": [], "typography_refs": [], "palette_ref": None,
            "evidence": ["来自已有人工文字标签；未据此认定精确字体、色值或区域坐标。"]}


def enrich(db, record, deck_key):
    record["deck_code"] = identity(db, "DK", deck_key)
    record["page_code"] = identity(db, "PG", record["id"])
    record["coding"] = suggest(record)
    saved = db.execute("SELECT payload FROM coding_pages_v1 WHERE asset_id=?", (record["id"],)).fetchone()
    if saved:
        manual = json.loads(saved[0])
        if manual.get("image_sha256") == record["sha256"]:
            record["coding"] = {k: v for k, v in manual.items() if k not in (
                "asset_id", "asset_version", "page_code", "deck_code", "image_sha256",
                "source_file", "page_order", "title", "definitions")}
            definitions = {}
            refs = manual.get("component_refs", []) + manual.get("typography_refs", []) + [manual.get("palette_ref")]
            for ref in filter(None, refs):
                definition = db.execute("SELECT payload FROM coding_definitions_v1 WHERE code=?", (ref,)).fetchone()
                if definition:
                    definitions[ref] = json.loads(definition[0])
            record["coding"]["definitions"] = definitions
        else:
            record["coding"]["previous_coding_stale"] = True
    deck = db.execute("SELECT payload FROM coding_decks_v1 WHERE code=?", (record["deck_code"],)).fetchone()
    record["deck_coding"] = json.loads(deck[0]) if deck else {"status": "unclassified", "narrative": [], "chapters": []}
    return record


def validate_marker(value, group):
    if value is None:
        return
    if not isinstance(value, dict) or value.get("code") not in VOCAB[group]:
        raise ValueError(f"unknown {group} code")
    if value.get("status", "suggested") not in STATUSES:
        raise ValueError("unknown coding status")


def bbox(value):
    import math
    if not isinstance(value, list) or len(value) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError("bbox must be [x,y,w,h] normalized")
    if min(value) < 0 or min(value[2:]) <= 0 or value[0] + value[2] > 1.000001 or value[1] + value[3] > 1.000001:
        raise ValueError("bbox outside image")


def not_applicable(row, field):
    return row.get("applicability", {}).get(field, {}).get("state") == "not_applicable"


def validate_applicability(row):
    fields = {"relations": row.get("relations"), "typography": row.get("typography") or row.get("typography_refs"),
              "density": row.get("density"), "material": row.get("material")}
    value = row.get("applicability", {})
    if not isinstance(value, dict):
        raise ValueError("applicability must describe fields")
    for key, item in value.items():
        if key not in fields or not isinstance(item, dict) or item.get("state") not in ("applicable", "not_applicable") or not str(item.get("reason", "")).strip():
            raise ValueError("applicability needs a known field, state and reason")
        if item["state"] == "not_applicable" and fields[key]:
            raise ValueError("not_applicable cannot hide existing coded values")


def validate_bundle(bundle, code, known):
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1 or not bundle.get("name"):
        raise ValueError("bundle needs schema_version and name")
    members, links = bundle.get("members"), bundle.get("links")
    if not isinstance(members, list) or not members or not isinstance(links, list):
        raise ValueError("bundle needs members and links")
    seen, main, resource = set(), set(), set()
    for item in members:
        if not isinstance(item, dict):
            raise ValueError("bundle member must be a record")
        rid = item.get("asset_id")
        r = known.get(rid, {})
        if rid in seen or not r or r.get("deck_code") != code or item.get("page_code") != r.get("page_code") or item.get("image_sha256") != r.get("sha256"):
            raise ValueError("bundle member identity/image/deck mismatch")
        if item.get("role") not in ("main", "resource"):
            raise ValueError("bundle member role must be main or resource")
        seen.add(rid)
        (main if item["role"] == "main" else resource).add(rid)
    touched, pairs = set(), set()
    for link in links:
        if not isinstance(link, dict):
            raise ValueError("bundle link must be a record")
        a, b = link.get("source"), link.get("target")
        key = (a, b, link.get("relation"))
        if a not in main or b not in resource or key in pairs or link.get("relation") not in ("background", "icon", "brand", "component") or not link.get("evidence"):
            raise ValueError("bundle link needs main-to-resource endpoints, relation and evidence")
        if link.get("source_bbox") is not None:
            bbox(link["source_bbox"])
        pairs.add(key)
        touched.update((a, b))
    if not main or not resource or touched != seen:
        raise ValueError("bundle must connect every main page and resource; no orphans")


def bundle_context(record, library):
    """Resolve a saved bundle by image identity, never silently follow changed bytes.

    Store hashes rather than mutually recursive metadata versions. Resolve one
    exact image snapshot per member at read time, including archived/history.
    """
    import ppt_assets as assets
    bundle = record.get("deck_coding", {}).get("reference_bundle")
    if not bundle:
        return None
    members = bundle["members"]
    ids = [m["asset_id"] for m in members]
    with assets.database(library) as db:
        rows = db.execute("SELECT payload FROM assets_v3 WHERE id IN (" +
                          ",".join("?" for _ in ids) + ") ORDER BY current DESC,rowid DESC", ids)
        snapshots = [json.loads(x[0]) for x in rows]
        archived = {x[0] for x in db.execute("SELECT id FROM asset_removals_v3")}
    resolved = []
    for member in members:
        r = next((x for x in snapshots if x["id"] == member["asset_id"]
                  and x["sha256"] == member["image_sha256"]
                  and x.get("page_code") == member["page_code"]), None)
        resolved.append({**member, "id": member["asset_id"], "available": bool(r),
                         "version": r["version"] if r else None,
                         "title": r["title"] if r else member["page_code"],
                         "kind": r["kind"] if r else None,
                         "archived": member["asset_id"] in archived})
    related = []
    for member in resolved:
        matches = [l for l in bundle["links"] if {record["id"], member["id"]} == {l["source"], l["target"]}]
        if matches:
            related.append({**member, "relations": list(dict.fromkeys(l["relation"] for l in matches)),
                            "evidence": [l["evidence"] for l in matches]})
    return {"name": bundle["name"], "members": resolved, "related": related,
            "main_count": sum(m["role"] == "main" for m in members),
            "resource_count": sum(m["role"] == "resource" for m in members),
            "current_role": next((m["role"] for m in members if m["asset_id"] == record["id"]), None),
            "usage_boundary": bundle.get("usage_boundary", "")}


def validate_package(package, records):
    if package.get("schema_version") != 1:
        raise ValueError("coding schema_version must be 1")
    wf.reject_secrets(package)
    for key in ("definitions", "decks", "pages"):
        if not isinstance(package.get(key, []), list) or any(not isinstance(x, dict) for x in package.get(key, [])):
            raise ValueError(f"{key} must be a list of records")
    definitions = package.get("definitions", [])
    defs = {}
    for item in definitions:
        code = item.get("code", "")
        if not re.fullmatch(r"(CMP|TYP|PAL)-[A-Z0-9-]{3,60}", code) or code in defs:
            raise ValueError("invalid/duplicate component, typography or palette instance code")
        if not item.get("name"):
            raise ValueError("definition needs a human-readable name")
        for sw in item.get("swatches", []):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", sw.get("hex", "")):
                raise ValueError("confirmed color swatches need real 6-digit hex values")
        if item.get("bbox") is not None:
            bbox(item["bbox"])
        if item.get("family") and item.get("identification") not in ("file_metadata", "author_supplied", "verified"):
            raise ValueError("exact font family needs verified identification, not visual guessing")
        for role, spec in item.get("roles", {}).items() if isinstance(item.get("roles"), dict) else []:
            if not isinstance(spec, dict):
                raise ValueError("typography role must describe a font")
            if spec.get("family") and spec.get("identification") not in ("file_metadata", "author_supplied", "verified"):
                raise ValueError("role font family needs verified identification")
        if item.get("status") == "reviewed":
            if not item.get("reviewer") or not item.get("evidence"):
                raise ValueError("reviewed definition needs reviewer and observations")
            if code.startswith("PAL-") and not item.get("swatches"):
                raise ValueError("reviewed palette needs sampled swatches")
            if code.startswith("CMP-") and not all(item.get(k) for k in ("source_page_code", "image_sha256", "bbox", "type_code")):
                raise ValueError("reviewed component needs exact source image and region")
            if code.startswith("CMP-") and not any(r.get("page_code") == item["source_page_code"]
                                                  and r["sha256"] == item["image_sha256"] for r in records):
                raise ValueError("component source image/version is not in this library")
        if item.get("style_code"):
            validate_marker({"code": item["style_code"]}, "font_style")
        if item.get("type_code"):
            validate_marker({"code": item["type_code"]}, "component")
        defs[code] = item
    seen = set()
    known = {r["id"]: r for r in records}
    for row in package.get("pages", []):
        rid = row.get("asset_id")
        if rid not in known or rid in seen:
            raise ValueError("unknown/duplicate asset_id")
        seen.add(rid)
        original = known[rid]
        for key in ("page_code", "deck_code"):
            if row.get(key) != original[key]:
                raise ValueError("identity codes cannot be changed or assigned to another image")
        if row.get("image_sha256") != original["sha256"]:
            raise ValueError("image changed since coding export")
        if row.get("asset_version") != original["version"]:
            raise ValueError("asset metadata changed since coding export; re-export before editing")
        if row.get("page_order") != original.get("order"):
            raise ValueError("page_order follows the original source; correct source order separately")
        if row.get("status") not in STATUSES:
            raise ValueError("coding status required")
        if row["status"] == "reviewed" and (not row.get("reviewer") or not row.get("evidence")):
            raise ValueError("reviewed coding needs reviewer and observations")
        validate_applicability(row)
        validate_marker(row.get("role"), "role")
        validate_marker(row.get("density"), "density")
        validate_marker(row.get("material"), "material")
        for r in row.get("relations", []):
            validate_marker(r, "relation")
        for l in row.get("layout", {}).get("types", []):
            validate_marker(l, "layout")
        for component in row.get("components", []):
            validate_marker(component, "component")
            if component.get("bbox") is not None:
                bbox(component["bbox"])
        for typo in row.get("typography", []):
            validate_marker(typo, "font_style")
            if typo.get("family") and typo.get("identification") not in ("file_metadata", "author_supplied", "verified"):
                raise ValueError("exact font family needs verified identification")
        for sw in row.get("palette", {}).get("swatches", []):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", sw.get("hex", "")):
                raise ValueError("invalid page color")
        for z in row.get("layout", {}).get("regions", []):
            bbox(z.get("bbox"))
        for ref in row.get("component_refs", []) + row.get("typography_refs", []) + list(filter(None, [row.get("palette_ref")])):
            if ref not in defs:
                raise ValueError(f"missing definition for {ref}")
    decks_seen = set()
    for deck in package.get("decks", []):
        code = deck.get("deck_code")
        if code in decks_seen or code not in {r["deck_code"] for r in records}:
            raise ValueError("unknown/duplicate deck code")
        decks_seen.add(code)
        if deck.get("status") not in STATUSES:
            raise ValueError("deck coding status required")
        if deck["status"] == "reviewed" and (not deck.get("reviewer") or not deck.get("evidence")):
            raise ValueError("reviewed deck needs reviewer and observations")
        for nt in deck.get("narrative", []):
            validate_marker(nt, "narrative")
        for chapter in deck.get("chapters", []):
            for pc in chapter.get("page_codes", []):
                if not any(r["page_code"] == pc and r["deck_code"] == code for r in records):
                    raise ValueError("chapter references a page outside this deck")
        if deck.get("reference_bundle") is not None:
            validate_bundle(deck["reference_bundle"], code, known)
    return package


def export_package(library, dest):
    import ppt_assets as assets
    with assets.database(library) as db:
        records = [json.loads(r[0]) for r in db.execute("SELECT payload FROM assets_v3 WHERE current=1")]
    decks = {}
    pages = []
    for r in records:
        if not r.get("page_code"):
            continue
        decks.setdefault(r["deck_code"], {**r.get("deck_coding", {}), "deck_code": r["deck_code"], "name": r.get("work"),
            "purpose": r.get("deck_coding", {}).get("purpose", r.get("category", "")),
            "source_description": r.get("deck_metadata", {}).get("deckIntro", "")})
        pages.append({**copy.deepcopy(r["coding"]), "asset_id": r["id"], "page_code": r["page_code"],
            "deck_code": r["deck_code"], "image_sha256": r["sha256"], "asset_version": r["version"],
            "source_file": r["source_path"],
            "page_order": r.get("order"), "title": r["title"], "reviewer": r["coding"].get("reviewer", "")})
    package = {"schema_version": 1, "exported_at": wf.now(), "definitions": [],
               "decks": list(decks.values()), "pages": pages}
    # Include existing definitions when exporting for another correction round.
    with assets.database(library) as db:
        package["definitions"] = [json.loads(x[0]) for x in db.execute("SELECT payload FROM coding_definitions_v1")]
    wf.write(dest, package)
    return {"path": str(dest), "pages": len(pages), "decks": len(decks)}


def import_package(library, package, execute=False):
    import ppt_assets as assets
    with assets.database(library) as db:
        records = [json.loads(r[0]) for r in db.execute("SELECT payload FROM assets_v3 WHERE current=1")]
        validate_package(package, records)
        if execute:
            for item in package.get("definitions", []):
                db.execute("INSERT OR REPLACE INTO coding_definitions_v1 VALUES(?,?)",
                           (item["code"], json.dumps(item, ensure_ascii=False)))
            for deck in package.get("decks", []):
                db.execute("INSERT OR REPLACE INTO coding_decks_v1 VALUES(?,?)",
                           (deck["deck_code"], json.dumps(deck, ensure_ascii=False)))
            for row in package.get("pages", []):
                db.execute("INSERT OR REPLACE INTO coding_pages_v1 VALUES(?,?)",
                           (row["asset_id"], json.dumps(row, ensure_ascii=False)))
            for r in records:
                enrich(db, r, r.get("deck_identity_key") or r["source_root"] + "|" + r.get("work", ""))
                assets._store(db, r)
    return {"valid": True, "applied": bool(execute), "pages": len(package.get("pages", []))}


def coverage(library):
    import ppt_assets as assets
    with assets.database(library) as db:
        rs = assets.current_records(db)
    return {"pages": len(rs), "decks": len({r.get("deck_code", r.get("work")) for r in rs}),
            "identified": sum(bool(r.get("page_code")) for r in rs),
            "reviewed": sum(r.get("coding", {}).get("status") == "reviewed" for r in rs),
            "missing_exact_palette": sum(not r.get("coding", {}).get("palette_ref") for r in rs),
            "missing_typography": sum(not r.get("coding", {}).get("typography_refs")
                                      and not not_applicable(r.get("coding", {}), "typography") for r in rs),
            "vocabulary": VOCAB}


def examples(library, group="layout", code=None, limit=3):
    """The same real-image examples for the browser and Agent; no invented diagrams."""
    import ppt_assets as assets
    if group not in VOCAB or (code and code not in VOCAB[group]):
        raise ValueError("unknown coding group/code")
    limit = max(1, min(6, int(limit)))
    with assets.database(library) as db:
        rows = assets.current_records(db)
    result = {key: {"code": key, "label": label, "examples": [], "matches": 0}
              for key, label in VOCAB[group].items() if not code or key == code}
    for r in rows:
        c = r.get("coding", {})
        fields = {"narrative": r.get("deck_coding", {}).get("narrative", []),
                  "role": [c.get("role")], "relation": c.get("relations", []),
                  "layout": c.get("layout", {}).get("types", []),
                  "component": c.get("components", []), "font_style": c.get("typography", []),
                  "density": [c.get("density")], "material": [c.get("material")]}
        for mark in fields[group]:
            if not isinstance(mark, dict) or mark.get("code") not in result:
                continue
            entry = result[mark["code"]]
            entry["examples"].append({
                "id": r["id"], "version": r["version"], "sha256": r["sha256"],
                "page_code": r.get("page_code"), "deck_code": r.get("deck_code"),
                "title": r["title"], "path": str(assets.path_for(r, library)),
                "status": mark.get("status", "suggested"),
                "evidence": mark.get("evidence") or c.get("evidence", []),
                "bbox": mark.get("bbox"),
                "preview_url": f"/api/assets/{r['id']}/preview?version={r['version']}"})
    for entry in result.values():
        matches = sorted(entry["examples"], key=lambda r: (r["status"] != "reviewed", r["page_code"] or r["id"]))
        entry["matches"] = len(matches)
        # Prefer different decks, but never change a recorded status.
        selected, decks = [], set()
        for row in matches:
            if row["deck_code"] not in decks:
                selected.append(row); decks.add(row["deck_code"])
        selected += [r for r in matches if r not in selected]
        entry["examples"] = selected[:limit]
    return {"group": group, "items": list(result.values()),
            "policy": "标签图例不等于人工复核；AI可据原图核验，不得继承参考页事实。"}


def sync(library):
    """One-time additive backfill; source images and historical asset versions stay unchanged."""
    import ppt_assets as assets
    count = 0
    with assets.database(library) as db:
        records = [json.loads(r[0]) for r in db.execute("SELECT payload FROM assets_v3 WHERE current=1")]
        for r in records:
            if r.get("page_code"):
                continue
            r["deck_identity_key"] = (r.get("source_root", "") + "|" + r.get("work", "")
                if r.get("source_root") else "import|" + (r.get("work") or r["id"]))
            enrich(db, r, r["deck_identity_key"])
            assets._store(db, r)
            count += 1
    return {"backfilled": count}


def prompt_constraints(selection):
    """Only adopted, reviewed design facts. Never source claims, title text, or loose guesses."""
    result = []
    for item in selection:
        c = item.get("coding", {})
        if c.get("status") != "reviewed":
            continue
        entry = {"asset_id": item["id"], "page_code": item.get("page_code"), "usage": item["usage"]}
        if item["usage"] in ("structure", "layout"):
            entry["relations"] = [v["code"] for v in c.get("relations", []) if v.get("status") == "reviewed"]
            entry["layout_types"] = [v["code"] for v in c.get("layout", {}).get("types", []) if v.get("status") == "reviewed"]
        if item["usage"] in ("style", "layout", "material"):
            entry["design_definitions"] = [{k: v for k, v in d.items() if k in (
                "code", "type_code", "bbox", "style_code", "family", "roles", "swatches",
                "appearance", "fixed", "variable_fields", "keep_clear")}
                for d in c.get("definitions", {}).values() if d.get("status") == "reviewed"]
        result.append(entry)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library", type=Path, default=wf.LIBRARY)
    sp = ap.add_subparsers(dest="command", required=True)
    s = sp.add_parser("export"); s.add_argument("--out", type=Path, required=True)
    s = sp.add_parser("import"); s.add_argument("--file", type=Path, required=True); s.add_argument("--execute", action="store_true")
    sp.add_parser("coverage")
    s = sp.add_parser("examples")
    s.add_argument("--group", default="layout", choices=VOCAB)
    s.add_argument("--code")
    args = ap.parse_args()
    result = examples(args.library, args.group, args.code) if args.command == "examples" else (
        export_package(args.library, args.out) if args.command == "export" else (
        import_package(args.library, wf.read(args.file), args.execute) if args.command == "import" else coverage(args.library))
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
