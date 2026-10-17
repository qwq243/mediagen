"""Focused reference shelf and closed-dialog regressions; no server/model calls."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

STATIC = Path(__file__).resolve().parents[1] / "scripts" / "static" / "ppt-workbench"


class ReferenceUiTests(unittest.TestCase):
    def render_preview(self, record):
        source = (STATIC / "app.js").read_text(encoding="utf-8")
        start, end = source.index("const chips="), source.index("async function legacyCodingView")
        setup = """
        let currentPreview;
        const esc=x=>String(x??''), font=()=>'', usages=()=>'', swatches=()=>'<div>色卡</div>';
        const kindNames={background:'背景'};
        const api=async()=>(RECORD);
        const modal=(title,body)=>process.stdout.write(body);
        """
        result = subprocess.run(
            [shutil.which("node") or "node", "-e",
             setup.replace("RECORD", json.dumps(record, ensure_ascii=False)) +
             source[start:end] + "\npreview('fixture');"],
            check=True, capture_output=True, text=True, encoding="utf-8")
        return result.stdout

    def test_na_and_components_do_not_show_false_pending_and_chapters_render(self):
        html = self.render_preview({
            "id": "fixture", "order": 8, "kind": "background", "title": "背景", "tags": ["背景"],
            "coding": {"status": "reviewed", "role": {"code": "RL-ASSET"},
                       "components": [{"code": "CP-BACKGROUND"}],
                       "layout": {"types": [{"code": "LY-FULLBLEED"}]},
                       "palette": {"swatches": [{"hex": "#AABBCC"}]}, "palette_ref": "PAL-TEST",
                       "material": {"code": "MT-GLASS"},
                       "applicability": {k: {"state": "not_applicable", "reason": "纯素材"}
                                         for k in ("typography", "relations", "density")}},
            "bundle_context": {"name": "关联范本", "main_count": 4, "resource_count": 10,
                               "current_role": "resource", "members": [], "related": []},
            "deck_coding": {"narrative": [{"code": "NT-MIXED"}],
                            "chapters": [{"name": "入口", "purpose": "交代用途", "page_codes": ["PG-TEST"]}]}
        })
        self.assertNotIn("待编码", html)
        self.assertNotIn("待确认", html)
        self.assertNotIn("第 8 页", html)
        self.assertIn("4 屏实拍 + 10 项配套资源", html)
        self.assertIn("不适用", html)
        self.assertIn("交代用途", html)
        self.assertIn("PG-TEST", html)

    def render_shelf(self, count, mode="assets", archived=False):
        source = (STATIC / "app.js").read_text(encoding="utf-8")
        start = source.index("async function assetsView(serial)")
        end = source.index("function watchAssets(serial)", start)
        setup = """
        let listing, renderSerial=1, filter={archived:ARCHIVED},
            checked=new Set(), galleryDensity='comfortable';
        const S={recommendations:Array.from({length:COUNT},(_,i)=>({
            id:'ref-'+i,title:'Title '+i,reason:'Reason '+i})),sites:[]};
        const view=()=>MODE, esc=x=>String(x??''),
            intro=()=>'', field=()=>'', facetNames={},
            facetLabel=(k,v)=>v, kindNames={},
            assetParams=()=>'', assetCard=()=>'', siteCard=()=>'';
        const api=async()=>({facets:{kind:[],work:[]},items:[],total:0,has_more:false});
        """
        setup = setup.replace("ARCHIVED", json.dumps(archived)).replace(
            "COUNT", str(count)).replace("MODE", json.dumps(mode))
        result = subprocess.run(
            [shutil.which("node") or "node", "-e",
             setup + source[start:end] + "\nassetsView(1).then(x=>process.stdout.write(x));"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        return result.stdout

    def test_closed_dialog_has_explicit_no_layout_guard(self):
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"dialog:not\(\[open\]\)\s*\{[^}]*display\s*:\s*none")

    def test_recommendations_stop_at_six_and_preserve_priority_order(self):
        html = self.render_shelf(8)
        ids = re.findall(r'class="recommendation"[^>]*data-id="([^"]+)"', html)
        self.assertEqual(ids, [f"ref-{i}" for i in range(6)])
        self.assertEqual(html.count('data-action="preview"'), 6)

    def test_fewer_recommendations_are_not_padded(self):
        html = self.render_shelf(2)
        self.assertEqual(html.count('class="recommendation"'), 2)

    def test_empty_shelf_is_not_shown(self):
        self.assertNotIn('class="recommendation-strip"', self.render_shelf(0))

    def test_archive_does_not_show_current_project_recommendations(self):
        self.assertNotIn('class="recommendation-strip"', self.render_shelf(8, archived=True))

    def test_favorites_does_not_show_current_project_recommendations(self):
        self.assertNotIn('class="recommendation-strip"', self.render_shelf(8, mode="favorites"))

    def test_recommendation_previews_keep_exact_versions(self):
        source = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-version="${esc(r.version||r.asset_version||', source)
        self.assertIn("await preview(el.dataset.id,el.dataset.version)", source)

    def test_component_proposal_is_not_a_sample_or_approval(self):
        source = (STATIC / "app.js").read_text(encoding="utf-8")
        start, end = source.index("function componentProposal("), source.index("function stageTwo(")
        result = subprocess.run(
            [shutil.which("node") or "node", "-e",
             "const esc=x=>String(x??'');" + source[start:end] +
             """process.stdout.write(componentProposal({component_proposal:{
                 title:'玻璃导航',preview_id:'candidate',preview_version:'exact',
                 status:'proposed',note:'仅结构示意，非样张',changes:['保留标题与章节'],
                 scope:'正文',approval_required:true}}));"""],
            check=True, capture_output=True, text=True, encoding="utf-8")
        self.assertIn("待确认", result.stdout)
        self.assertIn("仅结构示意，非样张", result.stdout)
        self.assertIn("data-version=\"exact\"", result.stdout)
        self.assertNotIn('data-action="confirm"', result.stdout)

    def test_adaptation_has_version_bound_parent_navigation(self):
        html = self.render_preview({
            "id": "adapted", "title": "适配示意", "kind": "navigation", "tags": [],
            "parent": {"id": "original-plate", "version": "pinned-parent"},
            "original_metadata": {"operation": "deterministic_local_composition"},
        })
        self.assertIn("查看上游版本", html)
        self.assertIn('data-id="original-plate"', html)
        self.assertIn('data-version="pinned-parent"', html)

    def test_seven_page_candidate_does_not_lose_its_closing_step(self):
        source = (STATIC / "app.js").read_text(encoding="utf-8")
        start, end = source.index("function candidateCard("), source.index("function swatches(")
        result = subprocess.run(
            [shutil.which("node") or "node", "-e",
             "const esc=x=>String(x??''),swatches=()=>'',globalSettingsSummary=()=>'';const S={proposal:{design:{palette:{}}}};" +
             source[start:end] +
             """process.stdout.write(candidateCard({name:'7页方案',
                narrative:'定位 → 场景 → 装配 → 留痕 → 演示 → 进展 → 愿景收束'},0));"""],
            check=True, capture_output=True, text=True, encoding="utf-8")
        self.assertIn("<span>愿景收束</span>", result.stdout)


if __name__ == "__main__":
    unittest.main()
