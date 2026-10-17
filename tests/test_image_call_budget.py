import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


class BudgetTests(unittest.TestCase):
    def test_failed_attempt_still_consumes_budget_across_process_restarts(self):
        import image_call_budget as budget
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "budget.json"
            p.write_text(json.dumps({"max_calls": 2, "evidence": "explicit test consent", "attempts": []}))
            budget.reserve(p, "generations")
            budget.reserve(p, "edits")
            with self.assertRaises(ValueError):
                budget.reserve(p, "generations")
            self.assertEqual(len(json.loads(p.read_text())["attempts"]), 2)

    def test_missing_authorization_does_not_create_ledger(self):
        import image_call_budget as budget
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "missing.json"
            with self.assertRaises((ValueError, FileNotFoundError)):
                budget.reserve(p, "generations")
            self.assertFalse(p.exists())

    def test_json_budget_disables_route_fallback_and_transport_retries(self):
        import newapi_image as engine
        with patch("image_call_budget.reserve_from_environment", return_value=True), \
             patch.object(engine, "select_transport", return_value="curl"), \
             patch.object(engine, "proxy_routes_for", return_value=[None, "http://unused.invalid"]), \
             patch.object(engine, "request_json_curl", side_effect=engine.TransportFailed("test timeout")) as request:
            with self.assertRaises(SystemExit):
                engine.request_with_transport("POST", "https://example.invalid/v1/images/generations", "test-not-a-key", retries=5)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[6], 1)

    def test_multipart_budget_disables_route_fallback_and_transport_retries(self):
        import newapi_image as engine
        with patch("image_call_budget.reserve_from_environment", return_value=True), \
             patch.object(engine, "select_transport", return_value="curl"), \
             patch.object(engine, "proxy_routes_for", return_value=[None, "http://unused.invalid"]), \
             patch.object(engine, "request_multipart_curl", return_value={"data":[]}) as request:
            engine.request_multipart_with_transport("POST", "https://example.invalid/v1/images/edits", "test-not-a-key", b"", "multipart/form-data", retries=5)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[7], 1)

    def test_get_requests_do_not_consume_image_budget(self):
        import image_call_budget as budget
        with patch.dict("os.environ", {"MEDIAGEN_IMAGE_BUDGET_FILE":"missing-must-not-be-opened.json"}):
            self.assertFalse(budget.reserve_from_environment("GET", "https://example.invalid/v1/models"))


if __name__ == "__main__":
    unittest.main()
