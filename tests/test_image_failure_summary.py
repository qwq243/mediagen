import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ppt_workflow as wf


class ImageFailureSummaryTests(unittest.TestCase):
    def test_timeout_returns_only_safe_category(self):
        self.assertEqual(wf.image_failure_summary("TimeoutError: timed out token=PRIVATE"),
                         {"category": "timeout"})

    def test_http_status_never_echoes_body(self):
        self.assertEqual(wf.image_failure_summary("HTTP 503 https://secret?key=PRIVATE"),
                         {"category": "upstream_http", "http_status": 503})

    def test_unknown_error_is_not_persisted(self):
        self.assertEqual(wf.image_failure_summary("password=PRIVATE"),
                         {"category": "unclassified"})

    def test_curl_timeout(self):
        self.assertEqual(wf.image_failure_summary("curl: (28) Operation timed out"),
                         {"category": "timeout"})


if __name__ == "__main__":
    unittest.main()
