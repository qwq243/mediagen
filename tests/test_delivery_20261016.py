"""Offline regression contracts for the authorized competition delivery."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import newapi_image as engine
import ppt_assets as assets
import ppt_fragments as fragments
import ppt_progress as progress
import ppt_workflow as wf
import test_ppt_v3 as fixtures
from PIL import Image
import ppt_regions as regions


class DeliveryTests(unittest.TestCase):
    setUp, tearDown = fixtures.V3Tests.setUp, fixtures.V3Tests.tearDown
    manifest, scan = fixtures.V3Tests.manifest, fixtures.V3Tests.scan

    def test_new_crop_is_favorited_without_approvals_or_cart(self):
        source = self.scan()
        record = fragments.crop(self.root, self.p, {
            "target_kind": "reference", "asset_id": source["id"],
            "asset_version": source["version"], "sha256": source["sha256"],
            "box": [0, 0, .5, .5], "title": "局部标题", "kind": "decoration",
            "tags": ["艺术字"]}, self.library)
        found = assets.search(filters={"favorite": True}, library=self.library)
        self.assertIn(record["id"], [x["id"] for x in found["items"]])
        self.assertTrue(record["favorite"])
        self.assertFalse(self.p["resource_cart"])
        self.assertFalse(self.p["approvals"])
        assets.favorite(record["id"], False, self.library)
        self.assertEqual(assets.search(filters={"favorite": True}, library=self.library)["total"], 0)

    def test_banana_drops_unsupported_quality_but_keeps_png_size(self):
        for model in ("nana-banana-2.1", "nano-banana-pro"):
            args = engine.build_parser().parse_args([
                "generate", "--model", model, "--prompt", "test", "--out", "unused.png",
                "--size", "2048x1152", "--quality", "high", "--output-format", "png"])
            payload = engine.build_payload(args, "test")
            self.assertNotIn("quality", payload)
            self.assertEqual(payload["output_format"], "png")
            self.assertEqual(payload["size"], "2048x1152")
            self.assertEqual(payload["model"], model)

    def test_non_banana_quality_is_unchanged(self):
        args = engine.build_parser().parse_args([
            "generate", "--model", "gpt-image-2", "--prompt", "test",
            "--out", "unused.png", "--quality", "high"])
        self.assertEqual(engine.build_payload(args, "test")["quality"], "high")

    def test_export_deliveries_unlocks_completed_delivery_stage(self):
        for pg in self.p["pages"]:
            pg["selected_output"] = {"path": str(self.image), "kind": "user_import"}
        self.p["deliveries"] = [{"pptx": {"path": "actual-export.pptx"}}]
        with patch.object(wf, "valid", return_value=True), \
                patch.object(wf, "subject", return_value="test-hash"):
            row = next(x for x in progress.state(self.root, self.p) if x["id"] == "delivery")
        self.assertTrue(row["complete"])

    def test_rgba_overlay_can_preserve_clean_generated_background(self):
        source = Image.new("RGB", (20, 20), "#abcdef")
        zone = {"box":[0,0,.5,.5], "mode":"image", "color":"#FFFFFF",
                "purpose":"Paste original transparent logo without an opaque rectangle",
                "preserve_background":True,
                "embedded_asset":{"id":"a-test","version":"v1","sha256":"test",
                                  "path":"unused.png","fit":"contain"}}
        actual = regions.render_regions(source, [zone])
        self.assertEqual(actual.getpixel((3,3)), (171,205,239,255))
        zone["preserve_background"] = False
        self.assertEqual(regions.render_regions(source,[zone]).getpixel((3,3)), (255,255,255,255))


if __name__ == "__main__":
    unittest.main()
