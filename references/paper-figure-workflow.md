# Paper Figure / Graphical Abstract Workflow

Read this when the user wants paper art: a graphical abstract (图文摘要), mechanism
schematic, concept illustration, pipeline/workflow diagram, or cover art.

Do not use this channel for data-bearing figures. See the route table below.

## Two layers — decide the content before the pixels

| Layer | Owner | Output |
|---|---|---|
| What to say | `nature-figure` skill → `references/ai-graphical-abstract-workflow.md`, then `references/figure-contract.md` | the figure contract: message, entities, reading order, evidence boundary, labels, exclusions |
| How to draw it | this skill | prompt + CLI call, transport/proxy, output files, prompt ledger |

Load layer 1 first. This channel may not invent science: no mechanism, structure,
anatomy, magnitude, or relationship that the author did not state. If the contract
is missing, build it with the user before calling the API.

## Route table

| Task | Route |
|---|---|
| Graphical abstract, mechanism schematic, concept illustration, pipeline / workflow diagram, cover art | **this channel** |
| Bar / line / scatter / heatmap / box / survival / forest plots, statistical panels | deterministic Python or R in `nature-figure` — never the image model |
| Micrographs, blots, gel images, spectra, medical imaging | real data only — never generated |
| Multi-panel assembly, journal-ready layout, vector / PDF export | `nature-figure` plotting route |
| Paper prose (abstract, intro, discussion), polishing, reviewer response | `nature-writing` / `nature-polishing` / `nature-response` — not this skill |
| Slides from a paper | `nature-paper2ppt` authors the real editable deck from the paper's own figures and notes; this skill supplies only **concept** art for it — cover, graphical-abstract page, mechanism illustration. Never the paper's data figures, and never `lecture`/`dense` slide-density pages of its results |

## Policy gate before the first API call

- Verify the target journal's current graphical-abstract, AI-use, image-integrity
  and disclosure rules on official pages; record journal, URL and access date.
  If clearance is unknown, label the output **internal design draft — submission
  eligibility unverified** and do not call it submission-ready.
- Do not upload confidential manuscripts, unpublished review material, or
  sensitive data to the image endpoint without explicit authorization.
- Keep a provenance plan (see the ledger section below).

## Figure contract → prompt

Map every contract field into the prompt; omit one and the model invents it.

| Contract field | Prompt fragment |
|---|---|
| Purpose and audience | "schematic for a research paper read by specialists" |
| One-sentence message | first sentence of the prompt, stated as the central claim |
| Figure type and reading order | "left-to-right four-stage pipeline" / "circular mechanism, clockwise" / "split before-after" |
| Required entities and relationships | explicit entity list with directions and arrows |
| Evidence boundary, forbidden implications | negative clauses: "no additional organs/cells/materials, no implied clinical effect" |
| Composition and focal element | panel flow, hierarchy, the strongest accent on the central causal step |
| Palette, contrast, accessibility | "restrained high-contrast palette, color-blind-safe, no rainbow gradient, white background" |
| Exact short labels | quoted verbatim, 1–3 words each, ASCII where possible |
| Exclusions | "no fabricated numbers, no axis scales, no logos, no watermark, no decorative science objects" |
| Output role | append "concept draft schematic, not a data panel" |

Style: flat vector-like, restrained palette, high contrast, white or transparent
background. Generate 2–4 layout alternatives before polishing a single composition;
correct scientific structure first, then typography and finish.

## Text inside generated art

`gpt-image-2` renders letters unreliably, and CJK is worse. Default rule: generate
the art **without text** (`no text, no letters, no labels`) and place labels
afterwards in PowerPoint, Illustrator, Inkscape, or Python. When the user insists
on rendered labels, keep them short and ASCII, then read the output back and fix
misspellings with a single `edit` call — never ship unverified lettering.

## CLI recipes

Graphical abstract, 16:9:

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py generate `
  --model gpt-image-2 `
  --base-url https://netcup-1.toapi.xyz/v1 `
  --tier 2k --aspect 16:9 `
  --quality high --response-format url --stream --transport auto `
  --prompt "<contract-mapped prompt>" `
  --out paper/<slug>-ga-v1.png
```

Square mechanism schematic, transparent so it can be placed on a journal layout:

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py generate `
  --model gpt-image-2 --base-url https://netcup-1.toapi.xyz/v1 `
  --tier 2k --aspect 1:1 --quality high --output-format png --transparent `
  --prompt "isolated schematic, transparent background, no backdrop, <contract-mapped prompt>" `
  --out paper/<slug>-schematic-v1.png
```

One bounded revision from the accepted candidate (do not regenerate from scratch):

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_image.py edit `
  --image paper/<slug>-ga-v1.png `
  --base-url https://netcup-1.toapi.xyz/v1 `
  --tier 2k --aspect 16:9 --quality high `
  --prompt "<the single change to make>" `
  --out paper/<slug>-ga-v2.png
```

`--n` and explicit `--size WxH` are available. Keep acceptance explicit: only the
candidate the user approves becomes `-v1` for further edits.

## Verify before reporting

- `newapi_image.py verify <file> --min-width <w> --min-height <h>` on every selected output.
- Transparent figures: confirm an alpha channel and transparent corners.
- Read the image back (delegate visual inspection per project rules) for label
  spelling, entity direction, arrow correctness, and fabricated detail.

## Provenance ledger

Append to `paper/<slug>-figure-ledger.jsonl`, following the asset-policies
prompt-ledger convention and satisfying the provenance bundle required by
`ai-graphical-abstract-workflow.md` §5:

```json
{
  "out": "paper/x-study-ga-v1.png",
  "asset_type": "graphical-abstract",
  "output_role": "concept draft",
  "target_journal": "Nature Communications",
  "policy_url": "https://www.nature.com/nature-portfolio/editorial-policies/ai",
  "policy_access_date": "2026-09-27",
  "submission_eligible": false,
  "contract_summary": "one-sentence message + figure type",
  "prompt": "...",
  "negative_prompt": "no fabricated numbers, no logos, no extra entities",
  "model": "gpt-image-2",
  "quality": "high",
  "size": "2048x1152",
  "endpoint_host": "netcup-1.toapi.xyz",
  "transport": "curl",
  "generated_at": "2026-09-27",
  "candidates": ["paper/x-study-ga-c1.png", "paper/x-study-ga-c2.png"],
  "manual_corrections": "labels redrawn in PowerPoint; arrow direction fixed in v2"
}
```

Never put the API key in the ledger.

## Out of scope

- Manuscript prose, citation work, statistics review → the `nature-*` writing layer.
- Any figure that carries measurements: generating it would fabricate evidence.
- Recoloring or restyling a real data plot with the image model.
