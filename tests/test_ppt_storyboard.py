"""Compact, editable storyboard with pinned per-page reference/evidence previews."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "scripts"))
import ppt_content_sources as sources
import ppt_confirm_ui as ui
import ppt_studio as studio
import ppt_workflow as wf


class StoryboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "speech.docx").write_bytes(b"speech fixture")
        (self.root / "speech.md").write_text("## para-001\n第一段\n\n## para-003\n第三段", encoding="utf-8")
        self.ref = {"id": "speech", "role": "content", "original_name": "讲稿.docx",
                    "path": "speech.docx", "sha256": wf.file_sha(self.root / "speech.docx"),
                    "note": "这份讲稿的边界",
                    "extraction": {"path": "speech.md", "sha256": wf.file_sha(self.root / "speech.md")}}
        self.p = wf.upgrade({"test_fixture": True, "pages": [
            {"page_id": f"P{i:02d}", "page_text": "页面文字",
             "logic": {"evidence": [{"source": "speech", "paragraph_ids": ["para-003"]}]}}
            for i in range(1, 11)]})
        self.p["references"] = [self.ref]
        wf.save(self.root, self.p)

    def tearDown(self):
        self.tmp.cleanup()

    def test_individual_notes_preserve_intentional_empty_text(self):
        self.p["communication"]["source_notes"] = {"speech": ""}
        self.assertEqual(sources.summaries(self.root, self.p)[0].get("note"), "")
        self.p["communication"]["source_notes"]["speech"] = "单独备注"
        self.assertEqual(sources.summaries(self.root, self.p)[0].get("note"), "单独备注")

    def test_evidence_opens_only_the_exact_pinned_paragraphs_even_if_historical(self):
        fn = getattr(sources, "evidence_preview", None)
        self.assertTrue(callable(fn), "missing clickable evidence preview")
        self.ref["superseded_by"] = "new-speech"
        result = fn(self.root, self.p, "P01", 0)
        self.assertEqual([x["id"] for x in result["paragraphs"]], ["para-003"])
        self.assertTrue(result["historical"])
        self.assertEqual(result["paragraphs"][0]["text"], "第三段")
        self.assertNotIn("path", result)
        with self.assertRaises(ValueError):
            fn(self.root, self.p, "P01", 99)
        (self.root / "speech.docx").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            fn(self.root, self.p, "P01", 0)

    def test_ten_page_edit_fields_are_recoverable_drafts_not_silent_application(self):
        proposal = copy.deepcopy(studio.proposal(self.p))
        fields = {f"story-{pg['page_id']}-{field}": "可编辑"
                  for pg in self.p["pages"] for field in (
                      "title", "chapter", "page_text", "purpose", "key_message_or_question",
                      "visual_expression", "transition_in", "transition_out", "information_relationship")}
        fields.update({f"story-P{i:02d}-duration_seconds": "18" for i in range(1, 11)})
        fields["font-heading"] = "Noto Serif SC"  # More than the legacy 100-field cap.
        changed = copy.deepcopy(proposal["pages"])
        changed[0]["page_text"] = ""
        r = studio.autosave_form(self.root, self.p, "stage2", {"pages": changed}, form_values=fields)
        self.assertEqual(r["details"]["form_values"], fields)
        self.assertEqual(r["patch"]["pages"][0]["page_text"], "")
        self.assertEqual(studio.proposal(wf.load(self.root)), proposal)
        self.assertFalse(self.p["generation_calls"])
        self.assertFalse(self.p["approvals"])
        for name in ("story-UNKNOWN-page_text", "story-P01-selected_output"):
            with self.assertRaises(ValueError):
                studio.autosave_form(self.root, self.p, "stage2", {}, form_values={name: "bad"})

    def test_source_notes_autosave_and_evidence_http_read_only(self):
        studio.autosave_form(self.root, self.p, "stage1",
                            {"communication": {**self.p["communication"], "source_notes": {"speech": "备注"}}},
                            form_values={"source-note-speech": "备注"})
        before = wf.file_sha(self.root / wf.PACK)
        web = ui.create_app(self.root, self.root / "library").test_client()
        response = web.get("/api/v3/pages/P01/evidence/0")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["paragraphs"][0]["id"], "para-003")
        self.assertEqual(before, wf.file_sha(self.root / wf.PACK))

    def test_page_remarks_are_recoverable_drafts_separate_from_source_and_script(self):
        changed = copy.deepcopy(studio.proposal(self.p)["pages"])
        changed[0]["remarks"] = "老师意见：“见微知著”小些，目前还没到宣传品牌的时候。"
        before = copy.deepcopy(self.p)
        record = studio.autosave_form(
            self.root, self.p, "stage2", {"pages": changed},
            form_values={"story-P01-remarks": changed[0]["remarks"]})
        self.assertEqual(record["patch"]["pages"][0]["remarks"], changed[0]["remarks"])
        self.assertEqual(self.p["pages"], before["pages"])
        self.assertEqual(self.p["references"], before["references"])
        self.assertEqual(self.p["approvals"], before["approvals"])
        changed[0]["remarks"] = ""
        record = studio.autosave_form(
            self.root, self.p, "stage2", {"pages": changed},
            form_values={"story-P01-remarks": ""}, draft_id=record["id"],
            draft_version=record["details"]["autosave_version"])
        self.assertEqual(record["patch"]["pages"][0]["remarks"], "")


class StoryboardUiTests(unittest.TestCase):
    def node(self, expr):
        path = BASE / "scripts/static/ppt-workbench/storyboard.js"
        self.assertTrue(path.is_file(), "missing compact storyboard renderer")
        script = "global.esc=x=>String(x??'').replace(/</g,'&lt;');const ui=require(" + json.dumps(str(path)) + ");\n"
        script += "Object.assign(global,require(" + json.dumps(str(path.with_name("material-viewer.js"))) + "));\n"
        return subprocess.run([shutil.which("node"), "-e", script + expr], capture_output=True,
                              text=True, encoding="utf-8", check=True).stdout

    def test_open_editable_text_and_reference_thumbnail_with_whole_deck_navigation(self):
        result = self.node("""
          const pg={page_id:'P01',title:'标题',page_text:'<可编辑>',logic:{evidence:[{source:'speech',paragraph_ids:['para-001']}]}};
          const s={content_sources:[{id:'speech',original_name:'讲稿.docx'}],reference_decks:[{id:'deck',page_bindings:{P01:[2]},
            page_previews:[{number:2,image_url:'/image2',native_text:['老师改字'],note:'适配待对齐'}]}]};
          process.stdout.write(ui.renderStoryboardPage(pg,s));
        """)
        self.assertIn('id="story-P01-page_text"', result)
        self.assertIn("&lt;可编辑>", result)
        self.assertIn('data-action="page-evidence"', result)
        self.assertIn('data-start-page="2"', result)
        self.assertIn('src="/image2"', result)
        self.assertNotIn("查看页面文字</summary>", result)

    def test_editor_patch_retains_empty_text_and_unrelated_page_metadata(self):
        result = json.loads(self.node("""
          const pages=[{page_id:'P01',title:'原名',page_text:'原文',logic:{purpose:'旧目的',evidence:[{source:'pinned'}]},reference_ids:['keep']}];
          const values={'story-P01-page_text':'','story-P01-purpose':'新目的'};
          process.stdout.write(JSON.stringify(ui.readStoryboardPages(pages,id=>values[id])));
        """))
        self.assertEqual(result[0]["page_text"], "")
        self.assertEqual(result[0]["logic"]["purpose"], "新目的")
        self.assertEqual(result[0]["logic"]["evidence"], [{"source": "pinned"}])
        self.assertEqual(result[0]["reference_ids"], ["keep"])

    def test_remarks_editor_keeps_source_as_initial_copy_and_respects_empty_edits(self):
        result = json.loads(self.node("""
          const state={reference_decks:[{page_bindings:{P01:[1]},
            page_previews:[{number:1,native_text:['老师原意见']}]}]};
          const pg={page_id:'P01',page_text:'正文'};
          const before=JSON.stringify(state);
          const initial=ui.renderStoryboardPage(pg,state);
          const blank=ui.renderStoryboardPage({...pg,remarks:''},state);
          const patch=ui.readStoryboardPages([pg],id=>id==='story-P01-remarks'?'':undefined,state);
          const untouched=ui.readStoryboardPages([pg],id=>id==='story-P01-remarks'?'老师原意见':undefined,state);
          process.stdout.write(JSON.stringify({initial,blank,patch,untouched,sourceUnchanged:before===JSON.stringify(state)}));
        """))
        self.assertIn('id="story-P01-remarks"', result["initial"])
        self.assertIn("<span>备注</span>", result["initial"])
        self.assertIn("老师原意见", result["initial"])
        self.assertNotIn("源页文字 / 老师意见", result["initial"])
        self.assertNotIn("老师原意见", result["blank"])
        self.assertEqual(result["patch"][0]["remarks"], "")
        self.assertNotIn("remarks", result["untouched"][0])
        self.assertTrue(result["sourceUnchanged"])

    def test_legacy_whole_sample_gate_still_requires_real_audited_outputs(self):
        path = BASE / "scripts/static/ppt-workbench/app.js"
        self.assertIn("function sampleConfirmationReady", path.read_text(encoding="utf-8"))
        script = """
          const text=require('fs').readFileSync(PATH,'utf8');
          const part=text.slice(text.indexOf('function sampleConfirmationReady'),text.indexOf('function imageCard'));
          const esc=x=>x??'',intro=()=>'',referenceDeckPanel=()=>'',imageCard=()=>'',S={
            check:{sample_page_ids:['P01'],ok:true},pending:[],approvals:{stage2:false},
            progress:[{id:'stage2',complete:false}],pages:[{page_id:'P01',candidates:[]}]};
          eval(part);
          const emptyReady=sampleConfirmationReady();
          S.progress[0].complete=true;S.approvals.stage2=true;
          S.pages[0].selected={kind:'reference',audit_status:'passed'};
          const referenceReady=sampleConfirmationReady();
          S.pages[0].selected={kind:'agent_composite',audit_status:'passed'};
          const realReady=sampleConfirmationReady();
          S.pending=[{status:'draft'}];
          const pendingReady=sampleConfirmationReady();
          process.stdout.write(JSON.stringify({emptyReady,referenceReady,realReady,pendingReady}));
        """.replace("PATH", json.dumps(str(path)))
        run = subprocess.run([shutil.which("node"), "-e", script], capture_output=True,
                             text=True, encoding="utf-8", check=True)
        result = json.loads(run.stdout)
        self.assertFalse(result["emptyReady"])
        self.assertFalse(result["referenceReady"])
        self.assertTrue(result["realReady"])
        self.assertFalse(result["pendingReady"])

    def test_no_reference_material_does_not_create_an_empty_reference_section(self):
        result = self.node("""
          process.stdout.write(ui.renderStoryboardPage({page_id:'P01',page_text:'正文'},{}));
        """)
        self.assertNotIn("对应参考PPT", result)
        self.assertNotIn("本页尚未关联参考PPT", result)
        self.assertIn("页面文字 · 可编辑草稿", result)

    def test_no_top_level_reference_block_or_shared_boundary_in_stage1(self):
        text = (BASE / "scripts/static/ppt-workbench/app.js").read_text(encoding="utf-8")
        stage1 = text[text.index("function stageOne"):text.index("function candidateCard")]
        stage2 = text[text.index("function stageTwo"):text.index("function sourceLabel") if "function sourceLabel" in text else text.index("function imagesView")]
        self.assertNotIn("briefField('调整与事实边界'", stage1)
        self.assertNotIn("referenceDeckPanel('stage2')+", stage2)
        self.assertIn("sourceNoteField(r)", text)
        self.assertIn("readStoryboardPages(original.pages", text)
        handler = text[text.index("if(a==='reference-deck-preview')"):text.index("if(a==='reference-deck-page')")]
        self.assertIn("getElementById('source-note-'", handler)


if __name__ == "__main__":
    unittest.main()
