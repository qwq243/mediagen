"""Reference galleries and scripts are read-only until explicitly edited."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "scripts"))
import ppt_content_sources as sources
import ppt_studio as studio
import ppt_workbench as workbench
import ppt_workflow as wf


class MaterialViewerTests(unittest.TestCase):
    def node(self, code):
        folder = BASE / "scripts/static/ppt-workbench"
        script = "global.esc=x=>String(x??'').replace(/</g,'&lt;');"
        script += "Object.assign(global,require(" + json.dumps(str(folder / "material-viewer.js")) + "));"
        script += "const story=require(" + json.dumps(str(folder / "storyboard.js")) + ");"
        return subprocess.run([shutil.which("node"), "-e", script + code], check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout

    def test_top_gallery_groups_reference_ppt_and_related_asset_types(self):
        result = self.node("""
          const s={reference_decks:[{id:'d',title:'老师稿',page_previews:[{number:1,image_url:'/p1'}]}],
            reference_assets:[{id:'b',version:'fixed',kind:'brand',title:'校徽',url:'/brand',origin:'related'}]};
          process.stdout.write(renderMaterialViewer('proposal',proposalMaterials(s),{vertical:true}));
        """)
        for text in ("老师参考PPT", "品牌素材", "material-rail", "is-vertical",
                     'data-action="material-select"', 'data-action="material-fullscreen"', 'src="/p1"'):
            self.assertIn(text, result)
        self.assertNotIn("已采用", result)

    def test_reference_thumbnails_use_bound_section_names_and_keep_source_location(self):
        result = json.loads(self.node("""
          const pg={page_id:'P01',title:'见微知著',chapter:'平台定位'};
          const s={pages:[pg],reference_decks:[{id:'d',original_name:'老师稿.pptx',
            page_bindings:{P01:[3]},page_previews:[{number:3,image_url:'/p3',title:'源第 3 页 · 封面'}]}]};
          const before=JSON.stringify(s);
          const top=proposalMaterials(s),local=pageMaterials(pg,s);
          process.stdout.write(JSON.stringify({top,local,unchanged:JSON.stringify(s)===before,
            html:renderMaterialViewer('proposal',top,{vertical:true})}));
        """))
        self.assertEqual(result["top"][0]["title"], "见微知著")
        self.assertEqual(result["local"][0]["title"], "见微知著")
        self.assertEqual(result["top"][0]["number"], 3)
        self.assertTrue(result["unchanged"])
        self.assertIn("<span>见微知著</span>", result["html"])
        self.assertIn('title="见微知著 · 老师稿.pptx · 源第 3 页"', result["html"])
        self.assertNotIn("<span>源第 3 页</span>", result["html"])

    def test_section_labels_do_not_invent_positional_or_ambiguous_bindings(self):
        result = json.loads(self.node("""
          const s={pages:[{page_id:'P01',title:'不相关第一页'},
            {page_id:'P02',title:'场景需求'},{page_id:'P03',title:'四个角色'}],
            reference_decks:[{id:'d',page_bindings:{P02:[2],P03:[2]},
              page_previews:[{number:1,image_url:'/p1',title:'源第 1 页'},
                {number:2,image_url:'/p2',title:'源第 2 页 · 角色与场景'},
                {number:3,image_url:'/p3',native_text:['老师说要改标题']}]}]};
          process.stdout.write(JSON.stringify({top:referenceMaterials(s),
            local:pageMaterials(s.pages[1],s)}));
        """))
        self.assertEqual([x["title"] for x in result["top"]],
                         ["源第 1 页", "角色与场景", "源第 3 页"])
        self.assertEqual(result["local"][0]["title"], "场景需求")

    def test_long_section_labels_are_not_truncated_in_metadata(self):
        title = "核心创新：可装配智能体与过程即资产"
        result = self.node("""
          process.stdout.write(renderMaterialViewer('P04',[{key:'d:4',id:'d',group:'teacher',
            number:4,title:'核心创新：可装配智能体与过程即资产',subtitle:'老师稿.pptx',url:'/p4'}],{all:true}));
        """)
        self.assertIn(f"<span>{title}</span>", result)
        self.assertIn(f'title="{title} · 老师稿.pptx · 源第 4 页"', result)
        css = (BASE / "scripts/static/ppt-workbench/material-viewer.css").read_text(encoding="utf-8")
        self.assertIn("-webkit-line-clamp:2", css)

    def test_page_versions_are_real_and_distinguished_from_source(self):
        result = json.loads(self.node("""
          const s={reference_decks:[{id:'d',page_bindings:{P01:[2]},
            page_previews:[{number:2,image_url:'/ref'}]}]};
          const pg={page_id:'P01',selected:{id:'old',url:'/selected',kind:'user_import',sha256:'a'},
            candidates:[{id:'new',url:'/candidate',kind:'generated',sha256:'b'}]};
          process.stdout.write(JSON.stringify(pageMaterials(pg,s)));
        """))
        self.assertEqual([x["group"] for x in result], ["versions", "versions", "teacher"])
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["url"], "/selected?v=a")
        self.assertEqual(result[2]["number"], 2)
        only_ref = json.loads(self.node("""
          process.stdout.write(JSON.stringify(pageMaterials({page_id:'P01'},{
            reference_decks:[{id:'d',page_bindings:{P01:[1]},page_previews:[{number:1,image_url:'/ref'}]}]})));
        """))
        self.assertEqual(len(only_ref), 1)
        self.assertEqual(only_ref[0]["group"], "teacher")

    def test_comments_left_script_below_viewer_and_no_long_disclaimers(self):
        html = self.node("""
          const pg={page_id:'P01',page_text:'正文',logic:{},
            script_sources:[{title:'讲稿',paragraphs:[{text:'这是本页讲稿',citation:'speech/para-001'}]}]};
          const s={reference_decks:[{id:'d',page_bindings:{P01:[1]},
            page_previews:[{number:1,image_url:'/ref',native_text:['老师改字']}]}]};
          process.stdout.write(story.renderStoryboardPage(pg,s));
        """)
        left, right = html.split('<aside class="story-materials"', 1)
        self.assertIn("老师改字", left)
        self.assertNotIn("老师改字", right)
        self.assertLess(right.index("material-viewer"), right.index("这是本页讲稿"))
        self.assertIn('id="story-P01-speaker_notes"', right)
        self.assertIn('data-action="script-edit"', right)
        self.assertNotIn("非实际样张", html)
        self.assertNotIn("点击查看整份PPT", html)

    def test_script_edits_patch_top_level_and_preserve_empty(self):
        result = json.loads(self.node("""
          process.stdout.write(JSON.stringify(story.readStoryboardPages(
            [{page_id:'P01',speaker_notes:'旧讲稿',logic:{purpose:'保留'}}],
            id=>id==='story-P01-speaker_notes'?'':undefined)));
        """))
        self.assertEqual(result[0]["speaker_notes"], "")
        self.assertEqual(result[0]["logic"], {"purpose": "保留"})

    def test_script_sources_verified_and_safe_unavailable_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "speech.docx").write_bytes(b"fixture")
            (root / "speech.md").write_text("## para-001\n原稿讲述", encoding="utf-8")
            p = wf.upgrade({"test_fixture": True, "pages": [{"page_id": "P01",
                "logic": {"evidence": [{"source": "speech", "paragraph_ids": ["para-001"]}]}}]})
            p["references"] = [{"id": "speech", "role": "content", "path": "speech.docx",
                "sha256": wf.file_sha(root / "speech.docx"),
                "extraction": {"path": "speech.md", "sha256": wf.file_sha(root / "speech.md")}}]
            before = copy.deepcopy(p)
            rows = sources.page_script_sources(root, p, "P01")
            self.assertEqual(rows[0]["paragraphs"][0]["text"], "原稿讲述")
            self.assertEqual(p, before)
            (root / "speech.docx").write_bytes(b"changed")
            rows = sources.page_script_sources(root, p, "P01")
            self.assertEqual(rows[0]["paragraphs"], [])
            self.assertEqual(rows[0]["availability"], "unavailable")

    def test_related_assets_fixed_versions_and_skip_removed_members(self):
        records = {"a": {"id": "a", "version": "v1", "title": "网页", "kind": "webpage"},
                   "b": {"id": "b", "version": "v2", "title": "校徽", "kind": "brand"}}
        def get(ident, version, library):
            if ident not in records or version != records[ident]["version"]:
                raise ValueError("missing pinned version")
            return records[ident]
        with patch.object(workbench.assets, "get", side_effect=get), \
             patch.object(workbench.coding, "bundle_context", return_value={"members": [
                 {**records["b"], "available": True},
                 {"id": "hidden", "version": "v3", "available": True, "archived": True}]}):
            p = {"asset_selection": [], "design": {}}
            rows = workbench.material_previews(p, [{"id": "a", "version": "v1"}], Path("."))
            self.assertEqual([x["id"] for x in rows], ["a", "b"])
            self.assertEqual(rows[1]["version"], "v2")
            self.assertIn("version=v2", rows[1]["url"])
            self.assertFalse(any(x.get("adopted") for x in rows))

    def test_script_field_allowed_in_autosave_without_applying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = wf.upgrade({"test_fixture": True, "pages": [{"page_id": "P01", "speaker_notes": ""}]})
            wf.save(root, p)
            r = studio.autosave_form(root, p, "stage2", {}, form_values={"story-P01-speaker_notes": "讲稿草稿"})
            self.assertEqual(r["details"]["form_values"]["story-P01-speaker_notes"], "讲稿草稿")
            self.assertEqual(wf.load(root)["pages"][0]["speaker_notes"], "")

    def test_page_bound_library_reference_is_not_output_or_unrelated_page(self):
        result = json.loads(self.node("""
          const pg={page_id:'P01',title:'封面',candidates:[]};
          const s={reference_decks:[{id:'teacher',page_bindings:{P01:[1]},
            page_previews:[{number:1,image_url:'/teacher'}]}],
            reference_assets:[{id:'cover',version:'fixed',kind:'slide',title:'封面构图参考',
              origin:'reference',page_ids:['P01'],url:'/cover?version=fixed'}]};
          const before=JSON.stringify({pg,s});
          process.stdout.write(JSON.stringify({local:pageMaterials(pg,s),
            other:pageMaterials({page_id:'P02'},s),top:proposalMaterials(s),
            unchanged:before===JSON.stringify({pg,s})}));
        """))
        self.assertEqual([x["group"] for x in result["local"]], ["teacher", "ppt"])
        self.assertEqual(result["local"][1]["version"], "fixed")
        self.assertEqual(result["local"][1]["subtitle"], "页面参考")
        self.assertEqual(result["other"], [])
        self.assertEqual(result["top"][1]["id"], "cover")
        self.assertTrue(result["unchanged"])

    def test_registered_reference_pin_merges_page_bindings_without_adoption(self):
        record = {"id": "cover", "version": "fixed", "title": "封面构图参考", "kind": "slide"}
        p = {"references": [
                {"id": "ref-a", "role": "style", "asset_id": "cover", "asset_version": "fixed"},
                {"id": "ref-b", "role": "layout", "asset_id": "cover", "asset_version": "fixed"}],
             "pages": [{"page_id": "P01", "reference_ids": ["ref-a"]},
                       {"page_id": "P02", "reference_ids": ["ref-b"]},
                       {"page_id": "P03", "reference_ids": []}],
             "asset_selection": [], "design": {}}
        before = copy.deepcopy(p)
        with patch.object(workbench.assets, "get", return_value=record) as get, \
             patch.object(workbench.coding, "bundle_context", return_value=None):
            rows = workbench.material_previews(p, [{"id": "cover", "version": "fixed"}], Path("."))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["page_ids"], ["P01", "P02"])
        self.assertEqual(rows[0]["origin"], "reference")
        self.assertIn("version=fixed", rows[0]["url"])
        get.assert_called_once_with("cover", "fixed", Path("."))
        self.assertEqual(p, before)
        self.assertFalse(rows[0].get("adopted"))

    def test_missing_reference_version_never_falls_back_to_latest(self):
        p = {"references": [
                {"id": "missing", "asset_id": "cover", "asset_version": "gone"},
                {"id": "unpinned", "asset_id": "cover"}],
             "pages": [{"page_id": "P01", "reference_ids": ["missing", "unpinned"]}]}
        with patch.object(workbench.assets, "get", side_effect=ValueError("missing pinned version")) as get:
            self.assertEqual(workbench.material_previews(p, [], Path(".")), [])
        get.assert_called_once_with("cover", "gone", Path("."))


if __name__ == "__main__":
    unittest.main()
