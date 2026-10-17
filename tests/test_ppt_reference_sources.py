"""Project content-reference decks, not style picks, samples or approvals."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ppt_content_sources as sources
import ppt_confirm_ui as ui
import ppt_workflow as wf

STATIC = Path(__file__).resolve().parents[1] / "scripts/static/ppt-workbench/app.js"


class ReferenceSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "job"
        self.library = Path(self.tmp.name) / "library"
        (self.root / "inputs").mkdir(parents=True)
        (self.root / "inputs/teacher.pptx").write_bytes(b"pinned-pptx-fixture")
        (self.root / "inputs/page1.png").write_bytes(b"original-render-fixture")
        self.manifest = {
            "source_sha256": wf.file_sha(self.root / "inputs/teacher.pptx"),
            "pages": [{"number": 1, "title": "封面",
                       "image": {"path": "inputs/page1.png",
                                 "sha256": wf.file_sha(self.root / "inputs/page1.png")},
                       "native_text": ["智慧基座雏形；让图书馆成为智慧伙伴"],
                       "comments": ["正式批注"], "speaker_notes": "演讲者备注",
                       "note": "替换原标语，不是追加一段。"}]}
        self.write_manifest()
        self.p = wf.upgrade({"test_fixture": True, "project_name": "reference-test",
                             "pages": [{"page_id": "P01", "page_text": "旧封面"}]})
        self.ref = {
            "id": "teacher-ppt", "role": "content", "content_kind": "reference_presentation",
            "original_name": "老师参考.pptx", "title": "老师参考",
            "path": "inputs/teacher.pptx", "sha256": self.manifest["source_sha256"],
            "use": "内容及老师修改意见", "note": "不是最终设计或实际样张。",
            "presentation": {"path": "inputs/deck.json",
                             "sha256": wf.file_sha(self.root / "inputs/deck.json")}}
        self.p["references"] = [self.ref]
        wf.save(self.root, self.p)

    def write_manifest(self):
        (self.root / "inputs/deck.json").write_text(
            json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8")

    def call(self, name, *args):
        fn = getattr(sources, name, None)
        self.assertTrue(callable(fn), f"missing reference-source API: {name}")
        return fn(self.root, self.p, *args)

    def tearDown(self):
        self.tmp.cleanup()

    def test_optional_deck_is_separate_from_speech_and_no_mapping_is_invented(self):
        self.assertEqual(sources.summaries(self.root, self.p), [])
        rows = self.call("reference_summaries")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["page_count"], 1)
        self.assertEqual(rows[0]["status"], "verified")
        self.assertEqual(rows[0]["note"], self.ref["note"])
        self.assertEqual(rows[0]["page_bindings"], {})
        self.p["references"] = []
        self.assertEqual(self.call("reference_summaries"), [])

    def test_preview_retains_overlay_text_formal_comments_and_speaker_notes(self):
        result = self.call("reference_preview", "teacher-ppt")
        page = result["pages"][0]
        self.assertEqual(page["native_text"], self.manifest["pages"][0]["native_text"])
        self.assertEqual(page["comments"], ["正式批注"])
        self.assertEqual(page["speaker_notes"], "演讲者备注")
        self.assertEqual(page["note"], self.manifest["pages"][0]["note"])
        self.assertEqual(page["image_url"], "/api/v3/reference-decks/teacher-ppt/pages/1/image")
        self.assertTrue(result["reference_only"])
        self.assertNotIn("path", page)

    def test_source_manifest_and_image_tampering_are_blocked(self):
        for filename in ("teacher.pptx", "deck.json", "page1.png"):
            with self.subTest(filename=filename):
                path = self.root / "inputs" / filename
                original = path.read_bytes()
                path.write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    self.call("reference_image", "teacher-ppt", 1)
                path.write_bytes(original)

    def test_outside_image_and_wrong_source_manifest_are_blocked(self):
        outside = Path(self.tmp.name) / "outside.png"
        outside.write_bytes(b"private-outside-image")
        self.manifest["pages"][0]["image"] = {
            "path": str(outside), "sha256": wf.file_sha(outside)}
        self.write_manifest()
        self.ref["presentation"]["sha256"] = wf.file_sha(self.root / "inputs/deck.json")
        with self.assertRaises(ValueError):
            self.call("reference_image", "teacher-ppt", 1)
        self.manifest["source_sha256"] = "0" * 64
        self.write_manifest()
        self.ref["presentation"]["sha256"] = wf.file_sha(self.root / "inputs/deck.json")
        with self.assertRaises(ValueError):
            self.call("reference_preview", "teacher-ppt")

    def test_archived_sources_missing_pages_and_duplicate_numbers_are_not_served(self):
        with self.assertRaises(ValueError):
            self.call("reference_image", "teacher-ppt", 99)
        self.manifest["pages"].append(copy.deepcopy(self.manifest["pages"][0]))
        self.write_manifest()
        self.ref["presentation"]["sha256"] = wf.file_sha(self.root / "inputs/deck.json")
        with self.assertRaises(ValueError):
            self.call("reference_preview", "teacher-ppt")
        self.ref["superseded_by"] = "new"
        self.assertEqual(self.call("reference_summaries"), [])
        with self.assertRaises(ValueError):
            self.call("reference_preview", "teacher-ppt")

    def test_read_only_routes_work_before_samples_unlock_without_changing_state(self):
        before = wf.file_sha(self.root / wf.PACK)
        web = ui.create_app(self.root, self.library).test_client()
        state = web.get("/api/v3/workbench").get_json()
        self.assertEqual(len(state.get("reference_decks", [])), 1)
        self.assertFalse(next(x for x in state["progress"] if x["id"] == "samples")["accessible"])
        response = web.get("/api/v3/reference-decks/teacher-ppt/preview")
        self.assertEqual(response.status_code, 200)
        image = web.get("/api/v3/reference-decks/teacher-ppt/pages/1/image")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.data, b"original-render-fixture")
        image.close()
        self.assertEqual(web.post("/api/v3/reference-decks/teacher-ppt/preview").status_code, 403)
        self.assertEqual(web.post("/api/v3/reference-decks/teacher-ppt/preview",
                                 headers={"X-Mediagen-CSRF": state["csrf"]}).status_code, 405)
        self.assertEqual(before, wf.file_sha(self.root / wf.PACK))
        self.assertEqual(wf.load(self.root)["pages"][0]["page_text"], "旧封面")
        self.assertFalse(wf.load(self.root)["approvals"])
        self.assertFalse(wf.load(self.root)["generation_calls"])


class ReferenceSourceUiTests(unittest.TestCase):
    def render(self, expression, refs):
        source = STATIC.read_text(encoding="utf-8")
        # Pure renderers live before selectedReferenceCards, no browser or network.
        self.assertIn("function referenceDeckSourceCard", source)
        start, end = source.index("function sourceNoteField"), source.index("function selectedReferenceCards")
        self.assertGreaterEqual(start, 0)
        script = """
        const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
        const sourceFileIcon=()=>'<span>PPTX</span>',uiIcon=()=>'',S={reference_decks:REFS};
        """ .replace("REFS", json.dumps(refs, ensure_ascii=False))
        return subprocess.run([shutil.which("node") or "node", "-e",
                               script + source[start:end] + f"\nprocess.stdout.write({expression});"],
                              check=True, capture_output=True, text=True, encoding="utf-8").stdout

    def test_absent_optional_references_render_nothing(self):
        self.assertEqual(self.render("referenceDeckPanel('stage2')", []), "")
        self.assertEqual(self.render("referenceDeckPanel('samples')", []), "")

    def test_source_card_and_stage_panels_keep_notes_and_reference_labels(self):
        refs = [{"id": "teacher", "original_name": "老师.pptx", "status": "verified",
                 "page_count": 10, "use": "对齐内容", "note": "<不要复制评注框>",
                 "preview_url": "/preview", "download_url": "/original", "page_bindings": {}}]
        card = self.render("referenceDeckSourceCard(S.reference_decks[0])", refs)
        panel = self.render("referenceDeckPanel('samples')", refs)
        self.assertIn("老师参考", card)
        self.assertIn("&lt;不要复制评注框&gt;", card)
        self.assertIn("reference-deck-preview", panel)
        self.assertIn("10 页", panel)
        self.assertIn("不是当前项目的实际样张", panel)
        self.assertNotIn('data-action="confirm"', panel)
        self.assertNotIn('data-action="adopt"', panel)

    def test_page_bindings_are_explicit_and_not_inferred_from_equal_page_numbers(self):
        refs = [{"id": "teacher", "page_count": 10, "page_bindings": {"P03": [4, 5]},
                 "preview_url": "/preview", "status": "verified"}]
        self.assertEqual(self.render("referenceDeckPanel('stage2','P01')", refs), "")
        self.assertIn("源第 4、5 页", self.render("referenceDeckPanel('stage2','P03')", refs))

    def test_stage1_stage2_and_locked_samples_have_shared_readonly_reference_entry(self):
        text = STATIC.read_text(encoding="utf-8")
        self.assertIn("(S.reference_decks||[]).map(referenceDeckSourceCard)", text)
        self.assertIn("renderStoryboardPage(pg,S,materialChoices.get(pg.page_id))", text)
        self.assertIn("renderPageStudio(S,", text)
        self.assertIn("referenceDeckPanel(v)", text)
        self.assertIn("reference-deck-preview", text)


if __name__ == "__main__":
    unittest.main()
