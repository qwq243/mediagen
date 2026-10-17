"""Shared global configuration and read-only overview, no real project writes."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

STATIC = Path(__file__).resolve().parents[1] / "scripts" / "static" / "ppt-workbench"


class ProposalSettingsTests(unittest.TestCase):
    def run_js(self, code, draft=None):
        source = (STATIC / "proposal-settings.js").read_text(encoding="utf-8")
        state = {
            "project": "测试方案", "pages": [], "pending": [],
            "proposal": {
                "design": {
                    "palette": {"primary": "#123456", "secondary_bg": "#fafafa"},
                    "typography": {"display": "Serif", "heading": "Serif", "body": "Sans",
                                   "numbers": "Mono", "sizes": {"heading": 40}},
                    "human_policy": "none", "icons": "线性图标",
                    "material": "<img src=x onerror=alert(1)>", "grid": "12 栏",
                    "text_in_image": True,
                },
                "communication": {"reading_mode": "presentation", "core_message": "保持原意"},
                "production_route": "full_image",
                "notes_policy": {"enabled": True, "mode": "optimize", "extra": "保留"},
                "transition": {"enabled": False, "duration": 0.4, "advance": "manual"},
                "component_pack": {"enabled": False, "chapters": ["章一"], "items": []},
                "pages": [],
            },
        }
        setup = """
        const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
        const font=esc,swatches=()=>'<div class="swatches"></div>';
        const roleNames={none:'不出现人物'};
        const field=(label,id,value)=>`<label>${label}<input id="${id}" value="${esc(value)}"></label>`;
        const formAutosave={getPatch:()=>(DRAFT)};
        const nodes={}; const $=s=>nodes[s.slice(1)]||null;
        """
        script = ("const S=" + json.dumps(state, ensure_ascii=False) + ";" +
                  setup.replace("DRAFT", json.dumps(draft or {}, ensure_ascii=False)) +
                  source + "\n" + code)
        result = subprocess.run([shutil.which("node") or "node", "-e", script],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_details_are_read_only_escaped_and_use_current_shared_draft(self):
        draft = {"production_route": "external"}
        html = self.run_js("process.stdout.write(globalSettingsDetails('production'));", draft)
        self.assertIn("本机制作", html)
        self.assertIn('data-action="configure-global"', html)
        self.assertNotRegex(html, r"<(?:input|textarea|select)\b")
        design = self.run_js("process.stdout.write(globalSettingsDetails('design'));")
        self.assertIn("&lt;img", design)
        self.assertIn("次级背景色", design)
        self.assertNotIn("<img src=x", design)

    def test_all_moved_fields_only_render_in_configuration(self):
        html = self.run_js("process.stdout.write(globalSettingsView());")
        for field in ["palette-primary", "palette-secondary_bg", "font-display", "font-heading",
                      "font-body", "size-heading", "icons", "material", "grid", "components-enabled",
                      "chapters", "human_policy", "reading_mode", "production_route", "text_in_image",
                      "notes_mode", "transition-enabled", "transition-duration", "stage-comment"]:
            self.assertEqual(html.count(f'id="{field}"'), 1, field)
        self.assertIn('data-action="draft"', html)
        self.assertIn('data-action="submit"', html)
        self.assertNotIn('data-action="confirm"', html)

    def test_summary_is_compact_buttons_not_duplicate_inputs(self):
        html = self.run_js("process.stdout.write(globalSettingsSummary());",
                           {"production_route": "external"})
        self.assertIn('data-action="proposal-details"', html)
        self.assertIn("草稿", html)
        self.assertIn("本机制作", html)
        self.assertNotRegex(html, r"<(?:input|textarea|select)\b")

    def test_settings_patch_preserves_hidden_state_and_stage2_handles_absent_controls(self):
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        patch = app[app.index("function stagePatch("):app.index("const chips=")]
        code = """
        const document={getElementById:()=>null};
        const readStoryboardPages=pages=>pages;
        """ + patch + """
        if(JSON.stringify(stagePatch('stage2'))!=='{}')throw Error('offscreen fields changed');
        if(JSON.stringify(globalSettingsPatch())!=='{}')throw Error('missing fields changed');
        nodes['production_route']={value:'external'};
        nodes['font-body']={value:'Updated'};
        nodes['reading_mode']={value:'balanced'};
        const p=globalSettingsPatch();
        if(p.design.typography.body!=='Updated'||p.design.material!==S.proposal.design.material)
          throw Error('design data lost');
        if(p.communication.core_message!=='保持原意')throw Error('communication lost');
        process.stdout.write(JSON.stringify(p));
        """
        patch = json.loads(self.run_js(code))
        self.assertEqual(patch["production_route"], "external")
        self.assertNotIn("pages", patch)

    def test_script_loaded_and_summary_is_inside_candidate_card(self):
        index = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('/workbench/proposal-settings.js', index)
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        candidate = app[app.index("function candidateCard("):app.index("function swatches(")]
        self.assertIn("${globalSettingsSummary()}", candidate)


if __name__ == "__main__":
    unittest.main()
