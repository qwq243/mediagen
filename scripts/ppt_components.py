"""Fixed-component selection handoff; adaptation remains an explicitly authorized asset job."""
import copy
from pathlib import Path
import ppt_assets as assets
import ppt_studio as studio
import ppt_workflow as wf
from ppt_coding import bbox

SLOTS = {"header": "顶部标题栏", "footer": "页脚", "navigation": "章节导航",
         "brand": "品牌形象", "progress": "进度", "page_number": "页码"}
SCOPES = ("all", "content", "cover", "divider", "closing")
STRATEGIES = ("reference", "variant", "composite")


def request_selection(root, p, body, library=wf.LIBRARY):
    slot, scope, strategy = body.get("slot"), body.get("scope"), body.get("strategy")
    if slot not in SLOTS or scope not in SCOPES or strategy not in STRATEGIES:
        raise ValueError("请选择组件部位、适用页面和使用方式")
    row = assets.get(body["asset_id"], body["asset_version"], library)
    if row["sha256"] != body.get("sha256"):
        raise ValueError("组件原图已变化，请重新选择")
    if body.get("box") is not None:
        bbox(body["box"])
    # Collection only; this does not approve the component or authorize model upload.
    pin = assets.choose(root, p, row["id"], row["version"], "material", library)
    details = {"slot": slot, "scope": scope, "strategy": strategy, "box": body.get("box"),
               "source": {k: pin[k] for k in ("id", "version", "sha256", "path", "title")},
               "instruction": str(body.get("instruction", ""))[:4000]}
    return studio.create_draft(root, p, comment=f"固定组件：{SLOTS[slot]}，需与 Agent 对齐",
        kind="fixed_component", details=details, submit=True)


def apply_selection(root, p, request_id, summary, result_id=None, result_version=None,
                    model_allowed=False, box=None, library=wf.LIBRARY):
    """Agent entry after alignment, not called by a browser selection button."""
    req = next((r for r in p["revision_requests"] if r["id"] == request_id), None)
    if not req or req["kind"] != "fixed_component" or req["status"] not in ("draft", "submitted"):
        raise ValueError("no pending fixed-component request")
    if not summary.strip():
        raise ValueError("alignment summary required")
    if req["base_proposal_hash"] != wf.sha(studio.proposal(p)):
        raise ValueError("方案已变化，请重新对齐组件选择，不自动合并旧请求")
    d = req["details"]
    rid, version = result_id or d["source"]["id"], result_version or d["source"]["version"]
    row = assets.get(rid, version, library)
    if d["strategy"] == "variant":
        if (rid, version) == (d["source"]["id"], d["source"]["version"]):
            raise ValueError("变体尚未生成并选定；不能把原始裁切冒充适配后的变体")
        if row.get("parent") != {"id": d["source"]["id"], "version": d["source"]["version"]}:
            raise ValueError("变体须记录所选原素材的准确父版本")
    if (row.get("original_metadata", {}).get("role") == "evidence" and
            (d["strategy"] != "composite" or model_allowed)):
        raise ValueError("真实证据只能确定性合成，不进入图像模型")
    region = box if box is not None else d.get("box")
    if d["strategy"] == "composite":
        bbox(region)
    elif not model_allowed:
        raise ValueError("参考融图需先与用户对齐图片发送许可；选择不等于许可")
    entry = assets.choose(root, p, rid, version, "material", library)
    entry = copy.deepcopy(entry)
    entry["model_allowed"] = bool(model_allowed and d["strategy"] != "composite")
    p["asset_selection"] = [x for x in p["asset_selection"] if x["id"] != rid] + [entry]
    pack = copy.deepcopy(p["component_pack"])
    pack["enabled"] = True
    item = {"slot": d["slot"], "scope": d["scope"], "asset_id": rid, "version": version,
            "sha256": row["sha256"], "title": row["title"], "box": region,
            "mode": "composite" if d["strategy"] == "composite" else "reference",
            "source_request": request_id, "fixed_appearance_only": True}
    pack["items"] = [x for x in pack.get("items", []) if
                     (x["slot"], x["scope"]) != (item["slot"], item["scope"])] + [item]
    return studio.resolve(root, p, request_id, summary, replacement={"component_pack": pack})


def applicable(pack, page):
    role = page.get("page_role", "content")
    if role in ("section", "transition"):
        role = "divider"
    general = {x["slot"]: x for x in pack.get("items", []) if x["scope"] == "all"}
    general.update({x["slot"]: x for x in pack.get("items", []) if x["scope"] == role})
    return list(general.values()) if pack.get("enabled") else []


def validate(pack, selection):
    if not pack.get("enabled"):
        return
    selected = {x["id"]: x for x in selection}
    for item in pack.get("items", []):
        if item.get("scope") not in SCOPES or item.get("slot") not in SLOTS or item.get("mode") not in ("reference", "composite"):
            raise ValueError("invalid fixed component")
        asset = selected.get(item.get("asset_id"), {})
        if (item.get("version"), item.get("sha256")) != (asset.get("version"), asset.get("sha256")) or not asset:
            raise ValueError("固定组件需锁定已选资产版本")
        if item["mode"] == "composite":
            bbox(item.get("box"))
        elif not asset.get("model_allowed") or asset.get("protected_evidence"):
            raise ValueError("融图组件未获发送许可，或包含不能重画的证据")


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job", type=Path, required=True)
    ap.add_argument("--library", type=Path, default=wf.LIBRARY)
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser("request"); a.add_argument("--spec", type=Path, required=True)
    a = sub.add_parser("apply")
    a.add_argument("--request", required=True); a.add_argument("--summary", required=True)
    a.add_argument("--result-id"); a.add_argument("--result-version")
    a.add_argument("--model-upload-allowed", action="store_true")
    a.add_argument("--box", type=float, nargs=4)
    args = ap.parse_args(); p = wf.load(args.job)
    result = (request_selection(args.job, p, wf.read(args.spec), args.library) if args.command == "request"
              else apply_selection(args.job, p, args.request, args.summary, args.result_id,
                  args.result_version, args.model_upload_allowed, args.box, args.library))
    print(json.dumps(result, ensure_ascii=False, indent=2))
