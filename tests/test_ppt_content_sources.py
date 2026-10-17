"""Current content provenance, separate from style shopping. No model requests."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ppt_content_sources as sources
import ppt_confirm_ui as ui
import ppt_studio as studio
import ppt_workflow as wf


class ContentSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        self.library = Path(self.tmp.name) / "library"
        (self.root / "inputs").mkdir(parents=True)
        self.original = self.root / "inputs/speech.docx"
        self.original.write_bytes(b"opaque user document fixture")
        self.extracted = self.root / "inputs/speech.md"
        self.extracted.write_text(
            "# 讲稿\n\n## para-001\n最重要的一句话。\n\n## para-003\n原稿中的待核实主张。\n",
            encoding="utf-8")
        self.ref = {
            "id": "speech-current", "role": "content", "title": "当前讲稿",
            "original_name": "复赛演讲稿(1).docx", "path": "inputs/speech.docx",
            "sha256": wf.file_sha(self.original), "use": "观点与演示顺序",
            "extraction": {"path": "inputs/speech.md", "sha256": wf.file_sha(self.extracted)}}
        self.p = wf.upgrade({"test_fixture": True, "project_name": "source-test",
                             "pages": [{"page_id": "P01", "page_text": "封面"}]})
        self.p["references"] = [
            self.ref, {"id": "style-site", "role": "style", "url": "https://example.org"},
            {"id": "old-speech", "role": "content", "superseded_by": "speech-current"}]
        self.p["notes_policy"]["source_reference_id"] = self.ref["id"]
        wf.save(self.root, self.p)

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_current_content_is_visible_and_hash_verified(self):
        rows = sources.summaries(self.root, self.p)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["original_name"], "复赛演讲稿(1).docx")
        self.assertEqual(rows[0]["status"], "verified")
        self.assertTrue(rows[0]["primary"])
        self.assertEqual(rows[0]["paragraph_count"], 2)
        self.assertNotIn("original_path", rows[0])
        self.assertEqual(sources.preview(self.root, self.p, "speech-current")["paragraphs"][1],
                         {"id": "para-003", "citation": "speech-current / para-003",
                          "text": "原稿中的待核实主张。"})

    def test_tampered_source_or_extraction_cannot_be_previewed(self):
        self.extracted.write_text("更换后的内容", encoding="utf-8")
        self.assertEqual(sources.summaries(self.root, self.p)[0]["extraction_status"], "changed")
        with self.assertRaises(ValueError):
            sources.preview(self.root, self.p, "speech-current")
        self.original.write_bytes(b"changed")
        self.assertEqual(sources.summaries(self.root, self.p)[0]["status"], "changed")
        with self.assertRaises(ValueError):
            sources.original(self.root, self.p, "speech-current")

    def test_paths_outside_workspace_and_unpinned_legacy_sources_are_not_served(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("not a project input", encoding="utf-8")
        self.p["references"][0].update(path=str(outside), sha256=wf.file_sha(outside))
        self.assertEqual(sources.summaries(self.root, self.p)[0]["status"], "outside_project")
        with self.assertRaises(ValueError):
            sources.original(self.root, self.p, "speech-current")
        self.p["references"][0] = {"id": "legacy", "role": "content", "path": "inputs/speech.docx"}
        self.assertEqual(sources.summaries(self.root, self.p)[0]["status"], "unpinned")

    def test_routes_are_read_only_and_do_not_expose_style_or_history(self):
        before = wf.file_sha(self.root / wf.PACK)
        web = ui.create_app(self.root, self.library).test_client()
        state = web.get("/api/v3/workbench").get_json()
        self.assertEqual(state["content_sources"][0]["id"], "speech-current")
        self.assertEqual(web.get("/api/v3/content-sources/speech-current/preview").status_code, 200)
        response = web.get("/api/v3/content-sources/speech-current/original")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.original.read_bytes())
        response.close()
        for ident in ("old-speech", "style-site", "missing"):
            self.assertEqual(web.get(f"/api/v3/content-sources/{ident}/preview").status_code, 409)
        self.assertEqual(before, wf.file_sha(self.root / wf.PACK))
        self.assertFalse(wf.load(self.root)["approvals"])
        self.assertFalse(wf.load(self.root)["generation_calls"])

    def test_core_message_and_afterlife_use_existing_revision_flow(self):
        communication = copy.deepcopy(self.p["communication"])
        communication.update(core_message="这是一句话主旨", artifact_afterlife="赛后独立阅读")
        request = studio.create_draft(self.root, self.p, {"communication": communication},
                                      stage="stage1", submit=True)
        self.assertNotEqual(self.p["communication"]["core_message"], communication["core_message"])
        studio.resolve(self.root, self.p, request["id"], "按用户意见更新第一轮，尚未确认")
        self.assertEqual(wf.load(self.root)["communication"]["artifact_afterlife"], "赛后独立阅读")
        self.assertFalse(self.p["approvals"])
        self.assertFalse(self.p["generation_calls"])


if __name__ == "__main__":
    unittest.main()
