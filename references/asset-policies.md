# Asset Prompt Policies

Treat image generation as reusable asset production, not a one-off preview. Read this when generating project-bound visuals, icons, cutouts, or prototype assets.

PPT slide pages are not covered here. Use `references/ppt-image-workflow.md` for lecture/dense/reconstruction decks.

## Classify each requested image

- `hero`: large page or homepage visual; may have background and atmosphere.
- `illustration`: section decoration or explanatory artwork; usually light background or transparent/chroma-key source.
- `icon`: small UI or prototype symbol; must be readable at small sizes and easy to isolate from background.
- `prototype-reference`: mockup support image; preserve prompts and asset notes for later reconstruction.

For each asset, decide and record:

- intended page/section
- front-end display strategy, for example `cover`, `contain`, `background`, `inline`, or `alpha`
- final output path
- source/chroma-key path if background removal is planned
- model, size, quality, and prompt

## Project style card

When a project has a visual direction, create or reuse a short style guide such as `docs/design/image-style-guide.md`. Keep it concise and reference it while writing prompts.

Recommended fields:

- brand mood and audience
- color palette
- shape language
- illustration style
- icon style
- forbidden styles
- page-specific display rules

Example for warm public-service projects:

```text
Style: warm, trustworthy, public-service, child rehabilitation friendly.
Palette: deep green, warm orange accent, cream background, low-saturation supporting colors.
Shapes: rounded, soft shadows, calm spacing, non-commercial and non-medical-alarm tone.
Avoid: cyberpunk, dark hospital mood, horror medical imagery, clutter, thin-line icons, tiny text, watermarks.
```

## Icon Generation Rules

Icons need stronger constraints than hero illustrations. Do not use delicate line art by default.

Prompt icon assets with:

```text
bold readable icon, thick rounded strokes, simple silhouette, high contrast, legible at 48px,
large clear shapes, minimal detail, no thin lines, no hairline strokes, no tiny details,
no text, no watermark
```

Practical stroke guidance:

- 1024px icon source: main strokes should visually read like roughly 48-72px strokes.
- 512px icon source: main strokes should visually read like roughly 28-44px strokes.
- Avoid dense hatching, tiny labels, subtle outlines, small facial details, micro UI marks, or decorative texture.

For icon batches, vary the subject while keeping a consistent visual system:

- same stroke weight family
- same corner radius feeling
- same palette
- same padding
- same background-removal strategy

## Transparent assets

The image model can emit already-cut RGBA PNGs. Prefer that. Do not run a local chroma-key / cutout pipeline.

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py generate `
  --model gpt-image-2 --size 1024x1024 --quality high --output-format png --transparent `
  --prompt "bold readable icon, isolated subject, transparent background, no drop shadow, no text" `
  --out icon.png
```

Prompt the subject as isolated, with no floor, cast shadow, or backdrop. Then send `--transparent` / `background=transparent`. Verify the file has an alpha channel and transparent corners.

Do not generate a green-screen plate and cut it locally unless the user explicitly asks for that fallback.

## Prompt Ledger / Reproducibility

For project assets, write or append a JSONL record so future agents can regenerate or adapt the asset.

Suggested ledger path:

```text
docs/design/image-assets.jsonl
```

Suggested JSONL fields:

```json
{
  "out": "frontend/public/images/example.png",
  "source": "tmp/imagegen/example-source-key.png",
  "asset_type": "icon",
  "page": "home",
  "section": "hero",
  "size": "1024x1024",
  "model": "gpt-image-2",
  "quality": "high",
  "display_strategy": "alpha",
  "background_strategy": "chroma-key",
  "key_color": "#00ff00",
  "prompt": "...",
  "negative_prompt": "no text, no watermark, no thin lines, no tiny details",
  "notes": "Readable at 48px; source kept for future background removal."
}
```

For prototype reconstruction, preserve prompts for every generated icon and illustration. If a prototype image includes many small visuals, create separate ledger entries for each icon/illustration that should be reproducible later.

## Post-generation Checks

Before reporting completion for project assets:

- generated files exist at the expected workspace paths
- selected outputs pass `newapi_image.py verify` or an equivalent file/dimension check
- prompt batch path and/or prompt ledger path is reported
- project-bound assets are not left only in a temp or Codex home directory
- icon prompts include bold/readable/thick-stroke constraints
- transparent/chroma-key assets keep source and final paths when applicable
- hero assets match their intended front-end strategy:
  - homepage visual can use `cover` and a taller art window
  - inner page hero should usually keep `contain` and the agreed aspect ratio
- no existing asset is overwritten unless the user explicitly requested replacement
