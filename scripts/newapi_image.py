#!/usr/bin/env python3
"""NewAPI image generation helper.

OpenAI-compatible image generation via a configurable NewAPI base URL.
Secrets are read only from environment variables; never hard-code API keys.

Connectivity: try a direct connection first; when the endpoint is unreachable
at the network layer (reset/timeout), automatically fall back to local
VPN/Clash proxy routes (NEWAPI_PROXY/env proxies, config.json "proxy", then a
TCP scan of common local proxy ports). Force one side with --proxy URL or
--no-proxy, or config.json "prefer_proxy": true.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_BASE_URL = "https://netcup-1.toapi.xyz/v1"
IMAGE_ENDPOINT = "/images/generations"
EDIT_ENDPOINT = "/images/edits"
VARIATIONS_ENDPOINT = "/images/variations"
MODELS_ENDPOINT = "/models"
_AUTO_CURL = object()

SIZE_PRESETS = {
    ("1k", "1:1"): "1024x1024",
    ("1k", "4:3"): "1365x1024",
    ("1k", "3:4"): "1024x1365",
    ("1k", "16:9"): "1920x1088",
    ("1k", "9:16"): "1088x1920",
    ("1k", "9:21"): "576x1344",
    ("1k", "21:9"): "1344x576",
    ("2k", "1:1"): "2048x2048",
    ("2k", "4:3"): "2048x1536",
    ("2k", "3:4"): "1536x2048",
    ("2k", "16:9"): "2560x1440",
    ("2k", "9:16"): "1440x2560",
    ("2k", "9:21"): "1088x2560",
    ("2k", "21:9"): "2560x1088",
    ("4k", "1:1"): "4096x4096",
    ("4k", "4:3"): "4096x3072",
    ("4k", "3:4"): "3072x4096",
    ("4k", "16:9"): "3840x2160",
    ("4k", "9:16"): "2160x3840",
    ("4k", "9:21"): "1648x3840",
    ("4k", "21:9"): "3840x1648",
}
CONVERT_FORMATS = {"png", "jpg", "jpeg", "webp", "avif", "gif", "bmp", "tiff"}
RATIO_ALIASES = {
    "square": "1024x1024",
    "1:1": "1024x1024",
    "landscape": "1536x1024",
    "3:2": "1536x1024",
    "16:9": "1536x1024",
    "4:3": "1536x1024",
    "portrait": "1024x1536",
    "2:3": "1024x1536",
    "9:16": "1024x1536",
    "3:4": "1024x1536",
}
RETRYABLE_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}
SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config.json"
DEFAULT_PROXY_PORTS = (12002, 7890, 7897, 10808, 10809, 2080, 8889, 1080, 33210, 12003)
PROBE_TIMEOUT = 8
PROBE_USER_AGENT = "Mozilla/5.0 Codex-NewAPI-ImageGen/2.0"


class TransportFailed(RuntimeError):
    """Network-layer failure (reset/timeout/DNS) on one transport route."""


def load_proxy_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return config if isinstance(config, dict) else {}


def describe_proxy(proxy: Optional[str]) -> str:
    return "direct" if proxy is None else str(proxy)


def opener_for(proxy: Optional[str]) -> urllib.request.OpenerDirector:
    if proxy and str(proxy).startswith(("socks4://", "socks5://", "socks5h://", "socks://")):
        try:
            import socks  # noqa: F401
        except ImportError:
            die(f"proxy {proxy} is SOCKS but PySocks is not installed; use an http:// proxy port")
    handler = urllib.request.ProxyHandler({} if proxy is None else {"http": str(proxy), "https": str(proxy)})
    return urllib.request.build_opener(handler)


def tcp_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_transport(proxy: Optional[str], health_url: str) -> bool:
    """True when the route reaches the endpoint at the network layer.

    Any HTTP status (including 401/403 without a key) proves reachability;
    only DNS/connection/TLS failures count as unusable.
    """
    request = urllib.request.Request(health_url, method="GET", headers={"User-Agent": PROBE_USER_AGENT})
    try:
        with opener_for(proxy).open(request, timeout=PROBE_TIMEOUT) as response:
            response.read(64)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, ConnectionResetError, TimeoutError, OSError):
        return False


def env_proxy_candidates() -> List[str]:
    found: List[str] = []
    configured = get_env("NEWAPI_PROXY", prefer_user=True)
    if configured:
        found.append(configured)
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        value = os.environ.get(name)
        if value:
            found.append(value)
    return found


def detect_local_proxies(config: Dict[str, Any], health_url: str) -> List[str]:
    """TCP-scan common local VPN/Clash ports, then keep ones that can
    actually complete an HTTPS request to the endpoint."""
    ports = config.get("proxy_ports") or DEFAULT_PROXY_PORTS
    working: List[str] = []
    for port in ports:
        candidate = f"http://127.0.0.1:{port}"
        if candidate in working:
            continue
        if not tcp_open(int(port)):
            continue
        if probe_transport(candidate, health_url):
            working.append(candidate)
    return working


def dedupe_keep_order(items: Iterable[Optional[str]]) -> List[str]:
    seen: set = set()
    unique: List[str] = []
    for item in items:
        if item is None:
            continue
        key = str(item)
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


@lru_cache(maxsize=8)
def build_proxy_routes(
    explicit_proxy: Optional[str],
    no_proxy: bool,
    prefer_proxy: bool,
    config_proxy: Optional[str],
    proxy_ports: Any,
    health_url: str,
) -> tuple:
    """Ordered proxy candidates; None means a direct connection.

    Cached per (route inputs, health URL) so a batch run scans ports once.
    ``proxy_ports`` must be a tuple (hashable); use :func:`proxy_routes_for`.
    """
    if explicit_proxy:
        return (explicit_proxy,)
    if no_proxy:
        return (None,)
    ports = tuple(int(p) for p in proxy_ports) if proxy_ports else None
    proxies = dedupe_keep_order(env_proxy_candidates() + [config_proxy] + detect_local_proxies({"proxy_ports": ports}, health_url))
    if prefer_proxy:
        return tuple(proxies) + (None,)
    return (None,) + tuple(proxies)


def proxy_routes_for(url: str, proxy: Optional[str] = None, no_proxy: bool = False) -> tuple:
    """build_proxy_routes with values from config.json; safe to call directly."""
    return build_proxy_routes(
        proxy,
        no_proxy,
        bool(PROXY_CONFIG.get("prefer_proxy")),
        PROXY_CONFIG.get("proxy"),
        tuple(PROXY_CONFIG.get("proxy_ports") or ()),
        health_url_for(url),
    )


PROXY_CONFIG = load_proxy_config()


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def get_env(name: str, prefer_user: bool = False) -> Optional[str]:
    process_val = os.environ.get(name)
    user_val: Optional[str] = None
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                reg_val, _ = winreg.QueryValueEx(key, name)
                if reg_val:
                    user_val = str(reg_val)
        except Exception:
            user_val = None
    if prefer_user and user_val:
        return user_val
    return process_val or user_val


def normalize_base_url(base_url: Optional[str]) -> str:
    url = (
        base_url
        or get_env("NEWAPI_BASE_URL", prefer_user=True)
        or get_env("TOAPI_BASE_URL", prefer_user=True)
        or DEFAULT_BASE_URL
    ).strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        die("base URL must start with http:// or https://")
    # The configured value is an API base. Accept a bare host for compatibility,
    # but normalize it to one and only one /v1 suffix.
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def get_api_key() -> str:
    key = (
        get_env("NEWAPI_API_KEY", prefer_user=True)
        or get_env("TOAPI_API_KEY", prefer_user=True)
        or get_env("OPENAI_API_KEY", prefer_user=True)
    )
    if not key:
        die("NEWAPI_API_KEY is not set. Set it in the environment; do not hard-code secrets in prompts or skill files.")
    return key


def resolve_size(size: Optional[str], tier: Optional[str], aspect: Optional[str]) -> str:
    if size:
        return size
    # generate-image style ratio aliases map to the nearest native size.
    if aspect and aspect in RATIO_ALIASES and not tier:
        return RATIO_ALIASES[aspect]
    if bool(tier) != bool(aspect):
        die("--tier and --aspect must be provided together (or use a ratio alias such as --ratio 16:9)")
    if tier and aspect:
        key = (tier.lower(), aspect)
        if key in SIZE_PRESETS:
            return SIZE_PRESETS[key]
        die(f"unknown size preset: tier={tier} aspect={aspect}")
    return "1024x1024"


def collect_image_items(value: Any) -> List[Dict[str, Any]]:
    """Collect image result objects from common JSON and SSE event shapes."""
    found: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("url") or value.get("b64_json"):
            found.append(value)
        for key in ("data", "result", "output", "outputs", "image", "images"):
            if key in value:
                found.extend(collect_image_items(value[key]))
    elif isinstance(value, list):
        for item in value:
            found.extend(collect_image_items(item))
    return found


def dedupe_image_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        identity = item.get("url") or item.get("b64_json")
        if not identity or identity in seen:
            continue
        seen.add(identity)
        unique.append(item)
    return unique


def parse_api_response(raw: str, url: str, expect_stream: bool = False) -> Dict[str, Any]:
    stripped = raw.strip()
    # Some gateways ignore stream=true and return ordinary JSON. Accept that
    # response even when the caller asked for SSE.
    if stripped.startswith(("{", "[")):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    is_sse = expect_stream or stripped.startswith("data:") or "\ndata:" in stripped
    if not is_sse:
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            die(f"non-JSON response from {url}: {stripped[:500]}")
        if not isinstance(parsed, dict):
            die(f"unexpected JSON response from {url}: {stripped[:500]}")
        return parsed

    events: List[Any] = []
    for line in raw.splitlines():
        payload = line.strip()
        if not payload or payload.startswith(":") or payload.startswith("event:"):
            continue
        if payload.startswith("data:"):
            payload = payload[5:].strip()
        if payload == "[DONE]":
            continue
        if not payload.startswith(("{", "[")):
            continue
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    final_groups: List[List[Dict[str, Any]]] = []
    fallback_groups: List[List[Dict[str, Any]]] = []
    for event in events:
        group = collect_image_items(event)
        if not group:
            continue
        event_type = str(event.get("type", "")).lower() if isinstance(event, dict) else ""
        is_partial = "partial" in event_type or any("partial_image_index" in item for item in group)
        (fallback_groups if is_partial else final_groups).append(group)
    final_group = next((group for group in reversed(final_groups) if group), None)
    if final_group is None:
        final_group = next((group for group in reversed(fallback_groups) if group), [])
    items = dedupe_image_items(final_group)
    if items:
        return {"data": items, "stream_events": len(events)}
    if events and isinstance(events[-1], dict):
        return events[-1]
    die(f"stream response from {url} did not contain JSON image data: {stripped[:500]}")
    return {}


def select_transport(
    requested: str,
    platform_name: Optional[str] = None,
    curl_path: Any = _AUTO_CURL,
) -> str:
    """Choose a request transport without exposing credentials in command logs."""
    if requested not in {"auto", "curl", "urllib"}:
        die(f"unsupported transport: {requested}")
    if requested != "auto":
        detected_curl = shutil.which("curl") if curl_path is _AUTO_CURL else curl_path
        if requested == "curl" and not detected_curl:
            die("curl transport requested but curl was not found")
        return requested
    platform_name = platform_name or os.name
    curl_path = shutil.which("curl") if curl_path is _AUTO_CURL else curl_path
    if platform_name == "nt" and curl_path:
        return "curl"
    return "urllib"


def _curl_config_quote(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def build_curl_request(
    method: str,
    url: str,
    api_key: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 180,
    stream: bool = False,
    curl_path: Optional[str] = None,
    content_type: Optional[str] = None,
    data_file: Optional[str] = None,
    proxy: Optional[str] = None,
) -> tuple[List[str], str]:
    """Build curl command/config; keep the bearer token out of process arguments."""
    curl_path = curl_path or shutil.which("curl")
    if not curl_path:
        die("curl transport requested but curl was not found")
    accept = "text/event-stream, application/json" if stream else "application/json"
    lines = [
        f'url = "{_curl_config_quote(url)}"',
        f'request = "{_curl_config_quote(method.upper())}"',
        "http1.1",
        "silent",
        "show-error",
        f'max-time = "{int(timeout)}"',
        'connect-timeout = "30"',
        'user-agent = "Mozilla/5.0 Codex-NewAPI-ImageGen/2.0"',
        f'header = "Authorization: Bearer {_curl_config_quote(api_key)}"',
        f'header = "Content-Type: {_curl_config_quote(content_type or "application/json")}"',
        f'header = "Accept: {_curl_config_quote(accept)}"',
        'write-out = "\\n__NEWAPI_HTTP_CODE__:%{http_code}"',
    ]
    if proxy:
        lines.append(f'proxy = "{_curl_config_quote(str(proxy))}"')
    if stream:
        lines.append("no-buffer")
    if data_file is not None:
        lines.append(f'data-binary = "@{_curl_config_quote(data_file)}"')
    elif payload is not None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        lines.append(f'data-binary = "{_curl_config_quote(body)}"')
    return [curl_path, "--config", "-"], "\n".join(lines) + "\n"


def retry_delay(attempt: int) -> float:
    return min(30.0, float(2 ** max(0, attempt - 1)))


def curl_status(raw: str) -> Optional[int]:
    marker = "\n__NEWAPI_HTTP_CODE__:"
    if marker not in raw:
        return None
    try:
        return int(raw.rsplit(marker, 1)[1].strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


def parse_curl_response(raw: str, url: str, expect_stream: bool = False) -> Dict[str, Any]:
    marker = "\n__NEWAPI_HTTP_CODE__:"
    if marker not in raw:
        die(f"curl response from {url} did not include an HTTP status marker: {raw[:500]}")
    body, status_raw = raw.rsplit(marker, 1)
    try:
        status = int(status_raw.strip().splitlines()[0])
    except (ValueError, IndexError):
        die(f"invalid HTTP status from {url}: {status_raw[:100]}")
    if status >= 400 or status == 0:
        die(f"HTTP {status} from {url}: {body.strip()[:800]}")
    return parse_api_response(body, url, expect_stream=expect_stream)


def request_json_curl(
    method: str,
    url: str,
    api_key: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 180,
    stream: bool = False,
    retries: int = 3,
    proxy: Optional[str] = None,
) -> Dict[str, Any]:
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        command, config = build_curl_request(method, url, api_key, payload, timeout, stream, proxy=proxy)
        try:
            completed = subprocess.run(
                command,
                input=config,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout + 15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            if attempt < attempts:
                warn(f"curl request timed out via {describe_proxy(proxy)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s")
                time.sleep(retry_delay(attempt))
                continue
            raise TransportFailed(f"curl request timed out after {timeout} seconds via {describe_proxy(proxy)}: {url}") from None
        status = curl_status(completed.stdout)
        if status in RETRYABLE_HTTP_STATUS or status == 0 or (
            completed.returncode != 0 and status is None
        ):
            if attempt < attempts:
                detail = completed.stderr.strip()[:240] or f"HTTP {status or 'network'}"
                warn(f"{detail} via {describe_proxy(proxy)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s")
                time.sleep(retry_delay(attempt))
                continue
        # curl writes http_code 000 (parsed as 0) when the network layer fails
        # before any HTTP status; treat it like a missing status so the caller
        # can fall back to the next proxy route instead of dying here.
        if completed.returncode != 0 and (status is None or status == 0):
            raise TransportFailed(
                f"curl request failed via {describe_proxy(proxy)} ({completed.returncode}) for {url}: {completed.stderr.strip()[:800]}"
            )
        return parse_curl_response(completed.stdout, url, expect_stream=stream)
    raise TransportFailed(f"curl request failed after {attempts} attempts via {describe_proxy(proxy)}: {url}")


def request_json(
    method: str,
    url: str,
    api_key: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 180,
    stream: bool = False,
    retries: int = 3,
    proxy: Optional[str] = None,
) -> Dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method.upper())
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream, application/json" if stream else "application/json")
    opener = opener_for(proxy)
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return parse_api_response(raw, url, expect_stream=stream)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code in RETRYABLE_HTTP_STATUS and attempt < attempts:
                warn(f"HTTP {exc.code} via {describe_proxy(proxy)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s")
                time.sleep(retry_delay(attempt))
                continue
            die(f"HTTP {exc.code} from {url}: {raw[:800]}")
        except urllib.error.URLError as exc:
            if attempt < attempts:
                warn(f"request failed via {describe_proxy(proxy)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s: {exc}")
                time.sleep(retry_delay(attempt))
                continue
            raise TransportFailed(f"request failed via {describe_proxy(proxy)}: {exc}") from None
        except (ConnectionResetError, TimeoutError, OSError) as exc:
            if attempt < attempts:
                warn(f"network failure via {describe_proxy(proxy)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s: {exc}")
                time.sleep(retry_delay(attempt))
                continue
            raise TransportFailed(f"network failure via {describe_proxy(proxy)}: {exc}") from None
    raise TransportFailed(f"request failed after {attempts} attempts via {describe_proxy(proxy)}: {url}")


def health_url_for(url: str) -> str:
    """Derive the probe URL (GET /v1/models) from any API endpoint URL."""
    parsed = urllib.parse.urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}/v1/models"


def request_with_transport(
    method: str,
    url: str,
    api_key: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 180,
    stream: bool = False,
    transport: str = "auto",
    retries: int = 3,
    proxy: Optional[str] = None,
    no_proxy: bool = False,
) -> Dict[str, Any]:
    selected = select_transport(transport)
    routes = proxy_routes_for(url, proxy, no_proxy)
    from image_call_budget import reserve_from_environment
    if reserve_from_environment(method, url):
        # One ledger reservation is exactly one outbound attempt. A timeout
        # may already have incurred cost; do not retry through another route.
        retries, routes = 1, routes[:1]
    errors: List[str] = []
    for route in routes:
        try:
            if selected == "curl":
                return request_json_curl(method, url, api_key, payload, timeout, stream, retries, proxy=route)
            return request_json(method, url, api_key, payload, timeout, stream, retries, proxy=route)
        except TransportFailed as exc:
            errors.append(str(exc))
            warn(f"transport route failed: {exc}; trying next route" if len(routes) > 1 else f"transport route failed: {exc}")
    die(
        "all transport routes failed (direct + proxy candidates):\n  "
        + "\n  ".join(errors)
    )
    return {}


def request_multipart_curl(
    method: str,
    url: str,
    api_key: str,
    body: bytes,
    content_type: str,
    timeout: int = 180,
    stream: bool = False,
    retries: int = 3,
    proxy: Optional[str] = None,
) -> Dict[str, Any]:
    """Send multipart data without putting the image bytes in argv or config."""
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        temp_name: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(prefix="codex-newapi-upload-", suffix=".bin", delete=False) as handle:
                handle.write(body)
                temp_name = handle.name
            command, config = build_curl_request(
                method,
                url,
                api_key,
                payload=None,
                timeout=timeout,
                stream=stream,
                content_type=content_type,
                data_file=temp_name,
                proxy=proxy,
            )
            try:
                completed = subprocess.run(
                    command,
                    input=config,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout + 15,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                if attempt < attempts:
                    warn(f"curl multipart request timed out via {describe_proxy(proxy)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s")
                    time.sleep(retry_delay(attempt))
                    continue
                raise TransportFailed(f"curl multipart request timed out after {timeout} seconds via {describe_proxy(proxy)}: {url}") from None
            status = curl_status(completed.stdout)
            if status in RETRYABLE_HTTP_STATUS or status == 0 or (
                completed.returncode != 0 and status is None
            ):
                if attempt < attempts:
                    detail = completed.stderr.strip()[:240] or f"HTTP {status or 'network'}"
                    warn(f"{detail} via {describe_proxy(proxy)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s")
                    time.sleep(retry_delay(attempt))
                    continue
            if completed.returncode != 0 and (status is None or status == 0):
                raise TransportFailed(
                    f"curl multipart request failed via {describe_proxy(proxy)} ({completed.returncode}) for {url}: {completed.stderr.strip()[:800]}"
                )
            return parse_curl_response(completed.stdout, url, expect_stream=stream)
        finally:
            if temp_name:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except TypeError:
                    temp_path = Path(temp_name)
                    if temp_path.exists():
                        temp_path.unlink()
    raise TransportFailed(f"curl multipart request failed after {attempts} attempts via {describe_proxy(proxy)}: {url}")


def request_multipart_urllib(
    method: str,
    url: str,
    api_key: str,
    body: bytes,
    content_type: str,
    timeout: int = 180,
    stream: bool = False,
    retries: int = 3,
    proxy: Optional[str] = None,
) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=body, method=method.upper())
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", content_type)
    req.add_header("Accept", "text/event-stream, application/json" if stream else "application/json")
    opener = opener_for(proxy)
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return parse_api_response(raw, url, expect_stream=stream)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code in RETRYABLE_HTTP_STATUS and attempt < attempts:
                warn(f"HTTP {exc.code} via {describe_proxy(proxy)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s")
                time.sleep(retry_delay(attempt))
                continue
            die(f"HTTP {exc.code} from {url}: {raw[:800]}")
        except urllib.error.URLError as exc:
            if attempt < attempts:
                warn(f"request failed via {describe_proxy(proxy)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s: {exc}")
                time.sleep(retry_delay(attempt))
                continue
            raise TransportFailed(f"request failed via {describe_proxy(proxy)}: {exc}") from None
        except (ConnectionResetError, TimeoutError, OSError) as exc:
            if attempt < attempts:
                warn(f"network failure via {describe_proxy(proxy)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s: {exc}")
                time.sleep(retry_delay(attempt))
                continue
            raise TransportFailed(f"network failure via {describe_proxy(proxy)}: {exc}") from None
    raise TransportFailed(f"multipart request failed after {attempts} attempts via {describe_proxy(proxy)}: {url}")


def request_multipart_with_transport(
    method: str,
    url: str,
    api_key: str,
    body: bytes,
    content_type: str,
    timeout: int = 180,
    stream: bool = False,
    transport: str = "auto",
    retries: int = 3,
    proxy: Optional[str] = None,
    no_proxy: bool = False,
) -> Dict[str, Any]:
    selected = select_transport(transport)
    routes = proxy_routes_for(url, proxy, no_proxy)
    from image_call_budget import reserve_from_environment
    if reserve_from_environment(method, url):
        retries, routes = 1, routes[:1]
    errors: List[str] = []
    for route in routes:
        try:
            if selected == "curl":
                return request_multipart_curl(method, url, api_key, body, content_type, timeout, stream, retries, proxy=route)
            return request_multipart_urllib(method, url, api_key, body, content_type, timeout, stream, retries, proxy=route)
        except TransportFailed as exc:
            errors.append(str(exc))
            warn(f"transport route failed: {exc}; trying next route" if len(routes) > 1 else f"transport route failed: {exc}")
    die(
        "all transport routes failed (direct + proxy candidates):\n  "
        + "\n  ".join(errors)
    )
    return {}


def slugify(text: str, fallback: str = "image") -> str:
    text = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", text.strip()).strip("-")
    return (text[:80] or fallback)


def content_type_for_path(path: Path) -> str:
    ctype, _ = mimetypes.guess_type(str(path))
    return ctype or "application/octet-stream"


class MultipartBuilder:
    def __init__(self) -> None:
        self.boundary = f"----CodexNewApiImageGen{int(time.time() * 1000)}"
        self.parts: List[bytes] = []

    def add_field(self, name: str, value: str) -> None:
        self.parts.append(
            (
                f"--{self.boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    def add_file(self, name: str, path: Path) -> None:
        self.parts.append(
            (
                f"--{self.boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
                f"Content-Type: {content_type_for_path(path)}\r\n\r\n"
            ).encode("utf-8")
            + path.read_bytes()
            + b"\r\n"
        )

    def build(self) -> tuple[bytes, str]:
        body = b"".join(self.parts) + f"--{self.boundary}--\r\n".encode("utf-8")
        return body, f"multipart/form-data; boundary={self.boundary}"


def download_bytes(
    url: str,
    timeout: int = 180,
    transport: str = "auto",
    retries: int = 3,
    proxy: Optional[str] = None,
    no_proxy: bool = False,
) -> bytes:
    """Download image bytes, falling back across proxy routes like the API
    requests do (the image CDN host may need a different route than the API)."""
    selected = select_transport(transport)
    routes = proxy_routes_for(url, proxy, no_proxy)
    attempts = max(1, retries)
    errors: List[str] = []
    if selected == "curl":
        curl_path = shutil.which("curl") or "curl"
        for route in routes:
            for attempt in range(1, attempts + 1):
                command = [curl_path, "--location", "--fail", "--silent", "--show-error"]
                if route:
                    command.extend(["--proxy", str(route)])
                command.extend([
                    "--retry",
                    str(max(0, attempts - 1)),
                    "--retry-all-errors",
                    "--max-time",
                    str(timeout),
                    url,
                ])
                completed = subprocess.run(command, capture_output=True, check=False)
                if completed.returncode == 0:
                    return completed.stdout
                errors.append(f"{describe_proxy(route)} attempt {attempt}: curl {completed.returncode}")
                if attempt < attempts:
                    warn(f"image download failed via {describe_proxy(route)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s")
                    time.sleep(retry_delay(attempt))
                    continue
        die(f"image download failed ({url}):\n  " + "\n  ".join(errors))
    for route in routes:
        for attempt in range(1, attempts + 1):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Codex-NewAPI-ImageGen/2.0"})
                with opener_for(route).open(request, timeout=timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                errors.append(f"{describe_proxy(route)} attempt {attempt}: HTTP {exc.code}")
                if exc.code in RETRYABLE_HTTP_STATUS and attempt < attempts:
                    warn(f"image download HTTP {exc.code} via {describe_proxy(route)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s")
                    time.sleep(retry_delay(attempt))
                    continue
                die(f"image download HTTP {exc.code}: {detail[:800]}")
            except (urllib.error.URLError, ConnectionResetError, TimeoutError, OSError) as exc:
                errors.append(f"{describe_proxy(route)} attempt {attempt}: {exc}")
                if attempt < attempts:
                    warn(f"image download failed via {describe_proxy(route)}; retry {attempt}/{attempts} after {retry_delay(attempt):g}s: {exc}")
                    time.sleep(retry_delay(attempt))
                    continue
    die(f"image download failed for {url}:\n  " + "\n  ".join(errors))
    return b""


def sniff_image_ext(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8"):
        return "jpg"
    if raw.startswith(b"GIF8"):
        return "gif"
    if raw.startswith(b"BM"):
        return "bmp"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "webp"
    if len(raw) >= 12 and raw[4:8] == b"ftyp" and raw[8:12] in {b"avif", b"avis"}:
        return "avif"
    if raw.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    return "bin"


def find_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def convert_with_ffmpeg(src: Path, dst: Path, quality: Optional[int] = None) -> None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        die("ffmpeg is required for image format conversion; use --output-format png or install ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if quality is not None and dst.suffix.lower() in {".jpg", ".jpeg", ".webp"}:
        command.extend(["-q:v", str(max(1, min(31, round((100 - quality) / 3.3))))])
    command.append(str(dst))
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        die(f"ffmpeg convert failed: {completed.stderr[:800]}")


def decode_image_item(
    item: Dict[str, Any],
    out_path: Path,
    transport: str = "auto",
    convert_to: Optional[str] = None,
    convert_quality: Optional[int] = None,
    retries: int = 3,
    keep_original: bool = False,
    proxy: Optional[str] = None,
    no_proxy: bool = False,
) -> Path:
    if item.get("b64_json"):
        encoded = item["b64_json"]
        if encoded.startswith("data:") and "," in encoded:
            encoded = encoded.split(",", 1)[1]
        raw = base64.b64decode(encoded)
    elif item.get("url"):
        raw = download_bytes(item["url"], timeout=180, transport=transport, retries=retries, proxy=proxy, no_proxy=no_proxy)
    else:
        die("image response item did not contain b64_json or url")
        return out_path

    out_path.parent.mkdir(parents=True, exist_ok=True)
    source_ext = sniff_image_ext(raw)
    if keep_original:
        target_ext = source_ext if source_ext != "bin" else (out_path.suffix.lstrip(".") or "bin")
    else:
        target_ext = (convert_to or out_path.suffix.lstrip(".") or source_ext).lower()
    target_ext = "jpg" if target_ext == "jpeg" else target_ext
    if target_ext not in CONVERT_FORMATS and target_ext != source_ext:
        die(f"unsupported local image format: {target_ext}")
    final_path = out_path
    if final_path.suffix.lower().lstrip(".") != target_ext and target_ext != "bin":
        final_path = final_path.with_suffix("." + target_ext)
    if not keep_original and target_ext != source_ext:
        with tempfile.TemporaryDirectory(prefix="codex-newapi-image-") as temp_dir:
            src = Path(temp_dir) / f"source.{source_ext if source_ext != 'bin' else 'img'}"
            src.write_bytes(raw)
            convert_with_ffmpeg(src, final_path, quality=convert_quality)
    else:
        final_path.write_bytes(raw)
    return final_path


def image_info(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "bytes": 0,
        "format": None,
        "width": None,
        "height": None,
    }
    if not path.exists():
        return info
    info["bytes"] = path.stat().st_size
    if info["bytes"] <= 0:
        return info
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        info["format"] = "png"
        info["width"], info["height"] = struct.unpack(">II", data[16:24])
        return info
    if data.startswith(b"\xff\xd8"):
        info["format"] = "jpeg"
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            offset += 2
            if marker in (0xD8, 0xD9):
                continue
            if offset + 2 > len(data):
                break
            seg_len = struct.unpack(">H", data[offset:offset + 2])[0]
            if seg_len < 2 or offset + seg_len > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                info["height"], info["width"] = struct.unpack(">HH", data[offset + 3:offset + 7])
                return info
            offset += seg_len
        return info
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        info["format"] = "webp"
        if data[12:16] == b"VP8X" and len(data) >= 30:
            info["width"] = 1 + int.from_bytes(data[24:27], "little")
            info["height"] = 1 + int.from_bytes(data[27:30], "little")
        return info
    return info


def build_payload(args: argparse.Namespace, prompt: str) -> Dict[str, Any]:
    stream = bool(getattr(args, "stream", False))
    # --ratio alias feeds the same resolver as --aspect when no tier preset is used.
    aspect = getattr(args, "aspect", None) or getattr(args, "ratio_alias", None)
    size = getattr(args, "size", None)
    payload: Dict[str, Any] = {
        "model": args.model,
        "prompt": prompt,
        "n": args.n,
        "size": resolve_size(size, getattr(args, "tier", None), aspect),
        "stream": stream,
    }
    optional = {
        "quality": args.quality,
        "style": args.style,
        "response_format": args.response_format,
        "output_format": args.output_format,
        "output_compression": args.output_compression,
        "background": args.background or ("transparent" if getattr(args, "transparent", False) else None),
        "moderation": args.moderation,
    }
    payload.update({k: v for k, v in optional.items() if v is not None})
    partial_images = getattr(args, "partial_images", None)
    if stream and partial_images is not None and int(partial_images) > 0:
        payload["partial_images"] = int(partial_images)
    if args.extra:
        for raw in args.extra:
            if "=" not in raw:
                die(f"--extra must be key=value, got: {raw}")
            k, v = raw.split("=", 1)
            try:
                payload[k] = json.loads(v)
            except json.JSONDecodeError:
                payload[k] = v
    # These configured image channels reject the OpenAI quality field. Keep
    # requested resolution/output format; this is not a quality downgrade.
    if args.model in ("nana-banana-2.1", "nano-banana-pro"):
        payload.pop("quality", None)
    return {k: v for k, v in payload.items() if v is not None}


def multipart_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def build_multipart_payload(args: argparse.Namespace, mode: str, prompt: str = "") -> tuple[bytes, str]:
    images = args.image if isinstance(args.image, list) else [args.image]
    image_paths = [Path(p) for p in images]
    for _p in image_paths:
        if not _p.is_file():
            die(f"image not found: {_p}")
    builder = MultipartBuilder()
    payload = build_payload(args, prompt)
    if mode == "variation":
        payload.pop("prompt", None)
    for key, value in payload.items():
        builder.add_field(key, multipart_value(value))
    if len(image_paths) == 1:
        builder.add_file("image", image_paths[0])
    else:
        # 多参考图：OpenAI 的 edits 接口用 image[] 数组字段（最多 16 张）
        for _p in image_paths:
            builder.add_file("image[]", _p)
    if mode == "edit" and getattr(args, "mask", None):
        mask_path = Path(args.mask)
        if not mask_path.is_file():
            die(f"mask not found: {mask_path}")
        builder.add_file("mask", mask_path)
    return builder.build()


def read_prompt(args: argparse.Namespace, required: bool = True) -> str:
    prompt = getattr(args, "prompt", None)
    prompt_file = getattr(args, "prompt_file", None)
    if prompt_file:
        prompt = Path(prompt_file).read_text(encoding="utf-8")
    prompt = (prompt or "").strip()
    if required and not prompt:
        die("prompt is required")
    return prompt


def local_convert_format(args: argparse.Namespace, out: Path) -> Optional[str]:
    if getattr(args, "keep_original", False):
        return None
    requested = getattr(args, "convert", None) or out.suffix.lstrip(".") or getattr(args, "ext", "png")
    requested = requested.lower().lstrip(".")
    if requested == "jpeg":
        requested = "jpg"
    if requested not in CONVERT_FORMATS:
        die(f"unsupported local image format: {requested}")
    return requested


def safe_batch_output(root: Path, out_name: str) -> Path:
    relative = Path(str(out_name))
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        die(f"batch output must stay under --out-dir: {out_name}")
    root_resolved = root.resolve()
    candidate = (root_resolved / relative).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        die(f"batch output must stay under --out-dir: {out_name}")
    return candidate


def cmd_models(args: argparse.Namespace) -> int:
    base = normalize_base_url(args.base_url)
    data = request_with_transport(
        "GET",
        base + MODELS_ENDPOINT,
        get_api_key(),
        timeout=args.timeout,
        transport=args.transport,
        proxy=getattr(args, "proxy", None),
        no_proxy=getattr(args, "no_proxy", False),
    )
    models = data.get("data", []) if isinstance(data, dict) else []
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    for m in models:
        mid = m.get("id") if isinstance(m, dict) else str(m)
        if args.filter and args.filter.lower() not in mid.lower():
            continue
        print(mid)
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    prompt = read_prompt(args)
    base = normalize_base_url(args.base_url)
    payload = build_payload(args, prompt)
    requested_ext = (args.convert or args.ext or "png").lower().lstrip(".") if not args.keep_original else (args.ext or "png")
    if requested_ext == "jpeg":
        requested_ext = "jpg"
    out = Path(args.out or f"{slugify(prompt)}.{requested_ext}")
    convert_to = local_convert_format(args, out)
    if args.dry_run:
        print(json.dumps({"url": base + IMAGE_ENDPOINT, "out": str(out), "convert_to": convert_to, "payload": payload}, ensure_ascii=False, indent=2))
        return 0
    import image_recipe
    recipe = image_recipe.begin(out, "generate", payload, postprocessing={
        "convert_to": convert_to, "convert_quality": args.convert_quality, "keep_original": args.keep_original})
    try:
        data = request_with_transport(
            "POST",
            base + IMAGE_ENDPOINT,
            get_api_key(),
            payload,
            timeout=args.timeout,
            stream=args.stream,
            transport=args.transport,
            retries=args.retries,
            proxy=getattr(args, "proxy", None),
            no_proxy=getattr(args, "no_proxy", False),
        )
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            die(f"unexpected image response: {json.dumps(data, ensure_ascii=False)[:800]}")
        outputs = []
        for idx, item in enumerate(items, start=1):
            target = out
            if len(items) > 1:
                target = out.with_name(f"{out.stem}-{idx}{out.suffix}")
            outputs.append(
                str(
                    decode_image_item(
                        item,
                        target,
                        args.transport,
                        convert_to=convert_to,
                        convert_quality=args.convert_quality,
                        retries=args.retries,
                        keep_original=args.keep_original,
                        proxy=getattr(args, "proxy", None),
                        no_proxy=getattr(args, "no_proxy", False),
                    )
                )
            )
        image_recipe.finish(recipe, outputs, data)
    except BaseException:
        image_recipe.failed(recipe)
        raise
    print(json.dumps({"outputs": outputs, "recipe_path": recipe["recipe_path"]}, ensure_ascii=False, indent=2))
    return 0


def read_batch_jobs(path: str) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    input_path = Path(path)
    if not input_path.exists():
        die(f"batch input does not exist: {input_path}")
    for line_no, raw in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            die(f"invalid JSONL at line {line_no}: {exc}")
        if isinstance(item, str):
            item = {"prompt": item}
        if not isinstance(item, dict) or not item.get("prompt"):
            die(f"batch line {line_no} must be an object with prompt")
        jobs.append(item)
    if not jobs:
        die("batch input has no jobs")
    return jobs


def cmd_batch(args: argparse.Namespace) -> int:
    jobs = read_batch_jobs(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = normalize_base_url(args.base_url)
    api_key = None if args.dry_run else get_api_key()
    outputs: List[str] = []
    for idx, job in enumerate(jobs, start=1):
        prompt = str(job["prompt"]).strip()
        # Job-level values override CLI defaults.
        local = argparse.Namespace(**vars(args))
        for k, v in job.items():
            if hasattr(local, k):
                setattr(local, k, v)
        payload = build_payload(local, prompt)
        out_name = job.get("out") or f"{idx:03d}-{slugify(prompt)}.{local.convert or local.ext}"
        out_path = safe_batch_output(out_dir, str(out_name))
        convert_to = local_convert_format(local, out_path)
        if args.dry_run:
            print(json.dumps({"job": idx, "url": base + IMAGE_ENDPOINT, "out": str(out_path), "convert_to": convert_to, "payload": payload}, ensure_ascii=False))
            continue
        try:
            shown = out_path.relative_to(out_dir)
        except ValueError:
            # --out-dir 给的是相对路径时 resolve 过再比，否则这里会 ValueError 把整批带崩
            shown = out_path.relative_to(Path(out_dir).resolve())
        print(f"[{idx}/{len(jobs)}] generating {shown}", file=sys.stderr)
        data = request_with_transport(
            "POST",
            base + IMAGE_ENDPOINT,
            api_key or "",
            payload,
            timeout=args.timeout,
            stream=local.stream,
            transport=local.transport,
            retries=local.retries,
            proxy=local.proxy,
            no_proxy=local.no_proxy,
        )
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            die(f"unexpected image response for job {idx}: {json.dumps(data, ensure_ascii=False)[:800]}")
        outputs.append(
            str(
                decode_image_item(
                    items[0],
                    out_path,
                    local.transport,
                    convert_to=convert_to,
                    convert_quality=local.convert_quality,
                    retries=local.retries,
                    keep_original=local.keep_original,
                    proxy=local.proxy,
                    no_proxy=local.no_proxy,
                )
            )
        )
        if args.sleep > 0 and idx < len(jobs):
            time.sleep(args.sleep)
    if not args.dry_run:
        print(json.dumps({"outputs": outputs}, ensure_ascii=False, indent=2))
    return 0


def cmd_edit_or_variation(args: argparse.Namespace) -> int:
    mode = "edit" if args.cmd == "edit" else "variation"
    prompt = read_prompt(args, required=mode == "edit")
    base = normalize_base_url(args.base_url)
    body, content_type = build_multipart_payload(args, mode, prompt)
    endpoint = EDIT_ENDPOINT if mode == "edit" else VARIATIONS_ENDPOINT
    if args.out:
        out = Path(args.out)
    else:
        _first_image = args.image[0] if isinstance(args.image, list) else args.image
        stem = slugify(prompt or Path(_first_image).stem)
        out = Path(f"{stem}.{args.convert or args.ext or 'png'}")
    convert_to = local_convert_format(args, out)
    if args.dry_run:
        print(json.dumps({"url": base + endpoint, "out": str(out), "convert_to": convert_to, "content_type": content_type}, ensure_ascii=False, indent=2))
        return 0
    import copy
    import image_recipe
    payload = build_payload(args, prompt)
    if mode == "variation":
        payload.pop("prompt", None)
    recipe = image_recipe.begin(out, mode, payload,
                                args.image if isinstance(args.image, list) else [args.image],
                                getattr(args, "mask", None) if mode == "edit" else None,
                                postprocessing={"convert_to": convert_to, "convert_quality": args.convert_quality,
                                                "keep_original": args.keep_original})
    archived_args = copy.copy(args)
    archived_args.image = [x["path"] for x in recipe["inputs"] if x["role"] == "reference"]
    archived_args.mask = next((x["path"] for x in recipe["inputs"] if x["role"] == "mask"), None)
    body, content_type = build_multipart_payload(archived_args, mode, prompt)
    try:
        data = request_multipart_with_transport(
            "POST",
            base + endpoint,
            get_api_key(),
            body,
            content_type,
            timeout=args.timeout,
            stream=args.stream,
            transport=args.transport,
            retries=args.retries,
            proxy=getattr(args, "proxy", None),
            no_proxy=getattr(args, "no_proxy", False),
        )
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            die(f"unexpected image response: {json.dumps(data, ensure_ascii=False)[:800]}")
        outputs: List[str] = []
        for idx, item in enumerate(items, start=1):
            target = out if len(items) == 1 else out.with_name(f"{out.stem}-{idx}{out.suffix}")
            outputs.append(
                str(
                    decode_image_item(
                        item,
                        target,
                        args.transport,
                        convert_to=convert_to,
                        convert_quality=args.convert_quality,
                        retries=args.retries,
                        keep_original=args.keep_original,
                        proxy=getattr(args, "proxy", None),
                        no_proxy=getattr(args, "no_proxy", False),
                    )
                )
            )
        image_recipe.finish(recipe, outputs, data)
    except BaseException:
        image_recipe.failed(recipe)
        raise
    print(json.dumps({"outputs": outputs, "mode": mode, "recipe_path": recipe["recipe_path"]}, ensure_ascii=False, indent=2))
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    src = Path(args.input)
    if not src.is_file():
        die(f"input not found: {src}")
    fmt = args.format.lower().lstrip(".")
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in CONVERT_FORMATS:
        die(f"unsupported format: {fmt}")
    dst = Path(args.out) if args.out else src.with_suffix("." + fmt)
    convert_with_ffmpeg(src, dst, quality=args.convert_quality)
    print(json.dumps({"ok": True, "input": str(src), "output": str(dst.resolve())}, ensure_ascii=False, indent=2))
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    raw = download_bytes(
        args.url,
        timeout=args.timeout,
        transport=args.transport,
        retries=args.retries,
        proxy=getattr(args, "proxy", None),
        no_proxy=getattr(args, "no_proxy", False),
    )
    out = Path(args.out or f"download.{args.convert or args.ext or sniff_image_ext(raw)}")
    convert_to = local_convert_format(args, out) if args.convert or args.out else (args.convert or args.ext or sniff_image_ext(raw))
    item = {"b64_json": base64.b64encode(raw).decode("ascii")}
    path = decode_image_item(
        item,
        out,
        args.transport,
        convert_to=convert_to,
        convert_quality=args.convert_quality,
        retries=args.retries,
        keep_original=args.keep_original,
    )
    print(json.dumps({"ok": True, "url": args.url, "saved": str(path.resolve())}, ensure_ascii=False, indent=2))
    return 0


def parse_ratio(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    if ":" in value:
        left, right = value.split(":", 1)
        return float(left) / float(right)
    return float(value)


def cmd_verify(args: argparse.Namespace) -> int:
    expected_ratio = parse_ratio(args.aspect_ratio)
    results: List[Dict[str, Any]] = []
    ok = True
    for raw in args.paths:
        path = Path(raw)
        info = image_info(path)
        checks: List[str] = []
        if not info["exists"]:
            ok = False
            checks.append("missing")
        elif info["bytes"] <= 0:
            ok = False
            checks.append("empty")
        if info["width"] is None or info["height"] is None:
            ok = False
            checks.append("unknown_dimensions")
        else:
            if args.min_width and int(info["width"]) < args.min_width:
                ok = False
                checks.append(f"width_below_{args.min_width}")
            if args.min_height and int(info["height"]) < args.min_height:
                ok = False
                checks.append(f"height_below_{args.min_height}")
            if expected_ratio:
                actual = int(info["width"]) / int(info["height"])
                tolerance = args.aspect_tolerance
                info["aspect_ratio"] = round(actual, 6)
                if abs(actual - expected_ratio) > tolerance:
                    ok = False
                    checks.append(f"aspect_ratio_outside_tolerance_{tolerance}")
        info["checks"] = checks or ["ok"]
        results.append(info)
    print(json.dumps({"ok": ok, "files": results}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def add_common_image_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--base-url", default=None, help="NewAPI API base; default NEWAPI_BASE_URL or https://netcup-1.toapi.xyz/v1")
    p.add_argument("--model", default=os.environ.get("NEWAPI_IMAGE_MODEL", "gpt-image-2"))
    p.add_argument("--size", default=None, help="explicit WxH size; overrides --tier/--aspect")
    p.add_argument("--tier", choices=["1k", "2k", "4k"], default=None, help="resolution tier used with --aspect")
    p.add_argument(
        "--aspect",
        choices=["1:1", "4:3", "3:4", "16:9", "9:16", "9:21", "21:9", "3:2", "2:3"],
        default=None,
        help="aspect preset used with --tier",
    )
    p.add_argument(
        "--ratio",
        dest="ratio_alias",
        choices=sorted(set(RATIO_ALIASES)),
        default=None,
        help="ratio alias (square/landscape/portrait/1:1/3:2/2:3/16:9/4:3/9:16/3:4); maps to the nearest native size; ignored when --tier/--aspect or --size is given",
    )
    p.add_argument("--quality", default=os.environ.get("NEWAPI_IMAGE_QUALITY", "high"))
    p.add_argument("--style", default=None)
    p.add_argument("--response-format", default="url", choices=["b64_json", "url"])
    p.add_argument("--output-format", default=None, help="Provider/model-specific, e.g. png/webp/jpeg")
    p.add_argument("--output-compression", type=int, default=None)
    p.add_argument("--background", default=None)
    p.add_argument("--transparent", action="store_true", help="send background=transparent")
    p.add_argument("--moderation", default=None)
    p.add_argument("--n", type=int, default=1)
    stream_group = p.add_mutually_exclusive_group()
    stream_group.add_argument("--stream", dest="stream", action="store_true", help="request SSE streaming output (default)")
    stream_group.add_argument("--no-stream", dest="stream", action="store_false", help="request a normal JSON response")
    p.set_defaults(stream=True)
    p.add_argument("--partial-images", type=int, default=None, help="request partial SSE image frames")
    p.add_argument(
        "--transport",
        default="auto",
        choices=["auto", "curl", "urllib"],
        help="HTTP transport; auto prefers curl on Windows and urllib elsewhere",
    )
    p.add_argument("--ext", default="png", help="local output extension")
    p.add_argument("--convert", default=None, help="local output format, e.g. png, jpg, webp, avif")
    p.add_argument("--keep-original", action="store_true", help="save downloaded bytes without conversion")
    p.add_argument("--convert-quality", type=int, default=None, help="lossy conversion quality 1-100")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--retries", type=int, default=3, help="maximum attempts for transient failures")
    p.add_argument("--extra", action="append", help="extra JSON request parameter as key=value; value may be JSON")
    p.add_argument("--proxy", default=None, help="force this proxy URL (e.g. http://127.0.0.1:12002), no direct attempt")
    p.add_argument("--no-proxy", action="store_true", help="direct connection only, never fall back to a proxy")
    p.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate images through an OpenAI-compatible NewAPI endpoint.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("models", help="List available models")
    pm.add_argument("--base-url", default=None)
    pm.add_argument("--filter", default=None)
    pm.add_argument("--raw", action="store_true")
    pm.add_argument("--timeout", type=int, default=60)
    pm.add_argument("--transport", default="auto", choices=["auto", "curl", "urllib"])
    pm.add_argument("--proxy", default=None, help="force this proxy URL, no direct attempt")
    pm.add_argument("--no-proxy", action="store_true", help="direct connection only")
    pm.set_defaults(func=cmd_models)

    pg = sub.add_parser("generate", help="Generate one prompt")
    add_common_image_args(pg)
    pg.add_argument("--prompt")
    pg.add_argument("--prompt-file")
    pg.add_argument("--out")
    pg.set_defaults(func=cmd_generate)

    pb = sub.add_parser("batch", help="Generate JSONL batch; one object per line: {prompt,out,...}")
    add_common_image_args(pb)
    pb.add_argument("--input", required=True)
    pb.add_argument("--out-dir", required=True)
    pb.add_argument("--sleep", type=float, default=0.0)
    pb.set_defaults(func=cmd_batch)

    pe = sub.add_parser("edit", help="Edit an image through /images/edits")
    add_common_image_args(pe)
    pe.add_argument("--prompt")
    pe.add_argument("--prompt-file")
    pe.add_argument("--image", required=True, action="append",
                    help="reference image; repeat the flag to pass several (sent as image[], max 16)")
    pe.add_argument("--mask")
    pe.add_argument("--out")
    pe.set_defaults(func=cmd_edit_or_variation)

    pvar = sub.add_parser("variation", help="Create an image variation through /images/variations")
    add_common_image_args(pvar)
    pvar.add_argument("--prompt", default="")
    pvar.add_argument("--image", required=True)
    pvar.add_argument("--out")
    pvar.set_defaults(func=cmd_edit_or_variation)

    pc = sub.add_parser("convert", help="Convert a local image with ffmpeg")
    pc.add_argument("--input", required=True)
    pc.add_argument("--format", required=True)
    pc.add_argument("--out")
    pc.add_argument("--convert-quality", type=int, default=None)
    pc.set_defaults(func=cmd_convert)

    pd = sub.add_parser("download", help="Download an image URL and optionally convert it")
    pd.add_argument("--url", required=True)
    pd.add_argument("--out")
    pd.add_argument("--convert", default=None)
    pd.add_argument("--ext", default=None)
    pd.add_argument("--keep-original", action="store_true")
    pd.add_argument("--convert-quality", type=int, default=None)
    pd.add_argument("--timeout", type=int, default=180)
    pd.add_argument("--retries", type=int, default=3)
    pd.add_argument("--transport", default="auto", choices=["auto", "curl", "urllib"])
    pd.add_argument("--proxy", default=None, help="force this proxy URL, no direct attempt")
    pd.add_argument("--no-proxy", action="store_true", help="direct connection only")
    pd.set_defaults(func=cmd_download)

    pv = sub.add_parser("verify", help="Verify generated image files exist and expose dimensions")
    pv.add_argument("paths", nargs="+")
    pv.add_argument("--min-width", type=int, default=0)
    pv.add_argument("--min-height", type=int, default=0)
    pv.add_argument("--aspect-ratio", default=None, help="Optional ratio such as 16:9 or 1.7777")
    pv.add_argument("--aspect-tolerance", type=float, default=0.04)
    pv.set_defaults(func=cmd_verify)

    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
