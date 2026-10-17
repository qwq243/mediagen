"""Page-count intent is collected early; a storyboard must satisfy it later."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ppt_studio as studio
import ppt_workflow as wf


class PageCountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = wf.upgrade({"test_fixture": True, "pages": [
            {"page_id": "P01", "page_role": "cover", "page_text": "封面"},
            {"page_id": "P02", "page_role": "closing", "page_text": "收束"}]})
        self.p["communication"].update(audience="评委", communication_intent="说明方法")
        for pg in self.p["pages"]:
            pg["logic"].update(purpose="说明", key_message_or_question="结论",
                               information_relationship="并列", visual_expression="标题")
        wf.save(self.root, self.p)

    def tearDown(self):
        self.tmp.cleanup()

    def test_recommend_mode_does_not_infer_a_count_from_existing_pages(self):
        self.assertEqual(self.p["communication"]["page_count"],
                         {"mode": "recommend", "count": None, "min": None, "max": None})
        self.assertTrue(wf.check(self.root, self.p)["ok"])

    def test_exact_count_can_be_confirmed_before_storyboarding_but_blocks_mismatched_production(self):
        self.p["communication"]["page_count"] = {
            "mode": "exact", "count": 6, "min": None, "max": None}
        wf.confirm(self.root, self.p, "stage1", "OFFLINE fixture only")
        self.assertTrue(wf.valid(self.p["approvals"]["stage1"], wf.subject(self.root, self.p, "stage1")))
        with self.assertRaisesRegex(ValueError, "page count"):
            wf.confirm(self.root, self.p, "stage2", "OFFLINE fixture only")
        self.assertTrue(any("page count" in e for e in wf.check(self.root, self.p, "render")["errors"]))
        self.p["communication"]["page_count"]["count"] = 2
        self.assertTrue(wf.check(self.root, self.p)["ok"])  # Includes cover and closing.

    def test_ranges_include_both_endpoints_and_reject_out_of_range_counts(self):
        c = self.p["communication"]
        c["page_count"] = {"mode": "range", "count": None, "min": 2, "max": 3}
        self.assertTrue(wf.check(self.root, self.p)["ok"])
        c["page_count"]["min"], c["page_count"]["max"] = 1, 2
        self.assertTrue(wf.check(self.root, self.p)["ok"])
        c["page_count"]["min"], c["page_count"]["max"] = 3, 4
        self.assertTrue(any("page count" in e for e in wf.check(self.root, self.p)["errors"]))

    def test_invalid_choices_cannot_be_saved_or_confirmed(self):
        cases = [None, "6页", {"mode": "unknown"}, {"mode": "exact", "count": True},
                 {"mode": "exact", "count": 0}, {"mode": "exact", "count": 2.5},
                 {"mode": "range", "min": 5, "max": 3},
                 {"mode": "range", "min": 3},
                 {"mode": "recommend", "count": 8},
                 {"mode": "exact", "count": 6, "min": 5}]
        for pref in cases:
            with self.subTest(pref=pref):
                self.p["communication"]["page_count"] = pref
                with self.assertRaisesRegex(ValueError, "page_count"):
                    studio.clean_patch({"communication": copy.deepcopy(self.p["communication"])})
                with self.assertRaisesRegex(ValueError, "page_count"):
                    wf.confirm(self.root, self.p, "stage1", "OFFLINE fixture only")

    def test_change_is_pending_until_agent_applies_it_and_invalidates_prior_confirmation(self):
        wf.confirm(self.root, self.p, "stage1", "OFFLINE fixture only")
        old = wf.subject(self.root, self.p, "stage1")
        request = studio.create_draft(self.root, self.p, {"communication": {
            **self.p["communication"],
            "page_count": {"mode": "range", "count": None, "min": 5, "max": 7}}},
            stage="stage1", submit=True)
        self.assertEqual(old, wf.subject(self.root, self.p, "stage1"))
        studio.resolve(self.root, self.p, request["id"], "采用页数范围，逐页方案待后续确认")
        self.assertNotEqual(old, wf.subject(self.root, self.p, "stage1"))
        self.assertFalse(wf.valid(self.p["approvals"]["stage1"], wf.subject(self.root, self.p, "stage1")))
        self.assertFalse(self.p["generation_calls"])

    def test_legacy_omission_does_not_rewrite_communication_or_old_receipt_hash(self):
        self.p["communication"].pop("page_count", None)
        communication = copy.deepcopy(self.p["communication"])
        expected = wf.sha({"contract": "communication-v3", "communication": {
            k: communication.get(k) for k in ("audience", "communication_intent",
                "audience_outcome", "core_message", "delivery_context", "artifact_afterlife",
                "content_divergence", "reading_mode", "duration_seconds")},
            "language": self.p["primary_language"], "canvas": self.p["generation_contract"]["size"],
            "reference_direction": self.p.get("reference_direction", "")})
        normalized = wf.upgrade(self.p)
        self.assertEqual(normalized["communication"], communication)
        self.assertEqual(wf.subject(self.root, normalized, "stage1"), expected)
        self.assertTrue(wf.check(self.root, normalized)["ok"])


if __name__ == "__main__":
    unittest.main()
