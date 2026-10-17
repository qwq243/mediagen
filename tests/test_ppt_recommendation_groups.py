"""Project shelf uses distinct works, not several pages from the same deck."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ppt_workbench as workbench


class RecommendationGroupTests(unittest.TestCase):
    def select(self, rows, records, removed=()):
        def lookup(rid, version=None, library=None):
            if rid not in records:
                raise ValueError("missing reference")
            return {"id": rid, "version": version or "current", **records[rid]}
        with patch.object(workbench.assets, "get", side_effect=lookup):
            return workbench.representative_recommendations(rows, set(removed), Path("fixture"))

    def test_same_deck_has_one_entry_even_for_different_usages(self):
        rows = [{"id": "hero", "version": "pinned", "usage": "style"},
                {"id": "cards", "usage": "layout"}, {"id": "other"}]
        result = self.select(rows, {"hero": {"deck_code": "DK-ONE"},
                                  "cards": {"deck_code": "DK-ONE"},
                                  "other": {"deck_code": "DK-TWO"}})
        self.assertEqual([r["id"] for r in result], ["hero", "other"])
        self.assertEqual(result[0]["version"], "pinned")
        self.assertEqual(len(rows), 3)  # presentation only, never delete stored choices

    def test_work_fallback_and_unknown_identity_do_not_collapse_unrelated_assets(self):
        rows = [{"id": x} for x in ("a", "b", "c", "d")]
        self.assertEqual([r["id"] for r in self.select(
            rows, {"a": {"work": "One"}, "b": {"work": "One"}, "c": {}, "d": {}})],
            ["a", "c", "d"])

    def test_hidden_or_missing_assets_do_not_consume_slots(self):
        rows = [{"id": x} for x in ("hidden", "missing", "visible")]
        result = self.select(rows, {"hidden": {"deck_code": "DK-ONE"},
                                  "visible": {"deck_code": "DK-ONE"}}, ["hidden"])
        self.assertEqual([r["id"] for r in result], ["visible"])

    def test_ceiling_six_not_a_target_and_input_order_is_priority(self):
        rows = [{"id": str(i)} for i in range(9)]
        records = {str(i): {"deck_code": f"DK-{i}"} for i in range(9)}
        self.assertEqual([r["id"] for r in self.select(rows, records)], list(map(str, range(6))))
        self.assertEqual(len(self.select(rows[:2], records)), 2)


if __name__ == "__main__":
    unittest.main()
