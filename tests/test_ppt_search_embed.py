"""Search precision and exact source-pixel insertion; no paid model requests."""
import copy
import sys
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_ppt_v3 as fixtures
import ppt_assets as assets
import ppt_regions as regions
import ppt_studio as studio
import ppt_workflow as wf


class SearchEmbedTests(unittest.TestCase):
    setUp, tearDown = fixtures.V3Tests.setUp, fixtures.V3Tests.tearDown
    manifest, scan, client, post = fixtures.V3Tests.manifest, fixtures.V3Tests.scan, fixtures.V3Tests.client, fixtures.V3Tests.post

    def test_search_uses_meaningful_fields_not_internal_json_keys(self):
        r = self.scan()
        for q in ("source_file", "suggested", "schema_version", r["sha256"]):
            self.assertEqual(assets.search(q, library=self.library)["total"], 0, q)
        self.assertEqual(assets.search("痛点 双栏", library=self.library)["total"], 1)
        self.assertEqual(assets.search("痛点 不存在", library=self.library)["total"], 0)
        for q in (r["page_code"], "layout:LY-SPLIT-2", "relation:IR-COMPARE", "tag:人工标签"):
            hit = assets.search(q, library=self.library)
            self.assertEqual(hit["total"], 1, q)
            self.assertTrue(hit["items"][0]["search_matches"])
        self.assertEqual(assets.search("layout:LY-SPLIT", library=self.library)["total"], 0)
        with self.assertRaises(ValueError):
            assets.search("secret:no", library=self.library)

    def test_categories_and_exact_facets_shared_with_http(self):
        self.scan()
        assets.import_image(self.image, {"title": "品牌A", "kind": "brand", "tags": ["青绿"]}, self.library)
        assets.import_image(self.image, {"title": "顶栏C", "kind": "header"}, self.library)
        assets.import_image(self.image, {"title": "插图B", "kind": "illustration"}, self.library)
        result = assets.search(filters={"family": "components"}, library=self.library)
        self.assertEqual([x["title"] for x in result["items"]], ["顶栏C"])
        # Brand marks have their own family, separate from reusable design components.
        branding = assets.search(filters={"family": "branding"}, library=self.library)
        self.assertEqual([x["title"] for x in branding["items"]], ["品牌A"])
        self.assertEqual(assets.search(filters={"layout": "LY-SPLIT-2"}, library=self.library)["total"], 1)
        self.assertEqual(assets.search(filters={"coding_status": "reviewed"}, library=self.library)["total"], 0)
        self.client()
        response = self.web.get("/api/v3/assets?family=components")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["items"], result["items"])
        self.assertEqual(self.web.get("/api/v3/assets?family=branding").get_json()["items"],
                         branding["items"])
        with self.assertRaises(ValueError):
            assets.search(filters={"unrecognized": "x"}, library=self.library)

    def test_search_continuation_has_no_duplicate_or_missing_items(self):
        for i in range(7):
            assets.import_image(self.image, {"id": f"ref-{i}", "title": f"参考{i}", "kind": "slide"}, self.library)
        first = assets.search(limit=3, library=self.library)
        second = assets.search(offset=first["next_offset"], limit=3, library=self.library)
        third = assets.search(offset=second["next_offset"], limit=3, library=self.library)
        self.assertEqual(len({x["id"] for r in (first, second, third) for x in r["items"]}), 7)
        self.assertFalse(third["has_more"])
        self.assertIsNone(third["next_offset"])

    def image_request(self):
        f = self.source / "proof.png"
        Image.new("RGB", (100, 50), "#cf3210").save(f)
        r = assets.import_image(f, {"title": "原始截图", "kind": "illustration", "role": "evidence"}, self.library)
        return r, {"page_id": "P02", "mode": "image", "box": [.25, .25, .5, .5],
                   "purpose": "嵌入原始截图", "asset_id": r["id"], "asset_version": r["version"],
                   "asset_sha256": r["sha256"], "fit": "contain", "color": "#ffffff"}

    def test_image_insert_is_pinned_draft_then_exact_composite(self):
        r, body = self.image_request()
        request = regions.request_region(self.root, self.p, body, self.library)
        embedded = request["details"]["region"]["embedded_asset"]
        self.assertEqual(embedded["version"], r["version"])
        self.assertFalse(self.p["pages"][1].get("reserved_regions"))
        self.assertFalse(self.p["generation_calls"])
        studio.resolve(self.root, self.p, request["id"], "截图保持比例放于右侧；所有文字移出该区域")
        # Project bytes survive replacement/removal of the original library file.
        Path(r["source_path"]).unlink()
        base = self.root / "base.png"
        Image.new("RGB", (640, 360), "#112233").save(base)
        regions.finish_layout(self.root, self.p, self.p["pages"][1], base)
        with Image.open(base) as im:
            self.assertEqual(im.getpixel((320, 180))[:3], (207, 50, 16))
            self.assertEqual(im.getpixel((160, 90))[:3], (255, 255, 255))
            self.assertEqual(im.getpixel((159, 90))[:3], (17, 34, 51))
        prompt = wf.prompts(self.root, self.p)["P02"]
        self.assertNotIn(embedded["path"], prompt)
        self.assertNotIn(r["id"], prompt)
        Path(embedded["path"]).write_bytes(b"tampered")
        self.assertTrue(any("嵌入" in x for x in wf.check(self.root, self.p)["errors"]))

    def test_stale_or_cropped_evidence_rejected_before_creating_request(self):
        r, body = self.image_request()
        for patch in ({"asset_sha256": "stale"}, {"fit": "stretch"}, {"fit": "cover"}):
            with self.assertRaises(ValueError):
                regions.request_region(self.root, self.p, {**body, **patch}, self.library)
        self.assertFalse(self.p["revision_requests"])

    def test_image_region_http_and_bundle_include_selected_image_only(self):
        r, body = self.image_request()
        self.client()
        res = self.post("/api/v3/regions", body)
        self.assertEqual(res.status_code, 200, res.get_json())
        p = wf.load(self.root)
        studio.resolve(self.root, p, res.get_json()["id"], "已明确精确坐标")
        # Explicit page selection can export its pinned embedded assets, even before a base exists.
        bundle = studio.export_bundle(self.root, p, [], ["P02"])
        manifest = wf.read(Path(bundle["folder"]) / "manifest.json")
        self.assertEqual(len(manifest["assets"]), 1)
        self.assertEqual(manifest["assets"][0]["id"], r["id"])
        self.assertTrue((Path(bundle["folder"]) / manifest["assets"][0]["file"]).is_file())


if __name__ == "__main__":
    unittest.main()
