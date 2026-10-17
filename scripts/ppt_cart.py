"""Shared local/external resource cart. Collection is never production consent."""
from __future__ import annotations
import argparse
import copy
import json
import sys
import uuid
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from pathlib import Path
import ppt_assets as assets
import ppt_studio as studio
import ppt_workflow as wf

# Discovery portals, not an assertion of availability or reuse permission.
# Only Commons has an integrated public API adapter. This curated directory
# is not presented as a complete scraped copy of the user's reference site.
CATALOG_PATH = Path(__file__).resolve().parents[1] / "references" / "ppt-resource-sites.json"
CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
SITES = CATALOG["sites"]
SITE_CATEGORIES = CATALOG["categories"]


def site_catalog(library=wf.LIBRARY):
    """Shared local channel index; no crawling or network requests while rendering."""
    categories = copy.deepcopy(SITE_CATEGORIES)
    items = [{**x, "collection": "curated"} for x in SITES]
    seen = {x["id"] for x in items}
    extension = Path(library) / "channels" / "aboutppt.json"
    if extension.is_file():
        extra = wf.read(extension)
        category_ids = {x["id"] for x in categories}
        for group in extra.get("categories", []):
            if group["id"] not in category_ids:
                categories.append({k: group[k] for k in ("id", "name", "hint")})
                category_ids.add(group["id"])
        for raw in extra.get("sites", []):
            try:
                safe_url(raw["url"])
                wf.safe_id(raw["id"])
            except (KeyError, ValueError):
                continue
            if raw["id"] in seen or raw.get("group") not in category_ids:
                continue
            # Treat imported metadata as data, not endpoint declarations.
            item = {k: raw[k] for k in ("id", "name", "group", "category", "url", "description",
                                       "monogram", "tone", "source_url", "source_tab") if k in raw}
            item.update(collection="aboutppt", api=False)
            items.append(item); seen.add(item["id"])
    return {"items": items, "categories": categories,
            "collections": [{"id": "curated", "name": "精选渠道"},
                            {"id": "aboutppt", "name": "AboutPPT 扩展"},
                            {"id": "all", "name": "全部渠道"}]}


def site_search(query="", category="", library=wf.LIBRARY, collection="all"):
    catalog = site_catalog(library)
    q = str(query).strip().casefold()
    if category and category not in {x["id"] for x in catalog["categories"]}:
        raise ValueError("unknown site category")
    if collection not in ("all", "curated", "aboutppt"):
        raise ValueError("unknown site collection")
    return [x for x in catalog["items"] if (collection == "all" or x["collection"] == collection) and
            (not category or x["group"] == category) and
            (not q or q in " ".join(str(x.get(k, "")) for k in
                                    ("name", "category", "description", "url")).casefold())]


def public_search(query, limit=12):
    query = str(query).strip()
    if not query or len(query) > 200:
        raise ValueError("请输入 1–200 字的检索词")
    params = dict(action="query", generator="search", gsrsearch=query, gsrnamespace=6,
                  gsrlimit=min(20, max(1, int(limit))), prop="imageinfo", iiprop="url|size",
                  iiurlwidth=600, format="json")
    url = "https://commons.wikimedia.org/w/api.php?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "MediagenLocalResourceBrowser/3.0"})
    try:
        with urlopen(req, timeout=12) as response:
            data = json.loads(response.read(4_000_000))
        if data.get("error"):
            raise ValueError(data["error"].get("info", "public search failed"))
        items = []
        for pg in data.get("query", {}).get("pages", {}).values():
            info = (pg.get("imageinfo") or [{}])[0]
            preview = info.get("thumburl", "")
            if urlsplit(preview).hostname not in ("upload.wikimedia.org", "thumb.wikimedia.org"):
                preview = ""
            items.append({"id": "commons-" + str(pg["pageid"]), "title": pg["title"],
                          "url": info.get("descriptionurl"), "preview_url": preview,
                          "width": info.get("width"), "height": info.get("height"),
                          "provider": "commons"})
        return {"status": "ok", "items": items, "query": query, "inference_performed": False}
    except Exception:
        # Do not leak network/proxy configuration, and never manufacture results.
        return {"status": "unavailable", "items": [], "query": query,
                "message": "公共检索暂不可达，请从网站入口收集后回传。", "inference_performed": False}


def safe_url(url):
    parsed = urlsplit(str(url).strip())
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("请提供不含凭据的 http(s) 资料链接")
    if len(url) > 4096:
        raise ValueError("URL too long")
    return url


def add_link(root, p, url, title="", usage="structure", comment=""):
    if usage not in assets.USAGES:
        raise ValueError("unknown usage")
    wf.reject_secrets({"url": url, "comment": comment})
    item = {"id": "link-" + uuid.uuid4().hex[:16], "url": safe_url(url),
            "title": title or urlsplit(url).hostname, "usage": usage, "comment": comment,
            "source_kind": "external_link", "collected_at": wf.now(), "model_allowed": False,
            "status": "awaiting_agent_review"}
    p["resource_cart"].append(item)
    wf.save(root, p)
    return item


def update(root, p, rid, patch=None, remove=False):
    item = next((x for x in p["resource_cart"] if x["id"] == rid), None)
    if not item:
        raise ValueError("cart item not found")
    if remove:
        p["resource_cart"] = [x for x in p["resource_cart"] if x["id"] != rid]
    else:
        patch = patch or {}
        if any(k not in ("usage", "comment", "title") for k in patch):
            raise ValueError("only cart usage/comment/title can be edited")
        if patch.get("usage", item["usage"]) not in assets.USAGES:
            raise ValueError("unknown usage")
        wf.reject_secrets(patch)
        item.update(patch)
    wf.save(root, p)
    return {"id": rid, "removed": remove}


def submit(root, p, stage="stage1", comment=""):
    if not p["resource_cart"]:
        raise ValueError("购物车为空，请先选择素材或添加网页资料")
    snapshot = copy.deepcopy(p["resource_cart"])
    return studio.create_draft(root, p, comment=comment or "请结合购物车重新推荐当前阶段方案",
                               stage=stage, submit=True, kind="resource_cart",
                               details={"cart_hash": wf.sha(snapshot), "items": snapshot})


def apply(root, p, request_id, decisions, summary, patch=None):
    """Agent-only resolution; browser cannot silently turn collection into production."""
    request = next((x for x in p["revision_requests"] if x["id"] == request_id), None)
    if not request or request.get("kind") != "resource_cart" or request["status"] not in ("draft", "submitted"):
        raise ValueError("pending cart submission required")
    if not summary.strip() or not isinstance(decisions, list):
        raise ValueError("alignment summary and per-resource decisions required")
    if request["details"]["cart_hash"] != wf.sha(p["resource_cart"]):
        raise ValueError("cart changed since submission; submit its latest version before applying")
    by_id = {x["id"]: x for x in request["details"]["items"]}
    result = []
    seen = set()
    for decision in decisions:
        rid = decision["id"]
        if rid not in by_id or rid in seen or not decision.get("reason", "").strip():
            raise ValueError("each decision must reference a unique submitted asset and explain its use")
        seen.add(rid)
        item = copy.deepcopy(by_id[rid])
        usage = decision.get("usage", item["usage"])
        if usage not in assets.USAGES:
            raise ValueError("unknown usage")
        if not decision.get("adopt", True):
            continue
        if item.get("path"):
            if wf.file_sha(item["path"]) != item["sha256"]:
                raise ValueError("pinned asset changed")
            item.update(usage=usage, model_allowed=bool(decision.get("model_allowed", False)),
                        borrow=decision["reason"])
            if item.get("protected_evidence") and item["model_allowed"]:
                raise ValueError("真实证据只能确定性合成，不能作为模型重画参考")
            if usage == "structure":
                item["model_allowed"] = False
            result.append(item)
        elif usage != "structure":
            raise ValueError("external URL is not an image: import the actual selected file before image use")
    if seen != set(by_id):
        raise ValueError("explicitly adopt or defer every submitted item")
    old = copy.deepcopy(p["asset_selection"])
    before = {pg["page_id"]: wf.page_design_hash(root, p, pg) for pg in p["pages"]}
    # Keep selections not in this shopping session; replace decisions only.
    p["asset_selection"] = [x for x in old if x["id"] not in by_id] + result
    try:
        resolved = studio.resolve(root, p, request_id, summary, replacement=patch, cart_review=True)
    except Exception:
        p["asset_selection"] = old
        raise
    resolved["resource_decisions"] = decisions
    resolved["impact"]["affected_pages"] = [pg["page_id"] for pg in p["pages"]
                                           if before.get(pg["page_id"]) != wf.page_design_hash(root, p, pg)]
    resolved["impact"]["preserved_pages"] = [pg["page_id"] for pg in p["pages"]
                                            if pg["page_id"] not in resolved["impact"]["affected_pages"]]
    wf.save(root, p)
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job")
    parser.add_argument("--library", type=Path, default=wf.LIBRARY)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("sites"); c.add_argument("--search", default=""); c.add_argument("--category", default="")
    c.add_argument("--collection", choices=("all", "curated", "aboutppt"), default="all")
    sub.add_parser("show")
    c = sub.add_parser("link"); c.add_argument("--url", required=True); c.add_argument("--comment", default="")
    c = sub.add_parser("submit"); c.add_argument("--stage", default="stage1"); c.add_argument("--comment", default="")
    c = sub.add_parser("apply"); c.add_argument("--id", required=True); c.add_argument("--decisions", required=True)
    c.add_argument("--summary", required=True); c.add_argument("--patch")
    args = parser.parse_args()
    try:
        if args.cmd == "sites":
            print(json.dumps({"items": site_search(args.search, args.category, args.library, args.collection),
                              "categories": site_catalog(args.library)["categories"]},
                             ensure_ascii=False, indent=2))
            return 0
        if not args.job:
            raise ValueError("--job required")
        p = wf.load(args.job)
        if args.cmd == "show": result = p["resource_cart"]
        elif args.cmd == "link": result = add_link(args.job, p, args.url, comment=args.comment)
        elif args.cmd == "submit": result = submit(args.job, p, args.stage, args.comment)
        else: result = apply(args.job, p, args.id, wf.read(args.decisions), args.summary,
                             wf.read(args.patch) if args.patch else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False)); return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
