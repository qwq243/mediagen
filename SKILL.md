---
name: mediagen
description: Generate or edit images through the NewAPI/OpenAI-compatible image endpoint (default https://netcup-1.toapi.xyz/v1), and generate Seedance video clips through the workstation sidecar (绘影 #/studio/video, 幻映 / local dola-pool). Covers everyday Chinese-preset images, PPT pages, paper art, style library, and generated video. Use for any 生成图 / 生视频 / 图生视频 request.
---

# Mediagen（生图 + 生视频）

## Overview

One skill for both media lines on this machine:

- **Images** go through the NewAPI/OpenAI-compatible image endpoint. Keep secrets out of skill files and command logs: read the API key from environment variables only.
- **Video** goes through the workstation sidecar (Seedance via 幻映 or the local dola-pool). NewAPI has no video models — never POST `/v1/videos`.

- Default API base: `https://netcup-1.toapi.xyz/v1`. The legacy host `api.toapi.xyz` is the same instance but is TLS-reset on the campus network — see [proxy-and-fallback](references/proxy-and-fallback.md).
- Generation endpoint: `https://netcup-1.toapi.xyz/v1/images/generations` — treat it as a standalone image endpoint. Model discovery is optional and must not block a direct generation smoke test when the user already supplied the model.
- Available image models on this site (2026-10-15 verified): `gpt-image-2`, `gpt-image-2.5`, `grok-imagine-image-2.0`, `nana-banana-2.1`, `nano-banana-pro`, `seedream-5.0`. Default stays `gpt-image-2`; switch deliberately, not by habit.
- Channel notes: `gpt-image-2` can return upstream "Model not found" and `gpt-image-2.5`/`-1k` variants can 503 "No available channel under group image" — these are site-side channel outages, not parameter errors; retry later or fall back to `nana-banana-2.1` / `seedream-5.0`. Banana models reject `quality` + default format combos: pass `--output-format png` (and drop `--quality`) or the helper tries an ffmpeg conversion that is unavailable on this machine.

## When to use

- Raster image generation, editing, or variations through NewAPI.
- The built-in image generation tool is unavailable.
- Project image assets via a custom OpenAI-compatible image endpoint.
- **学姐用的生图** — everyday/social images for a non-technical user (头像/壁纸/朋友圈/封面/贺卡/贴纸/表情包/海报). Read [xuejie-image-workflow](references/xuejie-image-workflow.md) and drive it with `scripts/xuejie_gen.py`; do not hand-tune sizes.
- PPT slide images. Read [ppt-image-workflow](references/ppt-image-workflow.md), then [ppt-resource-workbench](references/ppt-resource-workbench.md), [ppt-preflight](references/ppt-preflight.md) and [gpt-image-prompting](references/gpt-image-prompting.md). Use the two-stage workbench, shared resource cart and gated production; do not directly batch PPT pages with the generic image engine. Do not load a second image skill.
- Paper art — graphical abstract (图文摘要), mechanism schematic, concept illustration, pipeline diagram, cover art. Read [paper-figure-workflow](references/paper-figure-workflow.md). The content layer is the `nature-figure` skill; this skill only renders it. Data-bearing figures must not come here.
- Generated video (Seedance / 幻映 / 绘影生视频 / 图生视频). Read [video-workflow](references/video-workflow.md) and drive it with `scripts/newapi_video.py` or sidecar MCP `generate_video`. Do not POST `/v1/videos` to NewAPI.

Do not substitute another raster generator when NewAPI fails unless the user explicitly approves — see [proxy-and-fallback](references/proxy-and-fallback.md).

## Safety rules (always apply)

- Never hard-code API keys in `SKILL.md`, scripts, JSONL files, project files, or shell commands.
- Prefer the Windows user-level `NEWAPI_API_KEY`; fall back to the current process, then `OPENAI_API_KEY` only if the user set it.
- Use `quality=high` by default. Do not silently downgrade when the user requested high-quality output or PPT pages.
- Never overwrite an existing asset unless the user explicitly requested replacement.
- Not a source of other people's likenesses, ID photos, certificates, or brand marks — the 学姐 channel is a convenience layer, not a loophole around the [red lines](references/xuejie-image-workflow.md).
- Inspect actual images with available image-reading tools. Never require subagents or delegation merely to view an image. For PPT, independent review is a separate recorded pass; follow the user's execution/delegation constraints.
- PPT reference coding: read [ppt-reference-coding](references/ppt-reference-coding.md). Use the shared DK/PG identities and separate narrative, role, relation, layout, component, typography and palette codes. Preserve human tags; unknown fonts/colors stay unknown, never “complete” them by guessing.
- Atomic PPT knowledge and quantified full-image specs: read [ppt-atomic-knowledge](references/ppt-atomic-knowledge.md), [annotation-agent](references/ppt-annotation-agent.md), and [review-agent](references/ppt-review-agent.md). Use `ppt_knowledge.py` for version-bound candidates, taxonomy, explicit history selection and independent-review gates; use `ppt_design_spec.py` for typed targets, deterministic prompt/ordered-input compilation, ZIP replay packages and deviation checks. The 64-page set currently has 8 detailed candidates and 56 visual inventories, **not** 64 fully annotated or independently reviewed pages. Never promote based on JSON validation alone. UI, prompt compiler and render must share one input resolver; execute frozen bytes and keep unreported model/seed fields unknown.
- Stage handoff: the workbench locks unreached stages. After the user's first confirmation, independently review communication with `scripts/ppt_progress.py --job ... --review ...`; do not write a passed receipt without actual evidence. Later gates use content/prompt, sample visual, deck visual and notes audits. Previous stages remain revisitable, but pending revisions block production.
- Workbench copy: remove unnecessary, unrelated and repetitive explanations. Prefer short labels and contextual status; put provenance, factual boundaries and detailed help in remarks/details. Never repeat “click to view / not a sample / will not auto-generate” around every image. Keep reference/output type badges, genuine blocking reasons and explicit cost/approval gates. See the UI copy rules in [ppt-resource-workbench](references/ppt-resource-workbench.md).
- Workbench integration: use the existing dispatcher shell and design tokens. `/#workflow` is the overview, `/#knowledge` the atomic library, and `/#design-spec` the target/prompt/reference/audit views. Keep project version, stage gates and navigation shared; old `knowledge.html` bookmarks redirect into this shell. Do not create a separate application for new PPT tools. Cancel stale reads and protect unsaved drafts; performance caches must never replace current approval, source-hash or deviation checks.
- Read pending image handoffs from the project's `annotations/`: exact original image version + marked preview + normalized/pixel geometry. Reference and output annotations are distinct. Explain the intended edit/borrowing first; circles are not an automatic image mask. Favorites and shopping carts never imply generation authorization.
- Local crops, generation recipes, code examples, fixed components and precise blank regions: read [ppt-image-parts](references/ppt-image-parts.md). Treat the source crop, a proposed style variant, and an approved fixed component as different states. Resolve pending region/component requests with the user before production; never infer a paid authorization from a web selection.

## Routing

This skill is the only image/video generator for NewAPI + 绘影. Pick **one** channel; do not load another image skill for the same job.

| Group | Channel | Read |
|---|---|---|
| Core | Generate / edit / variation / JSONL batch; CLI params | [generate-edit-batch](references/generate-edit-batch.md) |
| Core | Prompt library for posters / infographics / UI / Chinese-text layouts (`awesome-gpt-image-2`, 22 templates) | [style-library](references/style-library.md) (data: `references/style-library.json`) |
| Core | Asset types, icon rules, native transparent PNG, prompt ledger | [asset-policies](references/asset-policies.md) |
| Everyday | **学姐用的生图** — 头像 / 壁纸 / 朋友圈 / 封面 / 贺卡 / 贴纸 / 表情包 / 海报; Chinese presets, no parameter tuning | [xuejie-image-workflow](references/xuejie-image-workflow.md) + `scripts/xuejie_gen.py` |
| Deck | PPT pages — `lecture` / `dense` / `reconstruction` | [ppt-image-workflow](references/ppt-image-workflow.md) |
| Deck | PPT preflight — research, outline, type lock, P01 master | [ppt-preflight](references/ppt-preflight.md) |
| Deck | GPT Image slide prompting (`gpt-image-2`, CJK/type, edit-from-P01) | [gpt-image-prompting](references/gpt-image-prompting.md) |
| Paper | Graphical abstract / mechanism schematic / concept illustration (**content layer = `nature-figure` skill**; never for data-bearing figures) | [paper-figure-workflow](references/paper-figure-workflow.md) |
| Video | Seedance clips via workstation sidecar (`#/studio/video`; 幻映 default, local dola-pool optional). **Not** NewAPI `/v1/videos` | [video-workflow](references/video-workflow.md) + `scripts/newapi_video.py` |
| Machine | Proxy / VPN fallback, endpoint failures (direct to `netcup-1` first; VPN auto-start pre-approved) | [proxy-and-fallback](references/proxy-and-fallback.md) |
| Machine | Windows credential setup | [environment-setup](references/environment-setup.md) |

## Quick start (one image)

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py generate `
  --model gpt-image-2 `
  --size 1024x1024 `
  --quality high `
  --response-format url `
  --stream `
  --transport auto `
  --prompt "soft watercolor visitor hero illustration, no text" `
  --out output.png
```

Everyday channel — one command, preset decides size and prompt scaffolding:

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/xuejie_gen.py 封面 `
  --subject "秋日校园银杏" --text "社团招新" --subtext "9月28日 图书馆前广场" --out 招新封面.png
```

Add `--list` for the preset table and `--print-prompt` / `--dry-run` to inspect the assembled prompt without spending.

## Bundled resources

- `scripts/newapi_image.py`: deterministic helper for `models`, `generate`, `edit`, `variation`, `batch`, `download`, `convert`, `verify`.
- `scripts/newapi_video.py`: video channel through the workstation sidecar (`generate` / `status`; `--dry-run` / `--wait`).
- `scripts/xuejie_gen.py`: everyday channel — Chinese presets assemble the prompt and call the helper (`--list`, `--print-prompt`, `--dry-run`, `--open`).
- `scripts/init_ppt_image_job.py`: PPT image-job workspace creator (`--profile lecture|dense|reconstruction`).
- `scripts/ppt_workflow.py`: versioned PPT approval/audit gates, English visual prompts with literal source-language text, controlled render, image-PPTX + native notes/transitions export, feedback and shared index. No paid calls without explicit authorization.
- `scripts/ppt_confirm_ui.py`: loopback v3 staged workbench: communication → complete proposal → real samples → revision → notes/delivery → feedback. Keeps MIT ppt-master two-round semantics; legacy UI remains at `/legacy`.
- `scripts/ppt_assets.py`: shared resource search, read-only incremental indexing, immutable pinning, independent asset import/variants. CLI and browser use identical IDs/search.
- `scripts/ppt_read_cache.py`: request-local image hashing and bounded DB/WAL-invalidated discovery indexes; not a production-decision cache.
- `scripts/ppt_cart.py`: local resource + external website shopping cart, public Commons search, submitted collection → agent-reviewed decisions. Collection is not approval or model-upload consent.
- `scripts/ppt_studio.py`: revision/history, version-bound annotations, image candidates, Agent composition, selected-asset ZIP export, external page import, controlled image editing and independent asset generation. No web drag-and-drop composition editor.
- `scripts/ppt_coding.py examples`: real, version-bound code examples shared by the browser and Agent, with suggested/reviewed status preserved.
- `scripts/ppt_fragments.py`: original-pixel local crops, immutable source snapshot, crop coordinates, parent asset version and tags.
- `scripts/ppt_components.py`: fixed-component selection handoff and Agent adoption; variant requests cannot silently fall back to the original crop.
- `scripts/ppt_regions.py`: precise blank-zone proposals, RGBA edit masks and deterministic blank/composite candidates; no model call.
- `scripts/image_recipe.py`: actual image-request model/parameters/prompt/input/output archives, used by the image engine and project/library imports. Never stores credentials or guesses unreported upstream defaults.
- `scripts/init_competition_ppt_job.py`: compatibility wrapper; same as `init_ppt_image_job.py --profile dense`.
- `scripts/query_style_library.py`: query the bundled GPT-Image-2 style library (`--list`, `--search`, `--template`, `--lang zh|en`); `--shared --search ...` queries cross-project preferences/references/feedback.
- `scripts/configure_newapi_credentials.ps1`, `scripts/open_newapi_credentials.cmd`: secure Windows credential setup.
- `config.json`: non-sensitive defaults only (base URL, default model/quality, `proxy`, `proxy_ports`, `prefer_proxy`); never put the API key here.
- `references/api-notes.md`: endpoint and parameter notes.
- `references/style-library.json`: 22 industrial prompt templates in 13 categories.
- `references/xuejie-image-workflow.md`: the everyday channel — preset table, text rules, red lines, failure table.
- `references/ppt-image-workflow.md`: generic PPT slide-image workflow. Do not use it for non-PPT assets.
- `references/paper-figure-workflow.md`: paper figures and graphical abstracts — contract-to-prompt mapping, journal policy gate, provenance ledger. Pairs with the `nature-figure` skill (content layer); replaces its OpenRouter provider route on this machine.
- `references/ppt-preflight.md`: research / outline / typography / P01-master gate before batch generation.
- `references/ppt-job-contract.md`: canonical v3 job fields, hashes, command gates and scoped feedback.
- `references/ppt-upstream-adaptation.md`: fixed source versions, MIT attribution and research-only license boundaries.
- `references/gpt-image-prompting.md`: `gpt-image-2` slide prompt protocol (CJK letterforms, negatives, edit-from-P01).
