# NewAPI image endpoint notes

This skill assumes an OpenAI-compatible API surface:

- `GET /v1/models`
- `POST /v1/images/generations`
- `POST /v1/images/edits` (multipart form data)
- `POST /v1/images/variations` (multipart form data; provider support is optional)

Base URL handling:

- Default API base: `https://netcup-1.toapi.xyz/v1` (the site's own host). The legacy `api.toapi.xyz` is the same instance but TLS-reset on this network — prefer the default.
- `https://netcup-1.toapi.xyz` becomes `https://netcup-1.toapi.xyz/v1/...`.
- `https://netcup-1.toapi.xyz/v1` is accepted without creating `/v1/v1`.
- Image models exposed on this site (checked 2026-09-30): `gpt-image-2`, `gpt-image-2-exact`, `gpt-image-2.5`, `gpt-image-2.5-exact`, `gpt-image-2.5-flare`, `gpt-image-2.5-sunburst`. The 2.5 family follows the same request protocol; change `--model` only when the caller asks for it.

Common image generation parameters:

- `model`: defaults to `NEWAPI_IMAGE_MODEL` or `gpt-image-2`.
- `prompt`: required text prompt.
- `size`: e.g. `1024x1024`, `2048x1152`, `3456x1152`, depending on provider/model support.
- `quality`: model-specific, commonly `low`, `medium`, `high`, or `auto`.
- `response_format`: defaults to `url` for the current `netcup-1.toapi.xyz` contract; `b64_json` remains available for compatible providers.
- `stream`: defaults to `true`; use `--no-stream` when the provider or proxy does not support SSE. The helper accepts SSE progress/completion events and normal JSON responses.
- `transport`: defaults to `auto`; on Windows this prefers system curl, while other platforms use urllib unless `--transport curl` is selected.
- `output_format`: provider/model-specific, commonly `png`, `jpeg`, or `webp`.
- `background`, `moderation`, `output_compression`: optional provider/model-specific parameters.
- `partial_images`: optional positive integer, sent only with `stream=true`; intermediate frames are not treated as final output when a completed event is present.
- `tier` and `aspect` are local CLI conveniences. The script resolves them to a concrete `size` before sending the request.
- `--extra key=value`: pass any provider-specific JSON parameter not exposed as a first-class flag.

Edit and variation multipart fields:

- Required file: `image`.
- Edit-only: `prompt`; optional `mask` file.
- Common fields: `model`, `n`, `size`, `response_format`, `stream`, `quality`, `partial_images`, `output_format`, `output_compression`, and `background` when supported by the provider.

Compatibility notes:

- NewAPI's generic image-generation docs list the OpenAI-compatible endpoint `/v1/images/generations`, bearer-token authentication, `model`, `prompt`, `n`, `size`, `background`, `moderation`, `quality`, and `style`.
- Some NewAPI docs may lag newer OpenAI image models. For the current standalone image endpoint, start with `gpt-image-2`, `quality=high`, `response_format=url`, `stream=true`, `transport=auto`, and a native size such as `1024x1024` for smoke tests. If streaming fails, retry the identical payload with `--no-stream` before changing model or prompt.
- If a provider rejects `gpt-image-2` or flexible sizes, retry with `gpt-image-1` and documented sizes: `1024x1024`, `1536x1024`, or `1024x1536`.
- Historical endpoint observations are not proof that the current channel can generate. Always make one real `POST /v1/images/generations` smoke request after checking local configuration.
- The same smoke test showed requested sizes may be provider-resampled: `1024x1024` returned `1254x1254`, and `2048x1152` returned `1672x941`. Treat `size` as intent rather than an exact guaranteed pixel dimension for this endpoint.
- A `gpt-image-2` wide hero smoke test at `2048x1152`, `quality=high`, `output_format=png`, `response_format=b64_json` produced a usable watercolor hero background with clean central negative space.

Troubleshooting:

- `401/403`: key invalid, missing, expired, or not authorized for the model.
- `404`: base URL may be wrong or provider does not expose the compatible endpoint.
- `400`: unsupported model, size, quality, output format, or parameter combination.
- URL responses are downloaded as signed URLs; do not persist signed URLs in project ledgers. SSE responses are parsed until the final event containing image data.
- Local format conversion is explicit and deterministic: `--convert` controls the target codec, `--keep-original` preserves provider bytes, and `convert`/`download` expose the same behavior outside a generation request. `ffmpeg` is required for codec changes.
- On Windows, curl transport sends the bearer header through curl config stdin rather than the command line. Do not add verbose logging that prints config stdin or authorization headers.
- `Connection reset` or `connection timed out` before an HTTP status: network path, firewall, proxy, DNS/CDN routing, or endpoint availability issue. Retry from another network or set `NEWAPI_BASE_URL` / `--base-url` to another compatible endpoint. On this network, `api.toapi.xyz` resets and `netcup-1.toapi.xyz` is the reachable host.
