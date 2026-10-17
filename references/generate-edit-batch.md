# Generate / Edit / Variation / Batch

Main generation flow and CLI usage for `newapi_image.py`. Read this when generating, editing, or creating variations of images, or running a JSONL batch.

## Transport and connectivity defaults

- Default to `response_format=url`, `stream=true`, and `transport=auto`. On Windows, auto transport prefers system curl over Python urllib and passes the bearer token through curl config stdin so it does not appear in process arguments.
- Use `--no-stream` when a provider does not support SSE or when diagnosing a proxy/streaming issue. The helper accepts both SSE events and normal JSON responses.
- Transient HTTP/network failures are retried with exponential backoff. Tune the maximum attempts with `--retries`; do not use retries to mask `401`, `403`, `404`, or invalid payload errors.
- For project assets, write outputs into the current workspace and use non-destructive filenames such as `*-v2.png` unless replacement is explicitly requested.

## Size / aspect / ratio

- Use `--tier 1k|2k|4k --aspect 1:1|4:3|3:4|16:9|9:16|9:21|21:9` for supported preset sizes.
- Use `--ratio square|1:1|landscape|3:2|16:9|4:3|portrait|2:3|9:16|3:4|auto` for a nearest-native-size alias (generate-image style).
- Use `--size WxH` for an explicit provider size. Explicit `--size` wins; a ratio alias without `--tier` maps to the nearest native size, and the actual requested native size should be reported rather than promising an exact unsupported ratio.

## Operation selection

- `generate` — new image.
- `edit` — a source image and a change instruction are supplied. Multipart request; on Windows, uploaded bytes are placed in a short-lived file while the bearer token remains in curl config stdin.
- `variation` — backend creates alternatives from a source image. Multipart request.
- `batch` — JSONL input, one prompt per line.
- Use `--partial-images N` only with streaming when intermediate SSE frames are useful. The parser prefers a completed image over late partial frames and falls back to a partial only when no final image exists.

## Commands

Optional model discovery:

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py models --filter image
```

Generate a JSONL batch:

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py batch `
  --input tmp/imagegen/prompts.jsonl `
  --out-dir frontend/public/images `
  --model gpt-image-2 `
  --size 3456x1152 `
  --quality high `
  --response-format url `
  --stream `
  --transport auto `
  --sleep 1
```

Verify generated files:

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py verify `
  output.png `
  --min-width 1200 `
  --min-height 675
```

Edit an existing image:

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py edit `
  --image source.png `
  --mask mask.png `
  --prompt "replace the background with a clean classroom scene" `
  --tier 1k --aspect 4:3 `
  --convert png `
  --out edited.png
```

Create a variation, download a result URL, or convert a local image:

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py variation --image source.png --out variation.png
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py download --url "https://signed.example/image" --out downloaded.png
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py convert --input image.avif --format png --out image.png
```

## JSONL line format

```json
{"out":"hero-about-v2.png","prompt":"Use case: illustration-story\nAsset type: visitor website top hero background illustration\n..."}
```

Job-level keys can override CLI defaults: `model`, `size`, `tier`, `aspect`, `quality`, `style`, `response_format`, `output_format`, `background`, `transparent`, `moderation`, `partial_images`, `n`, `ext`, `convert`, `keep_original`, `convert_quality`, `retries`.

Batch `out` values may contain nested paths such as `pages/hero.png`. Absolute paths and `..` traversal are rejected, so every generated file remains below `--out-dir`.

## Workflow

1. Confirm the request is raster image generation or model discovery through NewAPI.
2. If needed, create or reuse a JSONL prompt file under `tmp/imagegen/`.
3. Run `--dry-run` first for new prompt sets to validate payloads and output paths.
4. Run `models` only if the model name is unknown. A `/v1/models` failure does not replace a real image-generation smoke test when `gpt-image-2` is already known.
5. Run `generate`, `edit`, `variation`, or `batch` with workspace output paths. Use the default `stream=true`, `response_format=url`, and `transport=auto`; retry with `--no-stream` if the provider or proxy rejects SSE.
6. Use `--convert png|jpg|webp|avif` for a stable local codec. Use `--keep-original` only when preserving provider bytes matters; otherwise avoid mislabeled files by letting the helper convert to the requested extension. `ffmpeg` is required when the source and target codecs differ.
7. Run `verify` on selected outputs before reporting completion.
8. For project-bound assets, persist the prompt metadata in a ledger such as `docs/design/image-assets.jsonl` or `docs/design/image-prompts.jsonl` — see [asset-policies.md](asset-policies.md).
9. Summarize final saved paths and the prompt set/ledger location; do not paste large binary or full raw API responses.
