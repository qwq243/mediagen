"""Version-bound PPT design knowledge. Candidate files never overwrite the legacy index.

No image calls; an independent visual receipt is required for reviewed status.
The immutable candidate hash, not just the source image hash, binds a review.
"""
import argparse
import copy
import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from collections import defaultdict
from pathlib import Path

from ppt_coding import VOCAB

VERSION = "ppt-atoms/1.0"
STATES = ["measured", "estimated", "verified", "unknown", "not_applicable"]
KINDS = ["background", "title", "text", "card", "icon", "image", "chart", "table",
         "brand", "navigation", "page_number", "arrow", "decoration", "contamination"]
RELATIONS = ["contains", "aligns", "equal_spacing", "connects", "precedes",
             "parallel", "causes", "hierarchy", "unknown"]
PERMISSIONS = ["approved", "denied", "unknown"]
TYPE_UNITS = {"color": None, "dimension": "px", "ratio": "ratio", "angle": "deg",
              "fontFamily": None, "fontWeight": None, "text": None, "enum": None,
              "number": None, "shadow": None, "gradient": None}


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def value(v=None, type="text", status="unknown", evidence="未提供或未能可靠测量", unit=None):
    return {"value": v, "type": type, "unit": TYPE_UNITS.get(type) if unit is None else unit,
            "status": status, "evidence": evidence}


def valid_box(box):
    return (isinstance(box, list) and len(box) == 4 and
            all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in box) and
            box[0] >= 0 and box[1] >= 0 and box[2] > 0 and box[3] > 0 and
            box[0] + box[2] <= 1.000001 and box[1] + box[3] <= 1.000001)


def content_coordinates(box, content_box):
    """No crop is performed. Map original normalized coordinates into slide content coordinates."""
    x, y, w, h = content_box
    return [(box[0] - x) / w, (box[1] - y) / h, box[2] / w, box[3] / h]


def element(id, kind, label, bbox, parent=None, region="body"):
    return {"id": id, "kind": kind, "label": label, "parent_id": parent,
            "region_id": region, "bbox": bbox, "geometry_status": "estimated",
            "observed": {"text": value(), "font_family": value(type="fontFamily"),
                         "font_class": value(type="enum"), "font_weight": value(type="fontWeight"),
                         "glyph_height": value(type="dimension"), "rotation": value(type="angle"),
                         "color": value(type="color"), "opacity": value(type="ratio"),
                         "line_height": value(type="ratio"), "letter_spacing": value(type="dimension"),
                         "border_radius": value(type="dimension"), "shadow": value(type="shadow"),
                         "z_index": value(type="number")},
            "protection": {"identity": kind in ("brand", "image"), "do_not_redraw": kind in ("brand", "image", "chart", "table")},
            "reuse": ["structure"] if kind != "contamination" else [],
            "evidence": "人工视觉观察；边界为估计，需原尺寸复核"}


def empty_annotation(record):
    t = record["technical"]
    return {"schema_version": VERSION, "asset_id": record["id"], "deck_id": record["deck_code"],
            "page_id": record["page_code"],
            "source": {"version": record["version"], "sha256": record["sha256"],
                       "width": t["width"], "height": t["height"], "content_box": [0, 0, 1, 1],
                       "content_box_status": "estimated", "alpha": bool(t.get("alpha")),
                       "permissions": {"reuse": "unknown", "model_upload": "unknown"},
                       "original_tags": record.get("tags", [])},
            "deck": {"title": record.get("work", ""), "context": [], "styles": [],
                     "original_completeness": "unknown", "source_order": record.get("order"),
                     "narrative_order": None},
            "page": {"title": record.get("title", ""), "role": "RL-EXPLORATION",
                     "relations": [], "layout": [], "density": "DN-MEDIUM",
                     "key_message": value(), "reading_order": []},
            "regions": [{"id": "body", "role": "content", "bbox": [0, 0, 1, 1]}],
            "elements": [], "relations": [], "definitions": {"components": [], "typography": [], "palette": []},
            "review": {"status": "suggested", "annotator": "Astra-visual-pass1", "independent_review": None},
            "quality": {"image": {"status": "pending", "issues": []},
                        "annotation": {"status": "partial", "completeness": None},
                        "suitability": ["structure_reference"], "rights": "unknown"},
            "coverage": {"level": "inventory", "complete": False,
                         "missing": ["逐元素精标与独立原尺寸复核"]},
            "unknowns": ["原生字体文件与字号未知", "来源使用及模型上传授权未知"],
            "issues": [], "proposed_terms": []}


def taxonomy():
    aliases = {"FT-BRUSH": ["书法", "毛笔", "毛笔标题", "书法标题"],
               "FT-SANS": ["黑体", "无衬线"], "LY-COLS-3": ["三栏", "三列"],
               "CP-NAV": ["顶部章节导航", "章节导航", "顶部导航"],
               "RL-COVER": ["封面"], "RL-CONTEXT": ["研究背景", "项目背景"],
               "IR-FLOW": ["流程", "路径"], "IR-CYCLE": ["循环", "闭环"],
               "IR-HIERARCHY": ["层级", "上下级"], "LY-STACK": ["纵向堆叠"]}
    terms = []
    for family, entries in VOCAB.items():
        for code, label in entries.items():
            terms.append({"id": code, "prefLabel": label, "altLabel": aliases.get(code, []),
                          "broader": [family], "related": [], "family": family})
    for label, alt, family in [
        ("蓝白医疗", ["医疗蓝白", "蓝色医疗风"], "style"),
        ("深绿生态", ["绿色生态风", "生态科技"], "style"),
        ("红金国风", ["红金非遗", "非遗国风"], "style"),
        ("蓝白学术", ["学术汇报", "科研蓝白"], "style"),
        ("蓝白商务", ["商务蓝白", "工作汇报"], "style"),
    ]:
        terms.append({"id": label, "prefLabel": label, "altLabel": alt,
                      "broader": [family], "related": [], "family": family})
    families = {"role": "页面职责", "layout": "几何布局", "relation": "信息关系", "font_style": "字型类别",
                "style": "视觉风格", "component": "固定组件", "density": "信息密度",
                "material": "视觉材质", "narrative": "叙事结构"}
    for family, label in families.items():
        terms.append({"id": family, "prefLabel": label, "altLabel": [], "broader": [], "related": [], "family": "category"})
    related = {"RL-MECHANISM": ["IR-FLOW", "IR-HIERARCHY"], "CP-NAV": ["CP-PROGRESS"],
               "FT-BRUSH": ["MT-INK"], "LY-COLS-3": ["IR-PARALLEL"]}
    for term in terms:
        term["related"] = related.get(term["id"], [])
    return {"version": VERSION, "terms": terms, "new_terms_policy": "candidate_only",
            "related_policy": "suggestion_only_not_exact_match"}


def schema():
    box = {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "number", "minimum": 0, "maximum": 1}}
    strings = {"type": "array", "items": {"type": "string"}}
    typed = {"type": "object", "required": ["type", "value", "unit", "status", "evidence"],
             "additionalProperties": False,
             "properties": {"type": {"enum": list(TYPE_UNITS)}, "value": {},
                            "unit": {"enum": [None, "px", "ratio", "deg"]},
                            "status": {"enum": STATES}, "evidence": {"type": "string", "minLength": 1}}}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:mediagen:ppt-atoms:1",
            "type": "object", "additionalProperties": False,
            "required": ["schema_version", "asset_id", "deck_id", "page_id", "source", "deck", "page", "regions",
                         "elements", "relations", "definitions", "review", "quality", "coverage", "unknowns", "issues", "proposed_terms"],
            "properties": {
                "schema_version": {"const": VERSION}, "asset_id": {"type": "string", "pattern": "^a-[\\w-]+$"},
                "deck_id": {"type": "string", "pattern": "^DK-\\d+$"}, "page_id": {"type": "string", "pattern": "^PG-\\d+$"},
                "source": {"type": "object", "required": ["version", "sha256", "width", "height", "content_box", "permissions"],
                           "properties": {"sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                                          "version": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                                          "width": {"type": "integer", "minimum": 1}, "height": {"type": "integer", "minimum": 1},
                                          "content_box": box,
                                          "permissions": {"type": "object", "required": ["reuse", "model_upload"],
                                                          "properties": {k: {"enum": PERMISSIONS} for k in ["reuse", "model_upload"]}}}},
                "deck": {"type": "object", "required": ["title", "context", "styles", "original_completeness"],
                         "properties": {"title": {"type": "string"}, "context": strings, "styles": strings,
                                        "source_order": {"type": ["integer", "null"]},
                                        "narrative_order": {"type": ["integer", "null"]},
                                        "original_completeness": {"enum": ["complete", "partial", "unknown"]}}},
                "page": {"type": "object", "required": ["title", "role", "relations", "layout", "density", "reading_order"],
                         "properties": {"title": {"type": "string"}, "role": {"enum": list(VOCAB["role"])},
                            "relations": {"type": "array", "items": {"enum": list(VOCAB["relation"])}},
                            "layout": {"type": "array", "items": {"enum": list(VOCAB["layout"])}},
                            "density": {"enum": list(VOCAB["density"])}, "reading_order": strings, "key_message": typed}},
                "regions": {"type": "array", "items": {"type": "object", "required": ["id", "role", "bbox"],
                                                     "properties": {"bbox": box, "id": {"type": "string", "pattern": "^[\\w-]+$"}}}},
                "elements": {"type": "array", "items": {"type": "object", "required": ["id", "kind", "label", "parent_id", "bbox", "observed", "evidence", "protection"],
                                                         "properties": {"id": {"type": "string", "pattern": "^[\\w-]+$"},
                                                                        "kind": {"enum": KINDS}, "bbox": box,
                                                                        "label": {"type": "string"}, "evidence": {"type": "string", "minLength": 1},
                                                                        "parent_id": {"type": ["string", "null"]},
                                                                        "region_id": {"type": "string"}, "geometry_status": {"enum": STATES},
                                                                        "observed": {"type": "object", "additionalProperties": typed}}}},
                "relations": {"type": "array", "items": {"type": "object", "required": ["id", "type", "from", "to", "direction", "evidence"],
                                                          "properties": {"id": {"type": "string"}, "from": {"type": "string"}, "to": {"type": "string"},
                                                                         "label": {"type": ["string", "null"]}, "evidence": {"type": "string", "minLength": 1},
                                                                         "type": {"enum": RELATIONS}, "direction": {"enum": ["forward", "reverse", "bidirectional", "none", "unknown"]}}}},
                "definitions": {"type": "object", "required": ["components", "typography", "palette"],
                                "properties": {key: {"type": "array", "items": {"type": "object"}} for key in ["components", "typography", "palette"]}},
                "review": {"type": "object", "required": ["status", "annotator", "independent_review"],
                           "properties": {"status": {"enum": ["suggested", "reviewed", "rejected"]}, "annotator": {"type": "string", "minLength": 1}}},
                "quality": {"type": "object", "required": ["image", "annotation", "suitability", "rights"]},
                "coverage": {"type": "object", "required": ["level", "complete", "missing"],
                             "properties": {"complete": {"type": "boolean"}, "missing": strings, "level": {"type": "string", "minLength": 1}}},
                "unknowns": strings, "issues": strings, "proposed_terms": {"type": "array"}
            }}


def validate(a, record=None):
    from jsonschema import Draft202012Validator
    errors = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in Draft202012Validator(schema()).iter_errors(a)]
    if errors:
        return errors
    if not valid_box(a["source"]["content_box"]):
        errors.append("source.content_box invalid bbox")
    all_nodes = a["regions"] + a["elements"]
    ids = [e["id"] for e in all_nodes]
    if len(ids) != len(set(ids)):
        errors.append("duplicate node IDs")
    nodes = {e["id"]: e for e in all_nodes}
    for e in all_nodes:
        if not valid_box(e["bbox"]):
            errors.append(f"{e['id']}: invalid bbox")
        parent, seen = e.get("parent_id"), {e["id"]}
        while parent:
            if parent in seen:
                errors.append(f"{e['id']}: parent cycle")
                break
            if parent not in nodes:
                errors.append(f"{e['id']}: missing parent {parent}")
                break
            seen.add(parent)
            parent = nodes[parent].get("parent_id")
        if e.get("region_id") and e["region_id"] not in {r["id"] for r in a["regions"]}:
            errors.append(f"{e['id']}: missing region")
        for key, v in e.get("observed", {}).items():
            if v["status"] in ("unknown", "not_applicable") and v["value"] is not None:
                errors.append(f"{e['id']}/{key}: unknown must be null")
            if v["status"] not in ("unknown", "not_applicable") and v["value"] is None:
                errors.append(f"{e['id']}/{key}: observed value missing")
            if key == "font_family" and v["value"] is not None and v["status"] != "verified":
                errors.append(f"{e['id']}/font_family: exact font requires verified metadata evidence")
            if v["type"] == "color" and v["value"] is not None and not re.fullmatch(r"#[a-fA-F0-9]{6}", str(v["value"])):
                errors.append(f"{e['id']}/{key}: invalid RGB color")
            if v["value"] is not None and v["type"] in ("text", "fontFamily", "enum") and not isinstance(v["value"], str):
                errors.append(f"{e['id']}/{key}: expected string")
            if v["type"] in ("dimension", "ratio", "angle") and v["unit"] != TYPE_UNITS[v["type"]]:
                errors.append(f"{e['id']}/{key}: wrong unit")
            if v["value"] is not None and v["type"] in ("dimension", "ratio", "angle", "number", "fontWeight"):
                n = v["value"]
                if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n):
                    errors.append(f"{e['id']}/{key}: expected finite number")
            if v["value"] is not None and v["type"] in ("shadow", "gradient"):
                from ppt_design_spec import validate_token
                try:
                    validate_token(v, e["id"] + "/" + key)
                except ValueError as exc:
                    errors.append(str(exc))
    if len({r["id"] for r in a["relations"]}) != len(a["relations"]):
        errors.append("duplicate relation IDs")
    for rel in a["relations"]:
        if rel["from"] not in nodes or rel["to"] not in nodes:
            errors.append(f"{rel['id']}: missing relation endpoint")
    for definition in a["definitions"]["components"]:
        if definition.get("element_id") not in nodes or definition.get("code") not in VOCAB["component"]:
            errors.append("component definition requires a known element and controlled component code")
    for pal in a["definitions"]["palette"]:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(pal.get("color"))):
            errors.append("palette requires an RGB color")
        point = pal.get("sample_xy")
        if not isinstance(point, list) or len(point) != 2 or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not 0 <= v <= 1 for v in point):
            errors.append("palette requires normalized sampling coordinates")
        if not pal.get("method") or pal.get("source_sha256") != a["source"]["sha256"]:
            errors.append("palette requires method and bound image hash")
    if a["coverage"]["complete"] and a["coverage"]["missing"]:
        errors.append("complete coverage cannot have missing objects")
    for id in a["page"]["reading_order"]:
        if id not in nodes:
            errors.append(f"reading_order: missing {id}")
    for key, family in [("role", "role"), ("layout", "layout"), ("relations", "relation"), ("density", "density")]:
        vals = a["page"][key] if isinstance(a["page"][key], list) else [a["page"][key]]
        for v in vals:
            if v not in VOCAB[family]:
                errors.append(f"page.{key}: uncontrolled term {v}")
    if record:
        for key, val in [("asset_id", record["id"]), ("deck_id", record["deck_code"]), ("page_id", record["page_code"])]:
            if a[key] != val:
                errors.append(f"{key}: identity mismatch")
        if a["source"]["sha256"] != record["sha256"] or a["source"]["version"] != record["version"]:
            errors.append("source: stale image version/hash")
    if a["review"]["status"] != "suggested":
        errors.append("candidate review status must be suggested; use independent receipt")
    return errors


def stage(library, annotations, records=None):
    """Validate entire batch first, then append immutable candidates. No legacy DB write."""
    import ppt_workflow as wf
    wf.reject_secrets(annotations)
    if records is None and (Path(library) / "index.sqlite3").is_file():
        with sqlite3.connect((Path(library) / "index.sqlite3").resolve().as_uri() + "?mode=ro", uri=True) as db:
            records = {r["id"]: r for (payload,) in db.execute("SELECT payload FROM assets_v3 WHERE current=1")
                       for r in [json.loads(payload)]}
    if records is not None and any(a.get("asset_id") not in records for a in annotations):
        raise ValueError("candidate asset not in current source manifest")
    failures = {a.get("asset_id", "?"): validate(a, (records or {}).get(a.get("asset_id"))) for a in annotations}
    if any(failures.values()):
        raise ValueError(canonical({k: v for k, v in failures.items() if v}))
    dest = Path(library) / "knowledge/candidates"
    paths = []
    for a in annotations:
        p = dest / a["asset_id"] / a["source"]["version"] / (digest(a) + ".json")
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            temp = p.with_name(uuid.uuid4().hex + ".tmp")
            temp.write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                # Windows rename is atomic and fails if an immutable digest already exists.
                temp.rename(p)
            except FileExistsError:
                temp.unlink()
        paths.append(str(p))
    return paths


def load(library, include_candidates=True):
    root = Path(library) / "knowledge"
    latest = {}
    for p in (root / "candidates").glob("*/*/*.json"):
        a = json.loads(p.read_text(encoding="utf-8"))
        if digest(a) != p.stem:
            raise ValueError("candidate bytes changed without a new annotation version")
        key = (a["asset_id"], a["source"]["version"])
        if key not in latest or p.stat().st_mtime_ns > latest[key][0]:
            latest[key] = (p.stat().st_mtime_ns, a)
    for key in list(latest):
        selection = root / "selections" / key[0] / (key[1] + ".json")
        if selection.exists():
            chosen = json.loads(selection.read_text(encoding="utf-8"))
            path = root / "candidates" / key[0] / key[1] / (chosen["annotation_hash"] + ".json")
            a = json.loads(path.read_text(encoding="utf-8"))
            if digest(a) != chosen["annotation_hash"]:
                raise ValueError("selected annotation changed")
            latest[key] = (path.stat().st_mtime_ns, a)
    result = []
    for _, a in latest.values():
        sha = digest(a)
        receipt = root / "reviews" / (sha + ".json")
        a["annotation_hash"] = sha
        if receipt.exists():
            r = json.loads(receipt.read_text(encoding="utf-8"))
            a["review"] = {**a["review"], "status": r["status"], "independent_review": r}
        if include_candidates or a["review"]["status"] == "reviewed":
            result.append(a)
    return result


def history(library, asset_id, version):
    if not re.fullmatch(r"a-[\w-]+", asset_id) or not re.fullmatch(r"[a-f0-9]{64}", version):
        raise ValueError("invalid source identity")
    paths = (Path(library) / "knowledge/candidates" / asset_id / version).glob("*.json")
    result = []
    for p in sorted(paths, key=lambda p: p.stat().st_mtime_ns, reverse=True):
        a = json.loads(p.read_text(encoding="utf-8"))
        if digest(a) != p.stem:
            raise ValueError("candidate hash mismatch")
        result.append({"annotation_hash": p.stem, "coverage": a["coverage"], "annotator": a["review"]["annotator"],
                       "element_count": len(a["elements"]), "title": a["page"]["title"]})
    return result


def select_version(library, asset_id, version, expected, chosen, reason):
    """Explicit, source-bound rollback; never delete candidates or old labels."""
    rows = history(library, asset_id, version)
    if chosen not in {r["annotation_hash"] for r in rows} or not isinstance(reason, str) or not reason.strip():
        raise ValueError("existing candidate hash and rollback reason required")
    root = Path(library) / "knowledge"
    lock = root / ".selection.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("another annotation selection is in progress")
    os.close(fd)
    try:
        current = next(a for a in load(library) if a["asset_id"] == asset_id and a["source"]["version"] == version)
        if current["annotation_hash"] != expected:
            raise ValueError("annotation selection changed; refresh first")
        record = {"asset_id": asset_id, "version": version, "previous_hash": expected,
                  "annotation_hash": chosen, "reason": reason}
        path = root / "selections" / asset_id / (version + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        log = root / "selection-history" / (uuid.uuid4().hex + ".json")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return record
    finally:
        lock.unlink()


def record_review(library, asset_id, version, receipt):
    a = next((x for x in load(library) if x["asset_id"] == asset_id and x["source"]["version"] == version), None)
    if not a:
        raise ValueError("candidate not found")
    if not receipt.get("reviewer") or receipt["reviewer"] == a["review"]["annotator"]:
        raise ValueError("independent reviewer required")
    checks = ["coverage", "coordinates", "text", "font_evidence", "relations", "contamination", "rights"]
    if receipt.get("status") not in ("reviewed", "rejected") or receipt.get("annotation_hash") != a["annotation_hash"]:
        raise ValueError("review must bind current candidate hash and disposition")
    if receipt.get("source_sha256") != a["source"]["sha256"] or not receipt.get("visual_evidence"):
        raise ValueError("fresh original-image visual evidence required")
    if any(k not in receipt.get("checks", {}) for k in checks):
        raise ValueError("review checklist incomplete")
    if receipt["status"] == "reviewed":
        if not a["coverage"]["complete"] or not all(receipt["checks"][k] == "passed" for k in checks):
            raise ValueError("partial inventory or failed checks cannot be reviewed")
    p = Path(library) / "knowledge/reviews" / (a["annotation_hash"] + ".json")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    return str(p)


def rank(rows, query="", filters=None, offset=0, limit=36):
    filters = filters or {}
    if set(filters) - {"deck", "role", "layout", "relation", "font", "status", "usage", "alpha", "kind"}:
        raise ValueError("unknown knowledge filter")
    terms = taxonomy()["terms"]
    vocab = {t["id"]: [t["id"], t["prefLabel"], *t["altLabel"]] for t in terms}
    aliases = {alias.casefold(): t["id"] for t in terms for alias in [t["id"], t["prefLabel"], *t["altLabel"]]}
    broader = {t["id"]: t["broader"] for t in terms}
    queries = [x.casefold() for x in re.split(r"[+\s＋]+", query.strip()) if x]
    matches = []
    for a in rows:
        page, review, source = a["page"], a["review"], a["source"]
        fields = {"deck": [a["deck_id"]], "role": [page["role"]], "layout": page["layout"],
                  "relation": page["relations"], "status": [review["status"]], "font": [],
                  "kind": list({e["kind"] for e in a["elements"]})}
        for e in a["elements"]:
            for key in ("font_class", "font_family"):
                v = e["observed"].get(key, {})
                if v.get("value") and (key != "font_family" or v["status"] == "verified"):
                    fields["font"].append(v["value"])
        if any(v not in fields[k] for k, v in filters.items() if k in fields and v):
            continue
        if "alpha" in filters and bool(source.get("alpha")) != filters["alpha"]:
            continue
        if filters.get("usage") not in (None, "", "reusable", "reference"):
            raise ValueError("unknown usage filter")
        if filters.get("usage") == "reusable" and (source["permissions"]["reuse"] != "approved" or
            review["status"] != "reviewed" or a["quality"]["image"]["status"] not in ("clean", "verified_clean") or
            a["quality"]["image"]["issues"] or any(e["kind"] == "contamination" for e in a["elements"])):
            continue
        codes = [a["asset_id"], a["page_id"], *a["deck"]["styles"], *a["deck"]["context"]]
        codes += [v for values in fields.values() for v in values]
        codes += [x.get("code", "") for x in a["definitions"]["components"]]
        # Broader concepts expand recall, while related concepts are suggestions only.
        for code in list(codes):
            pending, seen = list(broader.get(code, [])), set()
            while pending:
                parent = pending.pop()
                if parent not in seen:
                    codes.append(parent)
                    seen.add(parent)
                    pending.extend(broader.get(parent, []))
        corpus = [a["deck"]["title"], page["title"], *[e["label"] for e in a["elements"]]]
        for c in codes:
            corpus.extend(vocab.get(c, [c]))
        corpus = [x.casefold() for x in corpus]
        reasons = []
        for term in queries:
            canonical_term = aliases.get(term)
            if canonical_term and canonical_term in codes:
                reasons.append({"query": term, "matched": canonical_term, "evidence": "结构化字段"})
            else:
                found = next((x for x in corpus if term in x), None)
                if found is None:
                    break
                reasons.append({"query": term, "matched": found, "evidence": "人工视觉候选标注"})
        if len(reasons) != len(queries):
            continue
        item = dict(a)
        item["match_reasons"] = reasons
        item["preview_url"] = f"/api/assets/{a['asset_id']}/preview?version={source['version']}"
        item["score"] = 100 * len(reasons) + (20 if review["status"] == "reviewed" else 0) - 5 * len(a["quality"]["image"]["issues"])
        matches.append(item)
    matches.sort(key=lambda a: (-a["score"], a["deck_id"], a["deck"].get("source_order") or 0, a["page_id"]))
    # Round-robin within relevance tiers: keep the highest relevant hit per work before its next page.
    buckets = defaultdict(list)
    for a in matches:
        buckets[a["deck_id"]].append(a)
    diverse = []
    while any(buckets.values()):
        heads = sorted((v[0] for v in buckets.values() if v), key=lambda a: (-a["score"], a["deck_id"]))
        for a in heads:
            diverse.append(buckets[a["deck_id"]].pop(0))
    offset, limit = max(0, int(offset)), min(100, max(1, int(limit)))
    return {"items": copy.deepcopy(diverse[offset:offset + limit]), "total": len(diverse),
            "offset": offset, "has_more": offset + limit < len(diverse),
            "facets": {"deck": sorted({a["deck_id"] for a in rows}),
                       "role": sorted({a["page"]["role"] for a in rows}),
                       "layout": sorted({x for a in rows for x in a["page"]["layout"]}),
                       "relation": sorted({x for a in rows for x in a["page"]["relations"]}),
                       "font": sorted({e["observed"][key]["value"] for a in rows for e in a["elements"]
                                       for key in ("font_class", "font_family")
                                       if e["observed"].get(key, {}).get("value") and
                                       (key != "font_family" or e["observed"][key]["status"] == "verified")})},
            "inference_performed": False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["validate", "stage", "review", "schema", "taxonomy"])
    ap.add_argument("--input", type=Path)
    ap.add_argument("--library", type=Path, default=Path.home() / ".mediagen/library")
    args = ap.parse_args()
    if args.command in ("schema", "taxonomy"):
        print(json.dumps(schema() if args.command == "schema" else taxonomy(), ensure_ascii=False, indent=2))
        return
    data = json.loads(args.input.read_text(encoding="utf-8"))
    if args.command == "review":
        print(record_review(args.library, data["asset_id"], data["version"], data))
    else:
        rows = data if isinstance(data, list) else [data]
        errors = {a.get("page_id"): validate(a) for a in rows}
        if any(errors.values()):
            print(json.dumps(errors, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        print(json.dumps({"pages": len(rows), "validation": "passed", "visual_review": "not_implied",
                          "paths": stage(args.library, rows) if args.command == "stage" else []}, ensure_ascii=False))


if __name__ == "__main__":
    main()
