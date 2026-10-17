"""Page-first studio: draft continuity, honest output states, deck overview."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / "scripts/static/ppt-workbench"


class PageStudioTests(unittest.TestCase):
    def node(self, body):
        script = """
        const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
        global.esc=esc;
        Object.assign(global,require(MATERIALS),require(STORY));
        const ui=require(STUDIO);
        const pages=Array.from({length:10},(_,i)=>({
          page_id:'P'+String(i+1).padStart(2,'0'),title:i?'小节'+(i+1):'见微知著',
          chapter:i?'正文':'平台定位',page_role:i?'content':'cover',
          page_text:'原文'+i,logic:{duration_seconds:18},candidates:[]}));
        const S={pages,proposal:{pages:structuredClone(pages)},pending:[],reference_assets:[],
          reference_decks:[{id:'teacher',page_bindings:{P01:[1]},page_previews:[
          {number:1,image_url:'/teacher.png',native_text:['老师意见']}]}]};
        """.replace("MATERIALS", json.dumps(str(STATIC / "material-viewer.js"))).replace(
            "STORY", json.dumps(str(STATIC / "storyboard.js"))).replace(
            "STUDIO", json.dumps(str(STATIC / "page-studio.js")))
        r = subprocess.run([shutil.which("node"), "-e", script + body],
                           capture_output=True, text=True, encoding="utf-8", check=True)
        return json.loads(r.stdout)

    def test_all_pages_in_navigation_only_current_editor_and_empty_output(self):
        r = self.node("""
          process.stdout.write(JSON.stringify(ui.renderPageStudio(S,{pageId:'P01'})));
        """)
        self.assertEqual(r.count('data-action="studio-page"'), 10)
        self.assertIn('id="story-P01-page_text"', r)
        self.assertNotIn('id="story-P02-page_text"', r)
        self.assertIn('aria-current="page"', r)
        self.assertIn("还没有成图", r)
        self.assertNotIn('src="/teacher.png"', r)
        self.assertIn("备注", r)
        self.assertNotIn('data-stage="samples"', r)

    def test_reference_mode_does_not_offer_adoption_or_count_as_output(self):
        r = self.node("""
          const html=ui.renderPageStudio(S,{pageId:'P01',mode:'references'});
          process.stdout.write(JSON.stringify({html,status:ui.studioPageStatus(S.pages[0])}));
        """)
        self.assertIn('src="/teacher.png"', r["html"])
        self.assertIn("老师参考PPT", r["html"])
        self.assertNotIn('data-action="adopt"', r["html"])
        self.assertEqual(r["status"]["key"], "empty")

    def test_merges_other_page_edits_and_preserves_revert_and_metadata(self):
        r = self.node("""
          const before=JSON.stringify(S);
          const draft={pages:structuredClone(S.proposal.pages),design:{font:'keep'}};
          draft.pages[0].page_text='P01草稿';
          draft.pages[1].remarks='保留P02备注';
          const a=ui.readStudioPages(S.proposal.pages,draft,id=>
            id==='story-P03-page_text'?'P03草稿':undefined,S);
          const b=ui.readStudioPages(S.proposal.pages,{pages:a},id=>
            id==='story-P01-page_text'?'原文0':undefined,S);
          process.stdout.write(JSON.stringify({a,b,unchanged:before===JSON.stringify(S)}));
        """)
        self.assertEqual(r["a"][0]["page_text"], "P01草稿")
        self.assertEqual(r["a"][1]["remarks"], "保留P02备注")
        self.assertEqual(r["a"][2]["page_text"], "P03草稿")
        self.assertEqual(r["b"][0]["page_text"], "原文0")
        self.assertEqual(r["b"][2]["page_text"], "P03草稿")
        self.assertTrue(r["unchanged"])

    def test_deck_is_contact_sheet_not_second_editor_and_never_uses_reference_as_output(self):
        r = self.node("""
          S.pages[1].selected={url:'/real.png',kind:'user_import',audit_status:'passed',sha256:'v1'};
          S.pages[2].selected={url:'/fake.png',kind:'reference',audit_status:'passed'};
          process.stdout.write(JSON.stringify(ui.renderDeckOverview(S,{})));
        """)
        self.assertEqual(r.count('data-action="studio-open"'), 10)
        self.assertIn('src="/real.png', r)
        self.assertNotIn('src="/teacher.png', r)
        self.assertNotIn('src="/fake.png', r)
        self.assertNotIn("<textarea", r)
        self.assertIn("180", r)
        self.assertIn("已选用", r)

    def test_output_versions_and_existing_audit_gate(self):
        r = self.node("""
          S.pages[0].candidates=[{id:'candidate-1',url:'/c.png',kind:'user_import',audit_status:'pending'}];
          const waiting=ui.renderPageStudio(S,{pageId:'P01'});
          S.pages[0].candidates[0].audit_status='passed';
          const ready=ui.renderPageStudio(S,{pageId:'P01'});
          S.pending=[{status:'draft',patch:{design:{font:'changed'}}}];
          const blocked=ui.renderPageStudio(S,{pageId:'P01'});
          process.stdout.write(JSON.stringify({waiting,ready,blocked}));
        """)
        self.assertRegex(r["waiting"], r'data-action="adopt"[^>]*disabled')
        self.assertNotRegex(r["ready"], r'data-action="adopt"[^>]*disabled')
        self.assertRegex(r["blocked"], r'data-action="adopt"[^>]*disabled')

    def test_current_adopted_candidate_is_not_duplicated_in_history(self):
        r = self.node("""
          const pg={selected:{url:'/selected',kind:'user_import',sha256:'current'},
            candidates:[{id:'old',url:'/old',kind:'user_import',status:'adopted',sha256:'old'},
            {id:'new',url:'/new',kind:'user_import',status:'adopted',sha256:'current'}]};
          process.stdout.write(JSON.stringify(ui.studioOutputVersions(pg).map(x=>x.studioKey)));
        """)
        self.assertEqual(r, ["selected", "old"])

    def test_integration_maps_studio_drafts_to_shared_stage2_and_flushes_before_switch(self):
        text = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("readStudioPages(original.pages", text)
        self.assertIn("['components','samples'].includes(view())?'stage2'", text)
        handler = text[text.index("if(a==='studio-page'"):text.index("if(a==='proposal-details'")]
        self.assertIn("formAutosave.flush('stage2')", handler)
        self.assertIn("studio-open", handler)


if __name__ == "__main__":
    unittest.main()
