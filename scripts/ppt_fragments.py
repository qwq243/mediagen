"""Non-destructive crops from registered image versions, in original oriented pixels."""
import math
import uuid
from pathlib import Path
from PIL import Image, ImageOps
import ppt_assets as assets
import ppt_studio as studio
import ppt_workflow as wf


def crop(root, p, body, library=wf.LIBRARY):
    box = body.get("box")
    if (not isinstance(box, list) or len(box) != 4 or any(
            type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in box)
            or box[2] <= box[0] or box[3] <= box[1]):
        raise ValueError("裁切范围必须为原图归一化坐标 [左,上,右,下]")
    title = str(body.get("title", "")).strip()
    tags = body.get("tags", [])
    kind = body.get("kind", "decoration")
    if not title or len(title) > 200 or kind not in assets.KINDS:
        raise ValueError("请填写素材名称并选择类型")
    if not isinstance(tags, list) or len(tags) > 30 or any(not isinstance(t, str) or len(t) > 80 for t in tags):
        raise ValueError("标签格式无效")
    parent = None
    if body.get("target_kind") == "reference":
        source = assets.get(body["asset_id"], body["asset_version"], library)
        path = assets.pin(source, library)
        parent = {"id": source["id"], "version": source["version"]}
        target = {**parent, "page_code": source.get("page_code"), "deck_code": source.get("deck_code")}
        protected = source.get("original_metadata", {}).get("role") == "evidence"
    elif body.get("target_kind") == "page":
        source = studio._image_target(p, body["page_id"], body.get("candidate_id"))
        path = wf.local(root, source["path"])
        target = {"project": str(Path(root).resolve()), "page_id": body["page_id"],
                  "candidate_id": source.get("id"), "kind": source.get("kind")}
        protected = bool(source.get("metadata", {}).get("contains_evidence") or
                         studio.page(p, body["page_id"]).get("materials"))
    else:
        raise ValueError("只可截取已登记的参考图或页面成图")
    digest = wf.file_sha(path)
    if digest != body.get("sha256"):
        raise ValueError("原图版本已变化，请重新打开图片")
    # Keep a complete immutable original even when the project is later removed.
    with Image.open(path) as original:
        im = ImageOps.exif_transpose(original)
        w, h = im.size
        pixel_box = [max(0, round(box[0]*w)), max(0, round(box[1]*h)),
                     min(w, round(box[2]*w)), min(h, round(box[3]*h))]
        if pixel_box[2]-pixel_box[0] < 4 or pixel_box[3]-pixel_box[1] < 4:
            raise ValueError("截取区域太小，请至少选择 4 × 4 像素")
        patch = im.crop(pixel_box)
    folder = Path(library) / "fragments" / ("crop-" + uuid.uuid4().hex[:16])
    folder.mkdir(parents=True)
    import shutil
    snapshot = folder / ("original" + path.suffix.lower())
    shutil.copyfile(path, snapshot)
    if wf.file_sha(snapshot) != digest:
        raise ValueError("截取期间原图变化，已停止")
    dest = folder / "fragment.png"
    patch.save(dest)
    derivation = {"operation": "crop", "target_kind": body["target_kind"], "source": target,
                  "original_path": str(snapshot), "original_sha256": digest,
                  "oriented_size": [w, h], "box_normalized": box, "box_pixels": pixel_box,
                  "at": wf.now(), "resampled": False}
    import image_recipe
    parent_recipe = image_recipe.bundle_to(path, Path(library) / "generation-records")
    if parent_recipe:
        # This recipe generated the source, not the cropped pixels.
        derivation["source_generation_recipe"] = parent_recipe
    record = assets.import_image(dest, {
        "title": title, "kind": kind, "tags": ["局部参考", *tags], "parent": parent,
        "status": "reference", "derivation": derivation,
        "role": "evidence" if protected else "reference",
        # Do not inherit facts, palette, typography or the whole slide's structure.
    }, library)
    wf.write(folder / "derivation.json", {**derivation, "asset_id": record["id"],
                                        "asset_version": record["version"]})
    assets.favorite(record["id"], True, library)
    record["favorite"] = True
    return record


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job", type=Path, required=True)
    ap.add_argument("--spec", type=Path, required=True, help="version-bound crop selection JSON")
    ap.add_argument("--library", type=Path, default=wf.LIBRARY)
    args = ap.parse_args()
    result = crop(args.job, wf.load(args.job), wf.read(args.spec), args.library)
    print(__import__("json").dumps(result, ensure_ascii=False, indent=2))
