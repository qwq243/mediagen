"""Contracts for the single-shell navigation; browser interaction is separately UAT'd."""
from pathlib import Path
import re

STATIC = Path(__file__).resolve().parents[1] / "scripts/static/ppt-workbench"


def test_new_surfaces_use_hash_routes_and_shared_shell():
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    for route in ("workflow", "knowledge", "design-spec"):
        assert f'href="#{route}"' in index
    assert 'href="/workbench/knowledge.html' not in index
    assert index.count('class="rail"') == 1
    assert index.count('id="view"') == 1
    assert index.index('knowledge.js') < index.index('/workbench/app.js')
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'PPTKnowledge.mount' in app
    assert 'PPTKnowledge?.unmount' in app
    assert 'workbench:changed' in app
    assert "location.hash.slice(1)||'workflow'" in app


def test_old_bookmarks_redirect_without_a_second_application():
    old = (STATIC / "knowledge.html").read_text(encoding="utf-8")
    script = (STATIC / "knowledge-redirect.js").read_text(encoding="utf-8")
    assert "knowledge-redirect.js" in old
    assert 'id="app"' not in old and "knowledge.css" not in old
    assert "location.replace" in script
    assert "#design-spec" in script and "#knowledge" in script


def test_new_styles_cannot_restyle_dispatcher_shell():
    css = (STATIC / "knowledge.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for selector in re.findall(r"([^{}]+)\{", css):
        if selector.strip().startswith("@"):
            continue
        for part in selector.split(","):
            assert "knowledge" in part, part
    assert not re.search(r"(?:^|[{}])\s*(?::root|body)\s*\{", css)


def test_knowledge_lifecycle_cancels_stale_fetch_and_protects_drafts():
    js = (STATIC / "knowledge.js").read_text(encoding="utf-8")
    assert js.startswith("(() => {")
    assert "controller?.abort()" in js
    assert "searchController?.abort()" in js
    assert "version!==mountVersion" in js
    assert "hasDraft:()=>draftDirty" in js
    assert "history.replaceState" not in js  # shell owns navigation
    assert 'id="previous"' in js
