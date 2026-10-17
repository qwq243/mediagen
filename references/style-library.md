# Prompt Engineering with the Bundled Style Library

`references/style-library.json` bundles the awesome-gpt-image-2 style library — 22 industrial prompt templates in 13 categories, with bilingual guidance and pitfalls.

For non-trivial images (posters, infographics, UI shots, product/brand visuals, Chinese-text layouts), build the prompt from a matching template instead of improvising. Simple subjects (a pig, an icon) do not need the library.

This library is **not** the PPT style card. For slide pages, lock a deck-level card in `references/ppt-image-workflow.md` and keep this file for non-PPT work. A poster template may inform texture language; it must not override lecture/dense density or the page-description schema.

## Query the library

```powershell
# List all templates
python C:/Users/USER/.codex/skills/mediagen/scripts/query_style_library.py --list
# Find one by keyword, then read its guidance
python C:/Users/USER/.codex/skills/mediagen/scripts/query_style_library.py --search poster
python C:/Users/USER/.codex/skills/mediagen/scripts/query_style_library.py --template poster-layout-system --lang zh
```

## Prompt assembly order

Per the library: subject/task → composition/layout → style/materials → exact text & labels → aspect ratio/format → constraints & negative details.

Always apply the template's `pitfalls` as negative constraints. For batch/series requests, reuse one template and vary subject, palette, and scene.
