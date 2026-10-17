#!/usr/bin/env python3
"""Initialize a generic PPT image-generation job workspace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


PROFILES = ("lecture", "dense", "reconstruction")

PROFILE_DEFAULTS = {
    "lecture": {
        "page_role": "lecture content page",
        "editability": "full-page image with verbatim on-slide text",
        "generated_text": "render page_text verbatim",
        "long_text": "adapt visible text to reading context, speaking time and audience; no fixed character cap",
        "prompt_intro": "Create a high-quality 16:9 lecture PPT page image.",
        "density_line": "Adapt information density to reading context and time; 3-5 items is an example, not a quota.",
    },
    "dense": {
        "page_role": "dense briefing page",
        "editability": "full-page image with verbatim on-slide text",
        "generated_text": "render page_text verbatim",
        "long_text": "thicken real structure first; do not invent numbers",
        "prompt_intro": "Create a high-quality 16:9 high-density briefing PPT page image.",
        "density_line": "High information density with a unique layout frame and the locked palette.",
    },
    "reconstruction": {
        "page_role": "main comp for later reconstruction",
        "editability": "record desired editable/reconstruction layer plan",
        "generated_text": "short exact labels only when supplied",
        "long_text": "reserve zones or overlay later when editable output is requested",
        "prompt_intro": "Create a high-quality 16:9 PPT main-comp image for later layered reconstruction.",
        "density_line": "Main comp first. Keep child-asset prompts dormant until the main image is accepted.",
    },
}


def write_text(path: Path, text: str, force: bool) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Dict[str, Any], force: bool) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prompt_pack(args: argparse.Namespace) -> Dict[str, Any]:
    defaults = PROFILE_DEFAULTS[args.profile]
    asset_prompts = []
    if args.profile == "reconstruction":
        asset_prompts = [
            {
                "asset_id": "P01_BG",
                "purpose": "clean PPT background/backplate without readable text",
                "prompt": "",
                "background": "opaque",
                "status": "dormant_until_main_comp_approved",
            },
            {
                "asset_id": "P01_ATOMS",
                "purpose": "icon/frame/connector atom sheet matching accepted main comp lineage",
                "prompt": "",
                "background": "transparent",
                "status": "dormant_until_main_comp_approved",
            },
        ]
    return {
        "project_name": args.project_name,
        "route": "mediagen ppt_image_workflow",
        "profile": args.profile,
        "generation_contract": {
            "provider": "NewAPI/OpenAI-compatible image endpoint",
            "model": args.model,
            "quality": args.quality,
            "size": args.size,
            "output_format": "png",
            "no_downgrade": True,
            "fallback_requires_user_approval": True,
            "image_only_pptx": args.image_only,
        },
        "requirement_alignment": {
            "scope": args.scope,
            "source_docx_or_content": args.source_docx,
            "reference_ppt_or_style_images": args.reference_ppt,
            "included_sections": [],
            "excluded_sections": [],
            "editability": "one generated image per slide" if args.image_only else defaults["editability"],
            "evidence_policy": "no fake proof; no fake screenshots/logos/certificates; no visible source labels by default",
            "focus_target": args.focus,
            "status": "pending_or_confirmed_by_user",
        },
        "style_lock": {
            "visual_dna": [],
            "content_dna": [],
            "header_master": "",
            "palette": [],
            "shape_grammar": "",
            "typography_rhythm": "",
            "forbidden_style_drift": [
                "generic rounded-card grid",
                "fake proof objects",
                "visible source labels by default",
                "pseudo text",
                "leaking style-reference text onto the page",
            ],
        },
        "style_extraction_note": {
            "visual_level": "",
            "content_level": "",
            "lessons_to_inherit": [],
            "lessons_to_reject": [],
            "status": "must be completed before image generation",
        },
        "pages": [
            {
                "page_id": "P01",
                "page_role": args.focus or defaults["page_role"],
                "profile": args.profile,
                "source_reference": [],
                "page_text": "",
                "materials": [],
                "layout_focus": "",
                "speaker_notes": "",
                "source_content_injection": {
                    "must_include": [],
                    "must_exclude": [],
                    "chapter_focus": args.focus,
                    "exact_visible_labels": [],
                },
                "page_visual_kernel": {
                    "one_sentence_takeaway": "",
                    "dominant_focal_point": "",
                    "layout_geometry": "",
                    "module_hierarchy": [],
                    "diagram_or_chart_logic": "",
                    "clean_footer_rule": "no visible 数据来源/来源/Source label by default",
                },
                "main_preview_prompt": "",
                "asset_prompts": asset_prompts,
                "element_map": [],
                "text_policy": {
                    "generated_text": defaults["generated_text"],
                    "long_text": defaults["long_text"],
                },
                "evidence_boundary": {
                    "no_fake_proof": True,
                    "real_assets_to_preserve": [],
                    "blank_or_neutral_frames": [],
                },
                "forbidden_items": [],
                "qa_checks": [
                    "matches requested page focus",
                    "inherits visual and content DNA from the style card",
                    "uses high quality NewAPI generation",
                    "contains no fake proof or visible source labels by default",
                    "selected output file exists and passes dimension verification",
                    "on-slide text matches page_text verbatim",
                ],
            }
        ],
    }


def build_main_jsonl(pack: Dict[str, Any], args: argparse.Namespace) -> str:
    defaults = PROFILE_DEFAULTS[args.profile]
    page = pack["pages"][0]
    prompt = "\n".join(
        [
            "Use the JSON prompt pack as the authority for this PPT page image.",
            "Global style lock: fill from prompt-pack.json before generation.",
            f"Profile: {args.profile}",
            f"Focus target: {args.focus or '[fill focus target]'}",
            defaults["prompt_intro"],
            defaults["density_line"],
            "Render 页面文字 verbatim. Do not paint field names onto the canvas.",
            "Do not invent proof screenshots, certificates, partner logos, source bars, or fake data.",
            "Do not draw visible 数据来源/来源/Source labels by default.",
            "Do not copy text from a style-reference image.",
            "Use crisp PPT-like design, controlled hierarchy, readable layout, and no pseudo text.",
            page.get("main_preview_prompt") or "[replace with the final page-specific main_preview_prompt]",
        ]
    )
    job = {
        "out": "P01_main_comp_high.png",
        "prompt": prompt,
        "model": args.model,
        "size": args.size,
        "quality": args.quality,
        "output_format": "png",
    }
    return json.dumps(job, ensure_ascii=False) + "\n"


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a NewAPI PPT image-generation workspace.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--project-name", default="ppt-image-job")
    parser.add_argument("--profile", choices=PROFILES, default="lecture")
    parser.add_argument("--source-docx", default="")
    parser.add_argument("--reference-ppt", default="")
    parser.add_argument("--scope", default="one page or selected chapter")
    parser.add_argument("--focus", default="")
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--size", default="2048x1152")
    parser.add_argument("--quality", default="high")
    parser.add_argument("--image-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.out_dir)
    from ppt_workflow import upgrade
    pack = upgrade(prompt_pack(args))

    write_text(
        root / "00-requirement-alignment.md",
        f"""# Requirement Alignment

- Project: {args.project_name}
- Profile: {args.profile}
- Scope: {args.scope}
- Source DOCX/content: {args.source_docx or '[fill]'}
- Reference PPT/style images: {args.reference_ppt or '[fill]'}
- Focus target: {args.focus or '[fill]'}
- Output: {'image-only PPTX, one generated image per slide' if args.image_only else PROFILE_DEFAULTS[args.profile]['editability']}
- Provider/model: NewAPI / {args.model}
- Size/quality/format: {args.size} / {args.quality} / png
- No-downgrade rule: enabled
- Fallback rule: requires explicit user approval
- Evidence boundary: no fake proof, no fake screenshots/logos/certificates, no visible source labels by default

Do not generate images until research (or an explicit skip), outline, style card, and P01 master are done. See references/ppt-preflight.md.

Confirm or revise this file before image generation.
""",
        args.force,
    )
    write_text(
        root / "02-research-brief.md",
        """# Research Brief

Fill before outline when the user gave a topic/homework prompt without sourced facts.

- Topic:
- Audience:
- Declared gaps:
- Status: pending | skipped: supplied-facts-sufficient | skipped: no-external-enrichment | completed

## Claims the deck may use

- 

## Claims that must stay off the canvas

- unsourced star/fork counts
- official logos/trademarks
- fake screenshots or certificates

Dispatch one research subagent when facts are thin. Write matching `02-fact-provenance.json`.
""",
        args.force,
    )
    write_json(
        root / "02-fact-provenance.json",
        {
            "schema": "mediagen.fact-provenance.v1",
            "topic": args.project_name,
            "gaps": [args.focus] if args.focus else [],
            "facts": [],
            "unresolved": [],
            "forbidden_inventions": [
                "GitHub star/fork counts unless sourced today",
                "official logos/trademarks",
                "fake screenshots, certificates, partner lists",
            ],
            "status": "pending_or_skipped",
        },
        args.force,
    )
    write_text(
        root / "03-outline.md",
        """# Outline

Fill after research, before prompts.

- Page count:
- Role sequence:
- Unique layout per content page: yes/no

| page_id | role | claim title | items | layout geometry | focal object |
|---|---|---|---|---|---|
| P01 | cover |  |  |  |  |
""",
        args.force,
    )
    write_text(
        root / "01-style-extraction-note.md",
        """# Style Card

Fill this before the first image call. Keep it for the whole deck.

## 视觉描述

-

## 配色与材质

- Background:
- Text:
- Accent (include hex and area cap):
- Material / shadow:

## 内容与排版

- Grid and margins:
- Title hierarchy:
- Density cap for this profile:
- Cover rule:
- Header master:

## 字体与中文排印

- CJK letterform (gothic vs Song/Kai; even stroke):
- Latin / digit letterform:
- Title weight / tracking:
- Body density: recommend from reading context and speaking time, no fixed character cap:
- Role-specific font families (display / heading / body / numbers), artistic display permitted:
- Repeat this lock at the end of every prompt: yes

## 插图与渲染要求

- Icon style:
- Chart style:
- Anti-AI risks:

## 禁止事项

-

## 生图执行提示

-

## Content DNA

- Page role sequence:
- Title grammar:
- Evidence grammar:
- Wording style:
- Weak habits to reject:

Status: must be completed before image generation. P01 is the visual master; do not batch later pages first.
""",
        args.force,
    )
    write_json(root / "prompt-pack.json", pack, args.force)
    write_text(root / "prompts" / "main-prompts.jsonl", build_main_jsonl(pack, args), args.force)
    write_text(root / "prompts" / "asset-prompts-dormant.jsonl", "", args.force)
    write_text(
        root / "qa-checklist.md",
        f"""# QA Checklist

- [ ] Requirement alignment completed
- [ ] Profile locked ({args.profile})
- [ ] Research brief completed or explicitly skipped
- [ ] Outline completed
- [ ] Style card completed, including 字体与中文排印
- [ ] P01 generated and accepted as visual master before later pages
- [ ] Page description split into 页面文字 / 配图与素材 / 版式与重点 / 演讲者备注
- [ ] Prompt pack JSON completed
- [ ] Main prompt JSONL dry-run passed
- [ ] High-quality main image generated
- [ ] Selected output passes `newapi_image.py verify`
- [ ] On-slide text matches 页面文字
- [ ] No fake proof or visible source-label wording by default
- [ ] Child asset prompts remain dormant until main approval (reconstruction only)
- [ ] Image-only PPTX uses one selected image per slide, if requested
""",
        args.force,
    )
    for sub in ["outputs/main", "outputs/assets", "outputs/contact-sheet", "pptx", "working"]:
        (root / sub).mkdir(parents=True, exist_ok=True)
    print(
        json.dumps(
            {
                "ok": True,
                "out_dir": str(root),
                "profile": args.profile,
                "prompt_pack": str(root / "prompt-pack.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
