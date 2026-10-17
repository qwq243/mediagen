# Proxy / VPN Fallback, Endpoint Failures, and Built-in ImageGen Fallback

Read this when NewAPI is unreachable or the network/proxy layer is suspected.

## Connectivity and base URL

- Use `NEWAPI_BASE_URL` for custom endpoints; the script accepts either `https://host` or `https://host/v1`. On Windows, the newest user-level base URL takes precedence over a stale value inherited by an already-running Codex process; explicit `--base-url` remains highest priority.
- **Default host is `https://netcup-1.toapi.xyz/v1`** (`config.json`, API notes, and the user-level `NEWAPI_BASE_URL`). The legacy `https://api.toapi.xyz/v1` is the *same* instance, but its TLS handshake is reset on the campus network — do not "fix" a failure by switching back to it.
- Default to `response_format=url`, `stream=true`, and `transport=auto`. On Windows, auto transport prefers system curl over Python urllib and passes the bearer token through curl config stdin so it does not appear in process arguments.
- Connectivity is **direct-first with automatic proxy fallback**: if the network layer keeps failing (connection reset/timeout before any HTTP status), the helper probes `NEWAPI_PROXY`, then `HTTPS_PROXY`/`HTTP_PROXY`/`ALL_PROXY`, then `config.json` `"proxy"`, then a TCP scan of common local VPN/Clash ports (`proxy_ports`), and retries through each working route.
  - Any HTTP status (even 401/403) means the route works; only DNS/connection/TLS failures trigger fallback.
  - Image CDN downloads reuse the same route chain.
  - Force one side with `--proxy URL` or `--no-proxy`, or set `config.json` `"prefer_proxy": true`. SOCKS proxies require PySocks; prefer the Clash mixed port (`http://127.0.0.1:PORT`).
- On Windows, the helper also reads user-level HKCU environment variables when the current process environment has not refreshed yet.

## Endpoint failure diagnosis

If NewAPI is unreachable, do not guess parameters or silently claim generation succeeded. The helper already tries direct plus every detected local proxy route and reports the route it used; before manual diagnosis, check its output `transport`/warning lines. First isolate whether the failure happens before the API request is accepted:

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py models --filter image
curl.exe -v https://netcup-1.toapi.xyz/v1/models --connect-timeout 20 --max-time 40
```

Interpretation guidance:

- `WinError 10054`, `Recv failure: Connection was reset`, or `failed to receive handshake` during `curl -v` TLS setup means the TCP connection opened but TLS was reset by the remote/network layer. This is not a prompt, payload, model, or key-format problem. The helper normally recovers this automatically through a local proxy route; if all routes fail, check that the VPN/Clash client is running and exposing its mixed port.
- If every transport (direct + all detected proxies) fails, report that neither direct nor local proxy routes reach the API and suggest starting the VPN client; do not silently substitute another generator.
- If Python urllib resets before an HTTP status but the provider dashboard shows no request, retry the same payload with `--no-stream --transport curl`. A successful curl request proves the API/model/key path and isolates the issue to the client transport or SSE connection.
- HTTP `401` / `403` / `404` / `429` / JSON error responses mean TLS worked and the API response should be summarized without exposing secrets. `401`/`403` appear only after a transport already works, so do not retry other transports.

## Fallback to built-in `imagegen`

When NewAPI fails at the network/TLS layer and the user explicitly permits a fallback or invokes `$imagegen`, use the system `imagegen` skill as the fallback generator. In the PPT image workflow, this approval must be explicit:

1. Keep the same prompt JSONL and ledger records so assets remain reproducible.
2. Generate a removable chroma-key source if transparency is needed, then remove the background locally with the `imagegen` helper.
3. Save final project-bound assets into the workspace, not only under Codex home.
4. In the ledger, record that NewAPI failed and which fallback path produced the file.
5. If the fallback cannot write directly to the desired workspace path, copy/move the selected generated file into the project before reporting completion.

If the user requests image generation through NewAPI and NewAPI is unavailable, stop and report the failure unless the user explicitly approves another raster image generator. Do not substitute editable PPT, SVG/HTML, old images, or low-quality output.

## Machine notes — Windows workstation `qwq` (verified 2026-09-23; base URL default fixed 2026-09-30)

**User authorization (standing):** on this machine the user has pre-approved **starting the VPN client automatically** when NewAPI image calls fail at the network layer. Do not stop to ask; start it, retry, then restore the previous state.

Order of attempts that actually works here (cheapest first):

1. **Just run the normal command.** Since 2026-09-30 the default base URL is `https://netcup-1.toapi.xyz/v1` (user-level `NEWAPI_BASE_URL` + `config.json`), which is reachable **directly** and needs no proxy. Earlier notes told you to pass `--base-url https://netcup-1.toapi.xyz/v1` first — that is now the default, so `--base-url` is only for pointing at a *different* host:

   ```powershell
   python C:/Users/USER/.zcode/skills/mediagen/scripts/newapi_image.py generate `
     --base-url https://netcup-1.toapi.xyz/v1 --model gpt-image-2 --size 1024x1024 `
     --quality high --transparent --prompt "..." --out out.png
   ```

   This reproduced a successful 1254x1254 transparent PNG with no proxy in the loop.

2. **If the sibling host also fails, start FlClash** (`E:\software\FlClash\FlClash.exe`, data dir `%APPDATA%\com.follow\clash`, profile declares `mixed-port: 7890`). Its Flutter UI exposes an accessibility tree (drive it with Computer Use, a11y first):
   - Dismiss the "发现新版本" dialog (`不再提示`).
   - The core only starts listening after the big timer button is pressed: before that only the DNS port (`1053`) is bound. The timer button's label ticks every second, so it **cannot be clicked by element index** (identity validation fails) — use it only when a fresh raster is available, otherwise ask the user to click it.
   - `系统代理 → 设置系统代理` checkbox toggles the Windows proxy; it is stable and clicks fine by index. Enabling it sets `HKCU\...\Internet Settings` `ProxyEnable=1`, `ProxyServer=127.0.0.1:7890`.
   - **Restore afterwards**: HTTPS through the currently configured node failed (both curl/schannel and .NET reported a closed TLS connection) while plain HTTP worked (204/200). Leaving the system proxy on would break the user's other apps, so toggle the checkbox back off and confirm `ProxyEnable=0` before finishing. Surviving a local listener on 7890 is harmless.
