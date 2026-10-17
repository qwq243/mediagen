"""Autosave is a recoverable draft, never a silent proposal or approval."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ppt_studio as studio
import ppt_workflow as wf
import ppt_confirm_ui as ui


class FormAutosaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = wf.upgrade({"test_fixture": True, "pages": [
            {"page_id": "P01", "page_text": "封面"}]})
        wf.save(self.root, self.p)
        self.original = copy.deepcopy(studio.proposal(self.p))

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, value="已修改", **kwargs):
        return studio.autosave_form(
            self.root, self.p, stage="stage1",
            patch={"communication": {**self.p["communication"], "content_divergence": value}},
            form_values={"content_divergence": value}, **kwargs)

    def test_upserts_one_draft_and_persists_empty_values_without_applying(self):
        first = self.save()
        second = self.save("", draft_id=first["id"], draft_version=1)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.p["revision_requests"]), 1)
        self.assertEqual(second["details"]["autosave_version"], 2)
        self.assertEqual(second["patch"]["communication"]["content_divergence"], "")
        self.assertEqual(wf.load(self.root)["revision_requests"][0]["details"]["form_values"],
                         {"content_divergence": ""})
        self.assertEqual(studio.proposal(self.p), self.original)
        self.assertFalse(self.p["approvals"])
        self.assertFalse(self.p["generation_calls"])

    def test_partial_numeric_input_is_recoverable_but_not_applicable(self):
        r = studio.autosave_form(self.root, self.p, "stage1",
            {"communication": {"page_count": {"mode": "range", "min": 6, "max": None}}},
            form_values={"page-count-mode": "range", "page-count-min": "6", "page-count-max": ""})
        self.assertTrue(r["details"]["validation_errors"])
        self.assertEqual(r["details"]["form_values"]["page-count-max"], "")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            studio.resolve(self.root, self.p, r["id"], "不能将半填表单作为生产内容")

    def test_stale_version_and_foreign_draft_cannot_overwrite(self):
        r = self.save()
        with self.assertRaisesRegex(ValueError, "draft version"):
            self.save("覆盖", draft_id=r["id"], draft_version=0)
        with self.assertRaisesRegex(ValueError, "draft"):
            self.save("覆盖", draft_id="rev-missing", draft_version=1)
        self.assertEqual(r["details"]["form_values"]["content_divergence"], "已修改")

    def test_changed_proposal_requires_alignment_instead_of_silent_rebase(self):
        r = self.save()
        self.p["communication"]["core_message"] = "Agent 更新后的主旨"
        with self.assertRaisesRegex(ValueError, "proposal changed"):
            self.save("旧表单", draft_id=r["id"], draft_version=1)

    def test_submit_freezes_snapshot_and_restore_original_clears_only_own_draft(self):
        r = self.save()
        studio.autosave_form(self.root, self.p, "stage1", {}, comment="",
                            draft_id=r["id"], draft_version=1, clear=True)
        self.assertEqual(r["status"], "discarded")
        r = self.save()
        submitted = self.save(draft_id=r["id"], draft_version=1, submit=True)
        self.assertEqual(submitted["status"], "submitted")
        with self.assertRaisesRegex(ValueError, "draft"):
            self.save(draft_id=r["id"], draft_version=2)

    def test_rejects_unknown_stage_fields_and_arbitrary_editable_data(self):
        with self.assertRaises(ValueError):
            studio.autosave_form(self.root, self.p, "delivery", {})
        with self.assertRaises(ValueError):
            studio.autosave_form(self.root, self.p, "stage1", {},
                                form_values={"unexpected": {"nested": "not a field"}})
        with self.assertRaises(ValueError):
            studio.autosave_form(self.root, self.p, "stage1", {"approvals": {"stage1": "fake"}})

    def test_http_roundtrip_is_csrf_and_revision_protected(self):
        web = ui.create_app(self.root, self.root / "library").test_client()
        state = web.get("/api/v3/workbench").get_json()
        self.assertTrue(state["job_id"])
        body = {"revision": state["revision"], "stage": "stage1",
                "patch": {"communication": {"content_divergence": ""}},
                "form_values": {"content_divergence": ""}}
        self.assertEqual(web.post("/api/v3/form-draft", json=body).status_code, 403)
        headers = {"X-Mediagen-CSRF": state["csrf"]}
        response = web.post("/api/v3/form-draft", json=body, headers=headers)
        self.assertEqual(response.status_code, 200)
        record = response.get_json()["record"]
        restored = web.get("/api/v3/workbench").get_json()
        self.assertEqual(restored["pending"][0]["id"], record["id"])
        self.assertEqual(restored["pending"][0]["details"]["form_values"]["content_divergence"], "")
        self.assertEqual(web.post("/api/v3/form-draft", json=body, headers=headers).status_code, 409)
        self.assertEqual(restored["proposal"], state["proposal"])
        self.assertFalse(wf.load(self.root)["generation_calls"])


if __name__ == "__main__":
    unittest.main()
