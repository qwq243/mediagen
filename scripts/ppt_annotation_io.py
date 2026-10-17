"""Image-bound annotation handoffs: original + normalized geometry + marked preview."""
import json
import math
import uuid
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont
import ppt_workflow as wf


def validate(shapes):
    if not isinstance(shapes, list) or len(shapes) > 300:
        raise ValueError("invalid annotation list")
    for shape in shapes:
        if shape.get("tool") not in ("pen", "rect", "ellipse", "arrow", "text"):
            raise ValueError("unknown annotation tool")
        pts = shape.get("points", [])
        if not isinstance(pts, list) or not pts or len(pts) > 6000:
            raise ValueError("annotation points missing/too many")
        if any(not isinstance(pt, list) or len(pt) != 2 or any(
                type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in pt) for pt in pts):
            raise ValueError("annotation coordinates must be normalized to the original image")
        if len(str(shape.get("text", ""))) > 4000:
            raise ValueError("annotation text too long")
        if not isinstance(shape.get("comment", ""), str) or len(shape.get("comment", "")) > 4000:
            raise ValueError("annotation comment too long")


def handoff(root, record):
    validate(record["shapes"])
    source = Path(record["base_path"])
    if wf.file_sha(source) != record["base_sha256"]:
        raise ValueError("annotation base changed")
    folder = Path(root) / "annotations" / record["id"]
    folder.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        im = ImageOps.exif_transpose(original).convert("RGB")
    w, h = im.size
    draw = ImageDraw.Draw(im)
    color, width = "#e83735", max(3, w // 350)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", max(18, w // 55))
    except OSError:
        font = ImageFont.load_default()
    geometry = []
    for index, shape in enumerate(record["shapes"]):
        pts = [(round(x * w), round(y * h)) for x, y in shape["points"]]
        a, b = pts[0], pts[-1]
        box = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
        if shape["tool"] == "ellipse":
            draw.ellipse(box, outline=color, width=width)
        elif shape["tool"] == "rect":
            draw.rectangle(box, outline=color, width=width)
        elif shape["tool"] == "text":
            draw.text(a, shape.get("text", ""), fill=color, font=font)
        elif len(pts) > 1:
            draw.line(pts, fill=color, width=width)
            if shape["tool"] == "arrow":
                angle = math.atan2(b[1] - a[1], b[0] - a[0])
                for d in (-.5, .5):
                    end = (b[0] - w / 50 * math.cos(angle + d), b[1] - w / 50 * math.sin(angle + d))
                    draw.line([b, end], fill=color, width=width)
        if shape.get("comment"):
            radius = max(13, w // 75)
            center = (min(w-radius, max(radius, a[0])), min(h-radius, max(radius, a[1])))
            draw.ellipse([center[0]-radius, center[1]-radius, center[0]+radius, center[1]+radius], fill=color)
            draw.text((center[0], center[1]), str(index+1), font=font, fill="white", anchor="mm")
        geometry.append({**shape, "pixel_points": pts})
    record["image_size"] = [w, h]
    record["overlay_path"] = str(folder / "marked-preview.png")
    record["handoff_path"] = str(folder / "annotation.json")
    im.save(record["overlay_path"])
    wf.write(record["handoff_path"], {**record, "geometry": geometry,
        "instruction": "标注仅解释修改意图；不是自动蒙版。先读原图、叠加图和文字，与用户对齐后再编辑。"})
    (folder / "README.md").write_text(
        f"# 图片批注 {record['id']}\n\n原图：{source}\n\nSHA-256：{record['base_sha256']}\n\n"
        f"目标：{record.get('page_id') or record.get('page_code') or record.get('asset_id')}\n\n"
        f"图像尺寸：{w} × {h}\n\n修改说明：{record['comment']}\n\n"
        f"叠加预览：{record['overlay_path']}\n\n坐标记录：{record['handoff_path']}\n\n"
        "原图未改动；每个点均有归一化及原图像素坐标。先确认局部编辑、重新生成或合成路线。\n",
        encoding="utf-8")
    return record


def reference(root, p, rid, version, image_hash, shapes, comment, library, submit=True, stage="stage1"):
    import ppt_assets as assets
    import ppt_studio as studio
    import ppt_progress as progress
    progress.require_stage(root, p, stage)
    validate(shapes)
    record = assets.get(rid, version, library)
    if record["sha256"] != image_hash:
        raise ValueError("reference image/version mismatch")
    path = assets.pin(record, library)
    item = {"id": "ann-" + uuid.uuid4().hex[:16], "target_kind": "reference",
            "asset_id": rid, "asset_version": record["version"], "page_code": record.get("page_code"),
            "base_path": str(path), "base_sha256": image_hash, "shapes": shapes, "comment": str(comment),
            "at": wf.now(), "status": "submitted" if submit else "draft", "stage": stage}
    handoff(root, item)
    p["annotations"].append(item)
    wf.save(root, p)
    if submit:
        studio.create_draft(root, p, comment=comment or "请解释参考图圈画部位的借鉴方式",
            stage=stage, submit=True, kind="reference_annotation",
            details={"annotation_id": item["id"], "asset_id": rid, "asset_version": record["version"],
                     "base_sha256": image_hash, "handoff_path": item["handoff_path"]})
    return item
