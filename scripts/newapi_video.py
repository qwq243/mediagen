#!/usr/bin/env python3
"""Submit / poll workstation sidecar video jobs (绘影).

Video is not a NewAPI image endpoint. This helper talks to
http://127.0.0.1:5278/api/studio/* with X-WS-Token from the sidecar
config. Never print the token.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

DEFAULT_SIDECAR = "http://127.0.0.1:5278"
CONFIG_CANDIDATES = [
    Path(r"D:\00\项目\日常\work\workstation\server\config.json"),
    Path(__file__).resolve().parents[4] / "work" / "workstation" / "server" / "config.json",
]
MODELS = ["seedance_v2.5", "seedance_v2.0", "seedance_v2.0_mini"]
SIZES = ["1280x720", "720x1280", "1024x1024"]
DURATIONS = {10, 15, 30}


def _load_sidecar() -> tuple[str, str]:
    for p in CONFIG_CANDIDATES:
        if not p.is_file():
            continue
        cfg = json.loads(p.read_text(encoding="utf-8"))
        token = str((cfg.get("auth") or {}).get("token") or "").strip()
        port = int(cfg.get("port") or 5278)
        if token:
            return f"http://127.0.0.1:{port}", token
    raise SystemExit("sidecar config / auth.token not found")


def _req(base: str, token: str, path: str, method: str = "GET", body: Optional[dict] = None, timeout: int = 40) -> dict[str, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "X-WS-Token": token,
            **({"Content-Type": "application/json; charset=utf-8"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise SystemExit(f"HTTP {err.code}: {raw[:300]}") from err
    except urllib.error.URLError as err:
        raise SystemExit(f"sidecar unreachable: {err.reason}") from err


def cmd_generate(args: argparse.Namespace) -> int:
    prompt = (args.prompt or "").strip()
    if not prompt:
        print("prompt required", file=sys.stderr)
        return 2
    duration = int(args.duration)
    if duration not in DURATIONS:
        print("duration must be 10, 15 or 30", file=sys.stderr)
        return 2
    payload = {
        "kind": "video",
        "prompt": prompt,
        "model": args.model,
        "size": args.size,
        "duration": duration,
        "upstream": args.upstream,
    }
    if args.reference:
        payload["referenceImages"] = [u.strip() for u in args.reference if u.strip()]
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    base, token = _load_sidecar()
    r = _req(base, token, "/api/studio/generate", method="POST", body=payload)
    item = r.get("item") or r
    if r.get("ok") is False:
        print(r.get("error") or "submit failed", file=sys.stderr)
        if r.get("hint"):
            print(r["hint"], file=sys.stderr)
        return 1
    print(json.dumps({"id": item.get("id"), "status": item.get("status"), "upstream": item.get("upstream"), "remote": item.get("remote")}, ensure_ascii=False, indent=2))
    if args.wait:
        return _poll(base, token, item.get("id"), args.wait)
    return 0


def _poll(base: str, token: str, item_id: str, wait_s: int) -> int:
    deadline = time.time() + wait_s
    while time.time() < deadline:
        r = _req(base, token, f"/api/studio/items?q={item_id}&limit=5")
        items = (r.get("items") if isinstance(r, dict) else None) or []
        hit = next((i for i in items if i.get("id") == item_id), None)
        if not hit:
            # list filter is keyword search; fall back to first page
            r = _req(base, token, "/api/studio/items?kind=video&limit=20")
            items = r.get("items") or []
            hit = next((i for i in items if i.get("id") == item_id), None)
        if hit:
            st = hit.get("status")
            print(f"{item_id} {st}", flush=True)
            if st in {"done", "failed"}:
                if hit.get("error"):
                    print(hit["error"], file=sys.stderr)
                    return 1
                files = hit.get("files") or []
                if files:
                    print(files[0].get("path"))
                return 0
        time.sleep(8)
    print("timed out waiting for video", file=sys.stderr)
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    base, token = _load_sidecar()
    if args.id:
        r = _req(base, token, "/api/studio/items?kind=video&limit=40")
        hit = next((i for i in (r.get("items") or []) if i.get("id") == args.id), None)
        if not hit:
            print(f"not found: {args.id}", file=sys.stderr)
            return 1
        print(json.dumps(hit, ensure_ascii=False, indent=2))
        return 0 if hit.get("status") != "failed" else 1
    snap = _req(base, token, "/api/videogen/status")
    safe = {
        "upstream": snap.get("upstream"),
        "upstreamLabel": snap.get("upstreamLabel"),
        "fallbackpConfigured": bool((snap.get("fallbackp") or {}).get("configured")),
        "dolaRunning": snap.get("running"),
        "dolaAccounts": len(snap.get("accounts") or []),
        "available": snap.get("available"),
    }
    print(json.dumps(safe, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Submit video jobs through the workstation sidecar (绘影).")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="Submit a video job")
    g.add_argument("--prompt", required=True)
    g.add_argument("--model", default=MODELS[0], choices=MODELS)
    g.add_argument("--size", default=SIZES[0], choices=SIZES)
    g.add_argument("--duration", type=int, default=10, choices=sorted(DURATIONS))
    g.add_argument("--upstream", default="fallbackp", choices=["fallbackp", "dolaPool"])
    g.add_argument("--reference", action="append", default=[], help="public http(s) image URL; repeatable")
    g.add_argument("--wait", type=int, default=0, help="seconds to poll; 0 = submit and exit")
    g.add_argument("--dry-run", action="store_true")
    g.set_defaults(func=cmd_generate)
    s = sub.add_parser("status", help="Sidecar video upstream status, or one library record")
    s.add_argument("--id", default="")
    s.set_defaults(func=cmd_status)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
