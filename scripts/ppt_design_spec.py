"""Compile one canonical design spec into measurable targets and full-image guidance.

Coordinates and fonts are prompt constraints, NOT image-API controls.
"""
import copy
import hashlib
import json
import math
import re
import shutil
import io
import zipfile
from pathlib import Path
from ppt_knowledge import canonical, digest, file_hash, valid_box

COMPILER = "ppt-design/1.0"
TOLERANCES = {"center_axis": .02, "relative_size": .10, "flat_delta_e00": 5.0}

def schema():
    box = {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "number", "minimum": 0, "maximum": 1}}
    layer = {"type": "object", "properties": {
        "tokens": {"type": "object", "additionalProperties": {"type": "object", "required": ["type", "value"]}},
        "hard_constraints": {"type": "object"}, "element_defaults": {"type": "object"}, "template": {"type": "string"},
        "elements": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["id", "bbox"],
            "properties": {"id": {"type": "string", "minLength": 1}, "bbox": box,
                           "text": {"type": "string"}, "kind": {"type": "string"}, "style": {"type": "object"},
                           "hard_constraints": {"type": "object"}}}},
        "relations": {"type": "array", "items": {"type": "object", "required": ["from", "to"]}},
        "components": {"type": "object"}, "background": {"type": "object"},
        "safe_zones": {"type": "array", "items": box}, "reference_borrowing": {"type": "array"}}}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:mediagen:ppt-design:1",
            "type": "object", "required": ["version", "pages"], "properties": {
                "version": {"const": 1}, "canvas": {"type": "array", "minItems": 2, "maxItems": 2,
                                                  "items": {"type": "integer", "minimum": 1}},
                "global": layer, "hard_constraints": {"type": "object"},
                "templates": {"type": "object", "additionalProperties": layer},
                "pages": {"type": "object", "minProperties": 1, "additionalProperties": layer},
                "tolerances": {"type": "object", "required": list(TOLERANCES), "additionalProperties": False,
                               "properties": {name: {"type": "number", "minimum": 0} for name in TOLERANCES}}}}


def finite_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def normalize_numbers(value):
    """Keep browser/Python JSON round trips from invalidating unchanged targets."""
    if isinstance(value, dict):
        return {key: normalize_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_numbers(item) for item in value]
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return value


def validate_token(token, name="token"):
    """Typed project targets, not a claim of DTCG or provider API conformance."""
    if not isinstance(token, dict) or "value" not in token:
        raise ValueError(f"{name}: token needs type/value")
    kind, v = token.get("type"), token["value"]
    if kind == "color":
        good = isinstance(v, str) and bool(re.fullmatch(r"#[0-9a-fA-F]{6}", v))
    elif kind in ("dimension", "angle", "ratio", "number"):
        unit = {"dimension": "px", "angle": "deg", "ratio": "ratio", "number": None}[kind]
        good = finite_number(v) and token.get("unit") == unit
        if kind == "ratio":
            good = good and 0 <= v <= 1
    elif kind == "fontWeight":
        good = finite_number(v) and 1 <= v <= 1000
    elif kind in ("fontFamily", "text", "enum"):
        good = isinstance(v, str) and bool(v.strip())
    elif kind == "gradient":
        good = isinstance(v, dict) and v.get("kind") in ("linear", "radial") and finite_number(v.get("angle_deg"))
        stops = v.get("stops", []) if isinstance(v, dict) else []
        good = good and len(stops) >= 2
        positions = []
        for stop in stops:
            validate_token({"type": "color", "value": stop.get("color")}, name + ".stop")
            pos = stop.get("position")
            if not finite_number(pos) or not 0 <= pos <= 1:
                raise ValueError(f"{name}: gradient stop outside 0..1")
            positions.append(pos)
        good = good and positions == sorted(positions)
    elif kind == "shadow":
        good = isinstance(v, dict) and all(finite_number(v.get(k)) for k in ("x_px", "y_px", "blur_px", "spread_px", "opacity"))
        if good:
            good = v["blur_px"] >= 0 and 0 <= v["opacity"] <= 1
            validate_token({"type": "color", "value": v.get("color")}, name + ".color")
    elif kind == "typography":
        good = isinstance(v, dict) and isinstance(v.get("class"), str)
        if good:
            good = (v.get("family") is None or isinstance(v["family"], str)) and all(
                finite_number(v.get(k)) for k in ("size_px", "weight", "line_height", "letter_spacing_px"))
        if good:
            good = v["size_px"] > 0 and 1 <= v["weight"] <= 1000 and v["line_height"] > 0
    else:
        good = False
    if not good:
        raise ValueError(f"{name}: invalid typed {kind} value/unit")


def merge(base, overlay):
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def borrow_proposal(spec, page_id, target_id, annotation, source_id, purpose):
    """Translate observed attributes into an explicit, unapproved design proposal.

    This never borrows words, brand identity, image bytes, unknown metrics or rights.
    """
    import ppt_knowledge as knowledge
    if purpose not in ("structure", "typography_appearance", "palette", "component"):
        raise ValueError("unknown borrowing purpose")
    source = next((e for e in annotation["elements"] if e["id"] == source_id), None)
    if not source or source["kind"] == "contamination":
        raise ValueError("source is not a design element")
    result = copy.deepcopy(spec)
    compiled = compile_spec(result, page_id)
    page = result["pages"][page_id]
    template = result.get("templates", {}).get(page.get("template"), {})
    inherited = merge(merge(result.get("global", {}), template), page)
    if "elements" not in page:
        page["elements"] = copy.deepcopy(inherited["elements"])
    target = next((e for e in page["elements"] if e["id"] == target_id), None)
    if not target:
        raise ValueError("unknown target element")
    before = copy.deepcopy(target)
    observations, changes = source["observed"], {}
    provenance = {
        "asset_id": annotation["asset_id"], "source_version": annotation["source"]["version"],
        "source_sha256": annotation["source"]["sha256"], "annotation_hash": annotation["annotation_hash"],
        "element_id": source_id, "purpose": purpose, "source_bbox": source["bbox"],
        "content_box": annotation["source"]["content_box"],
        "annotation_status": annotation["review"]["status"],
        "send_to_model": False, "target_element_id": target_id,
    }

    def observed(name):
        v = observations.get(name, {})
        return v if v.get("status") in ("measured", "estimated", "verified") and v.get("value") is not None else None

    def typed(v):
        return {key: v[key] for key in ("type", "value", "unit") if v.get(key) is not None}

    if purpose == "structure":
        box = knowledge.content_coordinates(source["bbox"], annotation["source"]["content_box"])
        if not valid_box(box):
            raise ValueError("source box extends outside the actual slide content")
        target["bbox"] = [round(v, 6) for v in box]
        target["geometry_status"] = "proposed_from_reference"
        changes["bbox"] = {"before": before["bbox"], "proposed": target["bbox"],
                           "observation_status": source["geometry_status"]}
    elif purpose == "typography_appearance":
        resolved_target = next(e for e in compiled["elements"] if e["id"] == target_id)
        typography = copy.deepcopy(resolved_target.get("style", {}).get("typography"))
        for name in ("font_class", "font_weight", "font_family", "letter_spacing"):
            v = observed(name)
            if v and (name != "font_family" or v["status"] == "verified"):
                if typography and typography.get("type") == "typography":
                    field = {"font_class": "class", "font_weight": "weight",
                             "font_family": "family", "letter_spacing": "letter_spacing_px"}[name]
                    typography["value"][field] = v["value"]
                    if name == "font_class" and not observed("font_family"):
                        typography["value"]["family"] = None
                    target.setdefault("style", {}).pop(name, None)
                else:
                    target.setdefault("style", {})[name] = typed(v)
                changes[name] = {"proposed": typed(v), "observation_status": v["status"], "evidence": v["evidence"]}
        if typography:
            target.setdefault("style", {})["typography"] = typography
        # Visible glyph height is intentionally NOT interpreted as the font's point size.
        if not changes:
            raise ValueError("no observed typography attributes; unknown font metrics cannot be invented")
    elif purpose == "palette":
        v = observed("color")
        if not v:
            raise ValueError("selected element has no evidenced color sample; confirm a sample first")
        target.setdefault("style", {})["color"] = typed(v)
        if target.get("flat_color"):
            target["flat_color"] = v["value"]
        changes["color"] = {"proposed": typed(v), "observation_status": v["status"], "evidence": v["evidence"]}
    else:
        if source["kind"] not in ("card", "icon", "arrow", "navigation", "decoration"):
            raise ValueError("only neutral design components; never import brands, evidence images or source words")
        definitions = [{key: d[key] for key in ("code", "fixed", "applicable_roles") if key in d}
                       for d in annotation["definitions"]["components"] if d.get("element_id") == source_id]
        appearance = {name: typed(v) for name in observations if name not in (
            "text", "font_family", "font_class", "font_weight", "glyph_height", "line_height", "letter_spacing")
            if (v := observed(name))}
        if not appearance and not definitions:
            raise ValueError("component appearance is still unknown; complete its annotation first")
        component_id = "borrow-" + digest(provenance)[:12]
        page.setdefault("components", {})[component_id] = {
            "appearance": appearance, "source_definitions": definitions,
            "variable": "Keep the current target text; source words and brands are excluded.",
            "source": provenance, "status": "user_confirmation_required",
        }
        target["component"] = component_id
        changes["component"] = {"proposed": component_id, "definition": page["components"][component_id]}
    page.setdefault("reference_borrowing", []).append(provenance)
    compile_spec(result, page_id)
    return {"spec": result, "changes": changes, "source": provenance,
            "warnings": ["这是观察值转为设计目标的提案，不代表精确测量或独立复核。",
                         "保留当前文案、硬约束与阈值；未知字号不推定；不上传原图，不改变版权或入模权限。"],
            "proposal_hash": digest(normalize_numbers({"spec": result, "source": provenance}))}


def compile_spec(spec, page_id, canvas=None):
    from jsonschema import Draft202012Validator
    errors = list(Draft202012Validator(schema()).iter_errors(spec))
    if errors:
        raise ValueError("design schema: " + "; ".join(f"{'/'.join(map(str,e.path))}: {e.message}" for e in errors[:5]))
    if spec.get("version") != 1:
        raise ValueError("unsupported design specification version")
    if page_id not in spec.get("pages", {}):
        raise ValueError("missing page design specification")
    page = spec["pages"][page_id]
    template_id = page.get("template")
    if template_id and template_id not in spec.get("templates", {}):
        raise ValueError("unknown page template")
    template = spec.get("templates", {}).get(template_id, {})
    hard = copy.deepcopy(spec.get("hard_constraints", {}))
    layers = [spec.get("global", {}), template, page]
    # Even overwritten template elements cannot silently remove a hard protection.
    for layer in [*layers, *(layer.get("element_defaults", {}) for layer in layers),
                  *(e for layer in layers for e in layer.get("elements", []))]:
        for k, v in layer.get("hard_constraints", {}).items():
            if k in hard and hard[k] != v:
                raise ValueError(f"hard constraint conflict: {k}")
            hard[k] = v
    resolved = merge(merge(spec.get("global", {}), template), page)
    size = canvas or spec.get("canvas", [1280, 720])
    if len(size) != 2 or any(type(x) is not int or x <= 0 for x in size):
        raise ValueError("canvas must contain two positive integer dimensions")
    tokens = resolved.get("tokens", {})
    for name, token in tokens.items():
        validate_token(token, name)
    seen = set()
    elements = [merge(resolved.get("element_defaults", {}), e) for e in resolved.get("elements", [])]
    if not elements:
        raise ValueError("a page must define at least one target element")
    for e in elements:
        if not e.get("id") or e["id"] in seen:
            raise ValueError("missing or duplicate target element id")
        seen.add(e["id"])
        if not valid_box(e.get("bbox")):
            raise ValueError(f"{e['id']}: invalid target bbox")
        e["pixels"] = [round(v * size[i % 2], 4) for i, v in enumerate(e["bbox"])]
        e["center"] = [round(e["bbox"][i] + e["bbox"][i+2]/2, 6) for i in (0, 1)]
        e["center_pixels"] = [round(e["center"][i]*size[i], 4) for i in (0, 1)]
        e["aspect_ratio"] = round(e["bbox"][2]*size[0]/(e["bbox"][3]*size[1]), 6)
        if e.get("style_token") and e["style_token"] not in tokens:
            raise ValueError("unresolved style token")
        for name, target in e.get("style", {}).items():
            if isinstance(target, dict) and "token" in target:
                if target["token"] not in tokens:
                    raise ValueError(f"{e['id']}: unresolved {name} token")
                e["style"][name] = copy.deepcopy(tokens[target["token"]])
            else:
                validate_token(target, e["id"] + "." + name)
        if e.get("flat_color"):
            validate_token({"type": "color", "value": e["flat_color"]}, e["id"] + ".flat_color")
    for r in resolved.get("relations", []):
        if r.get("from") not in seen or r.get("to") not in seen:
            raise ValueError("unknown target relation endpoint")
    result = {"compiler_version": COMPILER, "page_id": page_id, "canvas": size,
              "hard_constraints": hard, "tokens": tokens, "elements": elements,
              "relations": resolved.get("relations", []), "safe_zones": resolved.get("safe_zones", []),
              "components": resolved.get("components", {}),
              "background": resolved.get("background", {}),
              "tolerances": copy.deepcopy(spec.get("tolerances", TOLERANCES)),
              "reference_borrowing": resolved.get("reference_borrowing", []),
              "model_parameter_boundary": "All font/geometry/color values below are prompt targets, not exact API execution."}
    # Missing or relaxed checks are never silently accepted.
    if set(result["tolerances"]) != set(TOLERANCES):
        raise ValueError("all named tolerance thresholds required")
    for k, v in result["tolerances"].items():
        if not finite_number(v) or not 0 <= v <= (100 if k == "flat_delta_e00" else 1):
            raise ValueError("invalid tolerance")
    for b in result["safe_zones"]:
        if not valid_box(b):
            raise ValueError("invalid protected safe zone")
    result = normalize_numbers(result)
    result["spec_hash"] = digest(result)
    return result


def prompt_section(spec, page_id):
    resolved = compile_spec(spec, page_id)
    return ("\nQUANTIFIED DESIGN TARGETS (full-image generation; evaluate deviations, never assume exact execution):\n"
            + canonical(resolved) + "\nDo not render IDs, coordinates, source claims, or validation notes as slide text.\n"
            "Hard constraints cannot be relaxed. Use current exact visible text only. Unknown properties are not instructions.")


def validate_project_spec(spec, pages):
    if set(spec.get("pages", {})) != {p["page_id"] for p in pages}:
        raise ValueError("design spec must cover exactly the project pages")
    for page in pages:
        target = compile_spec(spec, page["page_id"])
        for e in target["elements"]:
            if e.get("text") and e["text"] not in page.get("page_text", ""):
                raise ValueError(f"{page['page_id']}/{e['id']}: design text conflicts with approved visible content")


def reference_inputs(root, p, pg, is_samples):
    """The UI and actual render share this exact ordered resolver, including the style anchor."""
    import ppt_workflow as wf
    by_id = {r["id"]: r for r in p["references"]}
    items = []

    def add(item, origin, path, id):
        fp = wf.local(root, path)
        items.append({"id": id, "origin": origin, "path": str(fp), "sha256": file_hash(fp),
                      "version": item.get("version") or item.get("sha256"),
                      "purpose": item.get("use") or item.get("usage") or item.get("role") or "approved style anchor",
                      "upload_authorization": "project_approved",
                      "copyright_status": item.get("rights", "unknown")})

    for rid in pg.get("reference_ids", []):
        ref = by_id[rid]
        if ref.get("send_to_model"):
            add(ref, "reference", ref["path"], rid)
    for item in p.get("asset_selection", []):
        if item.get("model_allowed") and item["usage"] != "structure" and wf.uses_asset(p, pg, item):
            add(item, "library", item["path"], item["id"])
    if not is_samples:
        approved = wf.sample_ids(p)
        if not approved:
            raise ValueError("no representative style anchor")
        default = approved[0] if pg.get("page_role") in ("cover", "divider", "closing") else approved[-1]
        style_id = pg.get("style_reference_page_id", default)
        if style_id not in approved:
            raise ValueError("style anchor must be an approved representative")
        master = next(x for x in p["pages"] if x["page_id"] == style_id)
        selected = master.get("selected_output")
        if not selected:
            raise ValueError("style anchor output missing")
        source = selected
        if master.get("materials") or selected.get("metadata", {}).get("contains_evidence"):
            source = selected.get("metadata", {}).get("clean_model_image")
            if not source or file_hash(wf.local(root, source["path"])) != source["sha256"]:
                raise ValueError("style anchor contains evidence; verified clean model image required")
        add(source, "style_anchor", source["path"], style_id)
        items.insert(0, items.pop())
    for i, item in enumerate(items):
        item["order"] = i + 1
    return items


def request_package(root, p, page_id, is_samples=True):
    import ppt_workflow as wf
    pg = next(x for x in p["pages"] if x["page_id"] == page_id)
    prompt = wf.prompts(root, p)[page_id]
    spec = p["design"].get("atomic_spec")
    package = {"schema_version": 1, "compiler_version": COMPILER, "page_id": page_id,
               "lane": "samples" if is_samples else "deck",
               "spec": compile_spec(spec, page_id) if spec else None,
               "spec_source": ({**{k: v for k, v in spec.items() if k not in ("pages", "templates")},
                                "pages": {page_id: spec["pages"][page_id]},
                                "templates": {k: v for k, v in spec.get("templates", {}).items()
                                              if k == spec["pages"][page_id].get("template")}} if spec else None),
               "legacy_design": p["design"] if spec is None else None,
               "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
               "inputs": reference_inputs(root, p, pg, is_samples),
               "api_parameters": {k: p["generation_contract"].get(k) for k in ("model", "size", "quality")},
               "api_fixed_parameters": {"output_format": "png", "response_format": "url", "stream": True},
               "reported_model": None, "seed": None, "provider_defaults": "unknown",
               "reproducibility": "Same spec and immutable input bytes compile the same request; generated pixels may vary."}
    package = normalize_numbers(package)
    package["request_hash"] = digest(package)
    return package


def freeze_package(root, package):
    dest = Path(root) / "design-request-packages" / package["request_hash"]
    dest.mkdir(parents=True, exist_ok=True)
    bundle = copy.deepcopy(package)
    for inp in bundle["inputs"]:
        src = Path(inp["path"])
        if file_hash(src) != inp["sha256"]:
            raise ValueError("reference changed after compilation")
        name = f"{inp['order']:02}-{inp['sha256']}{src.suffix.lower()}"
        target = dest / name
        if not target.exists():
            shutil.copy2(src, target)
        if file_hash(target) != inp["sha256"]:
            raise ValueError("archived reference corrupted")
        inp["original_path"] = inp["path"]
        inp["path"] = name
    (dest / "request.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    (dest / "prompt.txt").write_text(package["prompt"], encoding="utf-8")
    return str(dest / "request.json")

def package_zip(root, p, page_id, is_samples=True):
    """Read-only, local export. Unknown copyright stays unknown; no upload or inference."""
    import ppt_workflow as wf
    package = request_package(root, p, page_id, is_samples)
    archived = copy.deepcopy(package)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for item in archived["inputs"]:
            raw = Path(item["path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise ValueError("reference changed during export")
            name = f"inputs/{item['order']:02}-{item['sha256']}{Path(item['path']).suffix.lower()}"
            item["original_path"], item["path"] = item["path"], name
            z.writestr(name, raw)
        pg = next(x for x in p["pages"] if x["page_id"] == page_id)
        if pg.get("selected_output"):
            source = wf.local(root, pg["selected_output"]["path"])
            raw = source.read_bytes()
            output = {"path": "output" + source.suffix.lower(), "sha256": hashlib.sha256(raw).hexdigest(),
                      "adoption": pg["selected_output"]}
            z.writestr(output["path"], raw)
            z.writestr("adoption.json", json.dumps(output, ensure_ascii=False, indent=2))
            recipe_ref = pg["selected_output"].get("metadata", {}).get("generation_recipe")
            if recipe_ref:
                import image_recipe
                recipe_path = wf.local(root, recipe_ref["path"])
                if file_hash(recipe_path) != recipe_ref["sha256"]:
                    raise ValueError("selected output recipe changed")
                record = json.loads(recipe_path.read_text(encoding="utf-8"))
                image_recipe.safe(record)
                archive_base = recipe_path.parent.resolve()
                for i, row in enumerate(record.get("inputs", []) + record.get("outputs", [])):
                    path = Path(row["path"]).resolve()
                    if not path.is_relative_to(archive_base) or file_hash(path) != row["sha256"]:
                        raise ValueError("historical recipe input/output changed or escaped archive")
                    name = f"generation/{i+1:02d}-{row['sha256']}{path.suffix.lower()}"
                    z.writestr(name, path.read_bytes())
                    row["original_path"], row["path"] = row["path"], name
                z.writestr("generation/recipe.json", json.dumps(record, ensure_ascii=False, indent=2))
                # Historical returned model belongs to that output, not a future request.
                z.writestr("generation/provider-evidence.json", json.dumps({
                    "requested_model": record.get("requested_model"), "reported_model": record.get("reported_model"),
                    "seed": record.get("parameters", {}).get("seed"),
                    "provider_defaults": record.get("provider_defaults", "unknown"),
                    "source": "historical adopted output; no new inference"}, ensure_ascii=False, indent=2))
        report = copy.deepcopy(p.get("design_deviation_reports", {}).get(page_id))
        if report:
            current_sha = hashlib.sha256(raw).hexdigest() if pg.get("selected_output") else None
            if not package["spec"] or report.get("target_hash") != package["spec"]["spec_hash"] or report.get("output_sha256") != current_sha:
                report["status"] = "stale"
            z.writestr("audit.json", json.dumps(report, ensure_ascii=False, indent=2))
        z.writestr("request.json", json.dumps(archived, ensure_ascii=False, indent=2))
        z.writestr("prompt.txt", package["prompt"])
        z.writestr("README.txt", "This is a local reproducibility package, not a new generation or copyright grant.\n"
                   "The request hash binds the original-path manifest; packaged paths are transport paths.\n"
                   "Unreported seed/model revision/defaults remain unknown. Pixels can vary on rerun.\n")
    return out.getvalue()


def delta_e(first, second):
    import numpy as np
    from skimage.color import rgb2lab, deltaE_ciede2000
    def lab(c):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", c):
            raise ValueError("invalid sRGB color")
        rgb = np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], dtype=float) / 255
        return rgb2lab(rgb.reshape(1, 1, 3))
    return float(deltaE_ciede2000(lab(first), lab(second))[0, 0])


def audit(target, measured):
    """No OCR guesses become green lights. Measurements must be explicitly supplied."""
    checks = []
    tolerances = target["tolerances"]
    if not isinstance(measured, dict) or not isinstance(measured.get("elements", {}), dict):
        raise ValueError("measurements must contain an element object")
    if set(measured.get("elements", {})) - {e["id"] for e in target["elements"]}:
        raise ValueError("measurements reference an unknown target element")
    def check(id, name, passed, detail):
        if passed is not None and not isinstance(passed, bool):
            raise ValueError(f"{name}: measurement verdict must be boolean or unknown")
        checks.append({"element_id": id, "check": name,
                       "status": "pending" if passed is None else ("passed" if passed else "failed"),
                       "detail": detail})
    for e in target["elements"]:
        m = measured.get("elements", {}).get(e["id"], {})
        if not isinstance(m, dict):
            raise ValueError("element measurements must be an object")
        if "text_verified" in m and not isinstance(m["text_verified"], bool):
            raise ValueError("text_verified must be boolean")
        b = m.get("bbox")
        if b is not None and not valid_box(b):
            raise ValueError("invalid measured bbox")
        if b:
            tb = e["bbox"]
            dx = abs(b[0] + b[2] / 2 - tb[0] - tb[2] / 2)
            dy = abs(b[1] + b[3] / 2 - tb[1] - tb[3] / 2)
            sizes = [abs(b[i] - tb[i]) / tb[i] for i in (2, 3)]
            check(e["id"], "center", max(dx, dy) <= tolerances["center_axis"] + 1e-9, {"dx": dx, "dy": dy})
            check(e["id"], "size", max(sizes) <= tolerances["relative_size"] + 1e-9, sizes)
        else:
            check(e["id"], "center", None, "未提供原尺寸测量")
            check(e["id"], "size", None, "未提供原尺寸测量")
        if "text" in e:
            check(e["id"], "text", m.get("text") == e["text"] if m.get("text_verified") else None, "逐字核对；OCR不确定不可通过")
            check(e["id"], "typography", m.get("typography_matches"), "对照批准字样的类别、层级、字重和可读性；非字体文件鉴定")
        if e.get("flat_color"):
            actual = m.get("flat_color")
            if m.get("sample_region") is not None and not valid_box(m["sample_region"]):
                raise ValueError("color sample region must use normalized x,y,w,h")
            de = delta_e(e["flat_color"], actual) if actual and m.get("sample_region") and m.get("sample_method") else None
            check(e["id"], "flat_color", de <= tolerances["flat_delta_e00"] if de is not None else None,
                  {"delta_e00": de, "condition": "指定平坦区域sRGB；不适用于渐变/照片/阴影"})
        if e.get("component"):
            check(e["id"], "component", m.get("component_matches"), "固定轮廓/配色/变量内容/跨页一致性")
    if target["relations"]:
        check("*", "semantic_relations", measured.get("semantic_relations_match"), "节点、方向、标签不可改变")
    check("*", "safe_zones_and_occlusion", measured.get("safe_zones_and_occlusion_passed"), "关键文字无裁切遮挡，保护区域无侵入")
    check("*", "hard_constraints", measured.get("hard_constraints_passed"), target["hard_constraints"])
    statuses = {c["status"] for c in checks}
    return {"compiler_version": COMPILER, "target_hash": target["spec_hash"],
            "status": "failed" if "failed" in statuses else ("pending" if "pending" in statuses else "passed"),
            "checks": checks, "measurements": measured, "tolerances": copy.deepcopy(tolerances)}
