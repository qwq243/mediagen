"""Component-detail ownership; offline renders only, no project writes or model calls."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

STATIC = Path(__file__).resolve().parents[1] / "scripts" / "static" / "ppt-workbench"


class ComponentUiScopeTests(unittest.TestCase):
    def render(self, target, proposal=True):
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        tools = (STATIC / "design-tools.js").read_text(encoding="utf-8")
        component = {
            "title": "顶栏适配测试",
            "preview_id": "navigation-fixture",
            "preview_version": "pinned-version",
            "changes": ["保留标题与章节"],
            "scope": "正文页 P02–P09",
            "status": "proposed",
        } if proposal else {}
        state = {
            "approvals": {"stage1": True},
            "candidates": [],
            "pages": [],
            "pending": [],
            "proposal": {
                "design": {
                    "palette": {"primary": "#123456"},
                    "typography": {"display": "Serif", "heading": "Serif",
                                   "body": "Sans", "numbers": "Sans", "sizes": {}},
                    "component_proposal": component,
                },
                "communication": {},
                "transition": {},
                "notes_policy": {},
                "component_pack": {"enabled": False, "chapters": ["第一章"], "items": []},
            },
        }
        setup = """
        const esc=x=>String(x??''),font=()=>'',swatches=()=>'',roleNames={};
        const intro=(tag,title,note)=>`<h1>${title}</h1><p>${note}</p>`;
        const field=(label,id,value)=>`<label>${label}<input id="${id}"></label>`;
        const renderMaterialViewer=()=>'',proposalMaterials=()=>[],viewerOptions=()=>({});
        const pageLogic=()=>'',stageActions=()=>'',candidateCard=()=>'',componentSlots={},componentScopes={};
        const globalSettingsView=()=>'<section>全局配置表单</section>';
        """
        functions = app[app.index("function componentProposal("):app.index("const facetNames=")]
        functions += tools[tools.index("function componentsView("):tools.index("async function chooseComponent(")]
        script = ("const S=" + json.dumps(state, ensure_ascii=False) + ";" +
                  setup + functions + "\nprocess.stdout.write(" + target + "());")
        result = subprocess.run(
            [shutil.which("node") or "node", "-e", script],
            check=True, capture_output=True, text=True, encoding="utf-8")
        return result.stdout, state

    def test_navigation_and_breadcrumb_use_new_name(self):
        index = (STATIC / "index.html").read_text(encoding="utf-8")
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("全局设计与组件", index)
        self.assertIn("components:'全局设计与组件'", app)
        self.assertNotIn("固定组件与留空", index + app)

    def test_component_details_live_in_components_page(self):
        html, _ = self.render("componentsView")
        self.assertIn("<h1>全局设计与组件</h1>", html)
        self.assertEqual(html.count('class="panel component-proposal"'), 1)
        self.assertIn("顶栏适配测试", html)
        self.assertIn("正文页 P02–P09", html)
        self.assertIn('data-id="navigation-fixture"', html)
        self.assertIn('data-version="pinned-version"', html)
        self.assertIn("本次怎么改", html)
        self.assertIn("待确认", html)
        self.assertNotIn('data-action="confirm"', html)

    def test_complete_proposal_goes_directly_from_overview_to_storyboard(self):
        html, _ = self.render("stageTwo")
        self.assertNotIn('class="panel component-proposal"', html)
        self.assertNotIn("本次怎么改", html)
        self.assertNotIn("当前设计系统", html)
        self.assertNotIn("制作与交付选择", html)
        self.assertNotIn('id="palette-primary"', html)
        self.assertNotIn('id="human_policy"', html)
        self.assertRegex(html, r'</div>\s*<section class="panel storyboard-panel"')
        self.assertIn("逐页内容与设计", html)

    def test_components_includes_shared_global_settings(self):
        html, _ = self.render("componentsView")
        self.assertEqual(html.count("全局配置表单"), 1)

    def test_components_page_keeps_pack_pending_and_blank_region_controls(self):
        html, _ = self.render("componentsView")
        self.assertIn("当前组件包", html)
        self.assertIn("尚未启用", html)
        self.assertIn('id="region-page-select"', html)
        self.assertIn('data-action="new-region"', html)
        self.assertIn("当前页面留空安排", html)

    def test_no_proposal_has_no_empty_detail_card(self):
        html, _ = self.render("componentsView", proposal=False)
        self.assertNotIn('class="panel component-proposal"', html)
        self.assertIn("当前组件包", html)

    def test_rendering_does_not_adopt_or_mutate_project(self):
        html, state = self.render("componentsView")
        self.assertFalse(state["proposal"]["component_pack"]["enabled"])
        self.assertEqual(state["proposal"]["design"]["component_proposal"]["status"], "proposed")
        self.assertIn("尚未启用", html)
        # Also inspect the actual JavaScript state after rendering, not only its input fixture.
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        tools = (STATIC / "design-tools.js").read_text(encoding="utf-8")
        helper = app[app.index("function componentProposal("):app.index("function stageTwo(")]
        view = tools[tools.index("function componentsView("):tools.index("async function chooseComponent(")]
        result = subprocess.run(
            [shutil.which("node") or "node", "-e",
             "const S=" + json.dumps(state, ensure_ascii=False) + ";" +
             "const esc=x=>String(x??''),intro=()=>'',globalSettingsView=()=>'',componentSlots={},componentScopes={};" +
             helper + view +
             "const before=JSON.stringify(S);componentsView();process.stdout.write(String(before===JSON.stringify(S)));"],
            check=True, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.stdout, "true")


if __name__ == "__main__":
    unittest.main()
