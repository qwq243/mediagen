"""Version-bound region plans, alpha edit masks and exact post-generation blank zones."""
import copy
import re
import shutil
import uuid
from pathlib import Path
from PIL import Image, ImageOps
import ppt_studio as studio
import ppt_workflow as wf
from ppt_coding import bbox


def validate(regions, root=None):
    if not isinstance(regions, list) or len(regions) > 30:
        raise ValueError("reserved_regions must be a list of at most 30 zones")
    for r in regions:
        bbox(r.get("box"))
        if r.get("mode") not in ("prompt_only", "solid", "transparent", "image"):
            raise ValueError("unknown blank-zone mode")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", r.get("color", "#FFFFFF")):
            raise ValueError("blank-zone color must be #RRGGBB")
        if not str(r.get("purpose", "")).strip():
            raise ValueError("请说明留空位置的用途")
        if r.get("mode") == "image":
            item = r.get("embedded_asset", {})
            if not all(item.get(k) for k in ("id", "version", "sha256", "path")):
                raise ValueError("嵌入图片缺少固定版本或本机文件")
            if item.get("fit") not in ("contain", "cover"):
                raise ValueError("嵌入图片仅支持等比完整显示或居中裁切")
            if item.get("protected_evidence") and item["fit"] != "contain":
                raise ValueError("真实证据必须完整显示，不能自动裁切")
            if root is not None and wf.file_sha(wf.local(root, item["path"])) != item["sha256"]:
                raise ValueError("嵌入图片文件已变化，需重新选择并审核")


def pixels(box, size):
    bbox(box)
    x, y, w, h = box
    return [round(x*size[0]), round(y*size[1]),
            round((x+w)*size[0]), round((y+h)*size[1])]


def request_region(root, p, body, library=wf.LIBRARY):
    pid = body["page_id"]
    pg = studio.page(p, pid)
    mode = body.get("mode")
    region = {"id": "zone-" + uuid.uuid4().hex[:12], "box": body.get("box"),
              "mode": "prompt_only" if mode == "edit_mask" else mode,
              "color": body.get("color", "#FFFFFF"), "purpose": str(body.get("purpose", "")).strip()[:2000]}
    if mode == "image":
        import ppt_assets as assets
        r = assets.get(body["asset_id"], body.get("asset_version"), library)
        if not body.get("asset_version") or body.get("asset_sha256") != r["sha256"]:
            raise ValueError("嵌入图片版本已变化，请重新选取")
        pinned = Path(root).resolve() / "assets/pinned" / (r["id"] + "-" + r["version"][:12] + Path(r["source_path"]).suffix.lower())
        region["embedded_asset"] = {"id": r["id"], "version": r["version"], "sha256": r["sha256"],
            "title": r["title"], "path": str(pinned), "kind": r["kind"],
            "fit": body.get("fit", "contain"),
            "protected_evidence": r.get("original_metadata", {}).get("role") == "evidence"}
    validate([region])
    base = None
    if body.get("sha256"):
        base = studio._image_target(p, pid, body.get("candidate_id"))
        src = wf.local(root, base["path"])
        if wf.file_sha(src) != body["sha256"]:
            raise ValueError("图片已变化，请重新选择区域")
        # Mask coordinates must match actual input bytes, not an EXIF-rotated preview.
        with Image.open(src) as im:
            if im.getexif().get(274, 1) != 1:
                raise ValueError("请先导入已规范方向的 PNG，再制作精确蒙版")
            size = im.size
    else:
        if mode == "edit_mask":
            raise ValueError("编辑蒙版需要已生成图片；未出图时请选择版式留空")
        size = tuple(map(int, p["generation_contract"]["size"].split("x")))
    rect = pixels(region["box"], size)
    if min(rect[2]-rect[0], rect[3]-rect[1]) < 4:
        raise ValueError("区域至少需要 4 × 4 原始像素")
    if mode == "edit_mask" and (pg.get("materials") or base.get("metadata", {}).get("contains_evidence")):
        raise ValueError("含真实证据的成图不能提交模型编辑；请使用干净底板并在之后贴回原证据")
    if mode == "image":
        src_asset = assets.pin(r, library)
        pinned.parent.mkdir(parents=True, exist_ok=True)
        if pinned.exists() and wf.file_sha(pinned) != r["sha256"]:
            raise ValueError("项目内嵌入图片已被修改，不能覆盖历史文件")
        if not pinned.exists():
            shutil.copyfile(src_asset, pinned)
        validate([region], root)
    folder = Path(root) / "regions" / region["id"]
    folder.mkdir(parents=True)
    if base:
        shutil.copyfile(src, folder / ("original" + src.suffix.lower()))
        if wf.file_sha(folder / ("original" + src.suffix.lower())) != body["sha256"]:
            raise ValueError("图片在保存期间变化，请重新选择")
    mask = Image.new("RGBA", size, (255, 255, 255, 255))
    mask.paste((255, 255, 255, 0), tuple(rect))
    mask.save(folder / "mask.png")
    details = {"id": region["id"], "mode": mode, "region": region, "page_id": pid,
               "candidate_id": body.get("candidate_id"), "image_sha256": body.get("sha256"),
               "image_size": list(size), "box_pixels_ltrb": rect,
               "coordinate_space": "normalized-xywh", "mask": wf.asset(root, folder / "mask.png"),
               "mask_semantics": "transparent region = requested edit; opaque = preserve",
               "model_capability": "not_verified", "at": wf.now()}
    if base:
        details["original"] = wf.asset(root, folder / ("original" + src.suffix.lower()))
    patch = {}
    if mode != "edit_mask":
        pages = studio.proposal(p)["pages"]
        target = next(x for x in pages if x["page_id"] == pid)
        target["reserved_regions"] = target.get("reserved_regions", []) + [region]
        patch = {"pages": pages}
    wf.write(folder / "region.json", details)
    result = studio.create_draft(root, p, patch=patch, kind="region_edit" if mode == "edit_mask" else "reserved_region",
        comment="请核对精确位置、图片适配与页面文字/组件关系；采纳后确定性合成，不自动付费。",
        details=details, submit=True)
    return result


def render_regions(image, regions):
    validate(regions)
    canvas = image.convert("RGBA")
    for r in regions:
        rect = pixels(r["box"], canvas.size)
        if r["mode"] == "solid" or (r["mode"] == "image" and not r.get("preserve_background", False)):
            canvas.paste(r["color"], tuple(rect))
        elif r["mode"] == "transparent":
            canvas.paste((0, 0, 0, 0), tuple(rect))
    return canvas


def finish_layout(root, p, pg, output):
    """Exact optional blanking and fixed asset paste; never redraw real source pixels."""
    import ppt_components as components
    validate(pg.get("reserved_regions", []), root)
    with Image.open(output) as original:
        canvas = render_regions(original, pg.get("reserved_regions", []))
    for region in pg.get("reserved_regions", []):
        if region["mode"] != "image":
            continue
        item = region["embedded_asset"]
        rect = pixels(region["box"], canvas.size)
        w, h = rect[2]-rect[0], rect[3]-rect[1]
        with Image.open(wf.local(root, item["path"])) as im:
            raw = ImageOps.exif_transpose(im).convert("RGBA")
            patch = (ImageOps.fit(raw, (w, h), Image.Resampling.LANCZOS) if item["fit"] == "cover"
                     else ImageOps.contain(raw, (w, h), Image.Resampling.LANCZOS))
            canvas.alpha_composite(patch, (rect[0]+(w-patch.width)//2, rect[1]+(h-patch.height)//2))
    selected = {x["id"]: x for x in p["asset_selection"]}
    for item in components.applicable(p["component_pack"], pg):
        if item["mode"] != "composite":
            continue
        entry = selected[item["asset_id"]]
        path = wf.local(root, entry["path"])
        if wf.file_sha(path) != item["sha256"]:
            raise ValueError("固定组件文件已变化")
        box = pixels(item["box"], canvas.size)
        with Image.open(path) as raw:
            patch = ImageOps.exif_transpose(raw).convert("RGBA")
            patch.thumbnail((box[2]-box[0], box[3]-box[1]), Image.Resampling.LANCZOS)
            canvas.alpha_composite(patch, (box[0]+(box[2]-box[0]-patch.width)//2,
                                         box[1]+(box[3]-box[1]-patch.height)//2))
    canvas.save(output)
    return {"operation": "deterministic_layout", "regions": copy.deepcopy(pg.get("reserved_regions", [])),
            "components": copy.deepcopy(components.applicable(p["component_pack"], pg)),
            "output_sha256": wf.file_sha(output)}


def materialize(root, p, pid, candidate_id=None):
    """No model call: create a new reviewable base from an existing image and adopted zones."""
    if any(x["status"] in ("draft", "submitted") for x in p["revision_requests"]):
        raise ValueError("先与 Agent 对齐待处理修改，再制作留空底板")
    pg = studio.page(p, pid)
    source = studio._image_target(p, pid, candidate_id)
    if not pg.get("reserved_regions") and not wf.component_values(p, pg).get("items"):
        raise ValueError("没有已采纳的留空或组件安排")
    import ppt_components
    ppt_components.validate(p["component_pack"], p["asset_selection"])
    src = wf.local(root, source["path"])
    if wf.file_sha(src) != source["sha256"]:
        raise ValueError("原图已变化")
    out = Path(root) / "outputs/composites" / ("layout-" + uuid.uuid4().hex[:16] + ".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        ImageOps.exif_transpose(im).save(out)
    record = finish_layout(root, p, pg, out)
    record["original"] = wf.asset(root, src)
    record.update(id="cmp-" + uuid.uuid4().hex[:16], page_id=pid,
                  output_path=str(out.resolve()), at=wf.now())
    p["composition_records"].append(record)
    wf.save(root, p)
    wf.write(out.with_suffix(".composition.json"), record)
    return studio.add_candidate(root, p, pid, out, "agent_composite", "依据已采纳区域制作的留空/组件底板",
        {"composition": record, "contains_evidence": bool(pg.get("materials") or
            source.get("metadata", {}).get("contains_evidence") or
            any(r.get("embedded_asset", {}).get("protected_evidence") for r in pg.get("reserved_regions", [])) or
            any(x.get("protected_evidence") for x in p["asset_selection"]
                if x["id"] in {i["asset_id"] for i in ppt_components.applicable(p["component_pack"], pg)}))})


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job", type=Path, required=True)
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser("request"); a.add_argument("--spec", type=Path, required=True)
    a = sub.add_parser("materialize"); a.add_argument("--page", required=True); a.add_argument("--candidate")
    args = ap.parse_args()
    p = wf.load(args.job)
    result = (request_region(args.job, p, wf.read(args.spec)) if args.command == "request"
              else materialize(args.job, p, args.page, args.candidate))
    print(json.dumps(result, ensure_ascii=False, indent=2))
