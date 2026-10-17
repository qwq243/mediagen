#!/usr/bin/env python3
"""Query the bundled GPT-Image-2 style library (from awesome-gpt-image-2).

Lists categories/templates and prints bilingual guidance for building
production-grade prompts. Read-only; no network access.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LIBRARY_PATH = Path(__file__).resolve().parent.parent / "references" / "style-library.json"


def load_library() -> dict:
    if not LIBRARY_PATH.exists():
        raise RuntimeError(f"style library not found: {LIBRARY_PATH}")
    return json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))


def template_summary(template: dict, lang: str) -> dict:
    return {
        "id": template.get("id"),
        "title": template.get("title", {}).get(lang),
        "category": template.get("category"),
        "description": template.get("description", {}).get(lang),
        "use_when": template.get("useWhen", {}).get(lang),
        "guidance": template.get("guidance", {}).get(lang, []),
        "pitfalls": template.get("pitfalls", {}).get(lang, []),
        "example_cases": template.get("exampleCases", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the bundled GPT-Image-2 style library.")
    parser.add_argument("--list", action="store_true", help="list all templates (id + title + category)")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh", help="output language for details")
    parser.add_argument("--category", help="filter by category substring (e.g. poster, infographic, UI)")
    parser.add_argument("--search", help="search templates by keyword in title/description/tags")
    parser.add_argument("--template", help="show full guidance for one template id")
    parser.add_argument("--shared", action="store_true", help="also query cross-project references/preferences/feedback")
    args = parser.parse_args()
    if args.shared:
        from ppt_workflow import library_search
        print(json.dumps({"shared_records": library_search(args.search or "", args.category)},
                         ensure_ascii=False, indent=2))
        return 0

    try:
        library = load_library()
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    lang = args.lang
    templates = library.get("templates", [])

    if args.template:
        match = next((t for t in templates if t.get("id") == args.template), None)
        if not match:
            print(json.dumps({"error": f"template not found: {args.template}"}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(template_summary(match, lang), ensure_ascii=False, indent=2))
        return 0

    candidates = templates
    if args.category:
        needle = args.category.lower()
        candidates = [t for t in candidates if needle in str(t.get("category", "")).lower() or needle in str(t.get("anchor", "")).lower()]
    if args.search:
        needle = args.search.lower()

        def matches(template: dict) -> bool:
            haystack = json.dumps(template, ensure_ascii=False).lower()
            return needle in haystack

        candidates = [t for t in candidates if matches(t)]

    if args.list or (args.category and not args.search) or args.search:
        print(
            json.dumps(
                {
                    "library_version": library.get("version"),
                    "source": library.get("repository"),
                    "count": len(candidates),
                    "templates": [
                        {
                            "id": t.get("id"),
                            "title": t.get("title", {}).get(lang),
                            "category": t.get("category"),
                            "anchor": t.get("anchor"),
                        }
                        for t in candidates
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(
        json.dumps(
            {
                "library_version": library.get("version"),
                "source": library.get("repository"),
                "categories": [c.get("id") for c in library.get("categories", [])],
                "template_count": len(templates),
                "hint": "use --list to enumerate, --template <id> for guidance, --search <kw> to find one",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
