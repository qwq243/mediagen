"""Explicit, bounded caching of public website favicons. No project data is sent."""
import argparse
import io
import ipaddress
import json
import socket
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
import requests
from PIL import Image
import ppt_cart as cart
import ppt_workflow as wf


def public_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
        raise ValueError("public http(s) URL required")
    for addr in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80)):
        if not ipaddress.ip_address(addr[4][0]).is_global:
            raise ValueError("non-public host rejected")
    return url


def get(url, limit, timeout=6):
    # Never provide a generic browser proxy. This helper is CLI-only and takes catalog sites.
    for _ in range(4):
        public_url(url)
        with requests.get(url, timeout=timeout, stream=True, allow_redirects=False,
                          headers={"User-Agent": "Mediagen-local-icon-cache/1.0"}) as r:
            if r.is_redirect:
                url = urllib.parse.urljoin(url, r.headers["Location"])
                continue
            r.raise_for_status()
            data = bytearray()
            for chunk in r.iter_content(16384):
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("icon/page size cap exceeded")
            return bytes(data), url
    raise ValueError("too many redirects")


class IconLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and "icon" in a.get("rel", "").lower() and a.get("href"):
            self.links.append(a["href"])


def cache(site, library):
    folder = Path(library) / "site-icons"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / (site["id"] + ".png")
    if dest.exists():
        return {"id": site["id"], "status": "cached"}
    candidates = [urllib.parse.urljoin(site["url"], "/favicon.ico")]
    errors = []
    for attempt in range(2):
        if attempt:
            try:
                data, base = get(site["url"], 1800000)
                parser = IconLinks(); parser.feed(data.decode("utf-8", errors="replace"))
                candidates = [urllib.parse.urljoin(base, x) for x in parser.links][:3]
            except Exception as e:
                errors.append(type(e).__name__)
                break
        for url in candidates:
            try:
                data, final = get(url, 1200000)
                with Image.open(io.BytesIO(data)) as im:
                    im.thumbnail((96, 96))
                    im.convert("RGBA").save(dest)
                result = {"id": site["id"], "status": "downloaded", "source": final,
                          "sha256": wf.file_sha(dest), "at": wf.now()}
                wf.write(folder / (site["id"] + ".json"), result)
                return result
            except Exception as e:
                errors.append(type(e).__name__)
    return {"id": site["id"], "status": "unavailable", "errors": errors}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library", type=Path, default=wf.LIBRARY)
    ap.add_argument("--ids", nargs="*", help="Registered site ids; default only curated collection")
    a = ap.parse_args()
    sites = [s for s in cart.site_catalog(a.library)["items"] if
             (s["id"] in a.ids if a.ids else s["collection"] == "curated")]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda s: cache(s, a.library), sites))
    wf.write(a.library / "site-icons" / "cache-report.json", results)
    print(json.dumps(results, ensure_ascii=False, indent=2))
