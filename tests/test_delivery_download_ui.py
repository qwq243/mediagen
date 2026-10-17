import json
from pathlib import Path
import shutil
import subprocess
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/static/ppt-workbench/app.js"


class DeliveryDownloadUiTests(unittest.TestCase):
    def render(self, exports):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index("function deliveryDownloads(")
        end = source.index("\nfunction deliveryView(", start)
        harness = ("const S=" + json.dumps({"exports": exports}) + ";"
                   "const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('\"','&quot;');")
        result = subprocess.run([shutil.which("node") or "node", "-e",
                                 harness + source[start:end] + "console.log(deliveryDownloads());"],
                                capture_output=True, text=True, encoding="utf-8", check=True)
        return result.stdout

    def test_no_delivery_has_no_fake_link(self):
        self.assertEqual(self.render([]).strip(), "")

    def test_actual_registered_download_renders(self):
        result = self.render([{"downloads": [{"label": "完整PPTX", "download_url": "/api/bundles/delivery-pptx-123"}]}])
        self.assertIn('href="/api/bundles/delivery-pptx-123"', result)
        self.assertIn("完整PPTX", result)

    def test_rejects_external_and_path_traversal_urls(self):
        self.assertEqual(self.render([{"downloads": [
            {"label": "bad", "download_url": "https://untrusted.test"},
            {"label": "bad", "download_url": "/api/bundles/../secrets"}
        ]}]).strip(), "")

    def test_label_is_escaped(self):
        result = self.render([{"downloads": [{"label": "<img>", "download_url": "/api/bundles/delivery-123"}]}])
        self.assertIn("&lt;img>", result)
        self.assertNotIn("<img>", result)


if __name__ == "__main__":
    unittest.main()
