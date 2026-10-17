import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ppt_workflow as wf


class DeliveryRegistrationTests(unittest.TestCase):
    def test_registers_existing_delivery_with_hash_and_safe_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("real exported notes", encoding="utf-8")
            p = {"asset_exports": []}
            link = wf.register_delivery_download(p, path, "分页讲稿")
            self.assertEqual(link["sha256"], wf.file_sha(path))
            self.assertEqual(link["bytes"], path.stat().st_size)
            self.assertTrue(link["download_url"].startswith("/api/bundles/delivery-"))
            self.assertEqual(p["asset_exports"][0]["path"], str(path.resolve()))
            self.assertEqual(p["asset_exports"][0]["kind"], "delivery_file")

    def test_missing_file_is_not_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = {"asset_exports": []}
            with self.assertRaises(ValueError):
                wf.register_delivery_download(p, Path(tmp) / "missing.pdf", "PDF")
            self.assertEqual(p["asset_exports"], [])

    def test_refuses_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "program.exe"
            path.write_bytes(b"not a delivery")
            with self.assertRaises(ValueError):
                wf.register_delivery_download({"asset_exports": []}, path, "bad")


if __name__ == "__main__":
    unittest.main()
