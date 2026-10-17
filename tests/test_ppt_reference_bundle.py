"""Offline contracts for linked reference bundles; no model or production writes."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_ppt_v3 as fixtures
import ppt_assets as assets
import ppt_coding as coding
import ppt_workflow as wf


class ReferenceBundleTests(unittest.TestCase):
    setUp, tearDown = fixtures.V3Tests.setUp, fixtures.V3Tests.tearDown
    manifest, scan, client = fixtures.V3Tests.manifest, fixtures.V3Tests.scan, fixtures.V3Tests.client

    def test_distinct_design_and_brand_families_preserve_identity_on_recapture(self):
        records = {}
        for kind, family in (("slide", "pages"), ("webpage", "webpages"), ("brand", "branding"),
                             ("icon", "components"), ("background", "materials")):
            r = assets.import_image(self.image, {"title": kind, "work": "分类测试", "kind": kind}, self.library)
            records[kind] = r
            self.assertEqual(assets.search_fields(r)["family"], [family])
            result = assets.search(filters={"family": family}, library=self.library)
            self.assertEqual([x["id"] for x in result["items"]], [r["id"]])
        original = records["webpage"]
        from PIL import Image
        Image.new("RGB", (80, 40), "red").save(self.image)
        replacement = assets.import_image(self.image, {
            "id": original["id"], "title": "清晰网页实拍", "work": "分类测试", "kind": "webpage",
        }, self.library)
        self.assertEqual(replacement["page_code"], original["page_code"])
        self.assertEqual(replacement["deck_code"], original["deck_code"])
        self.assertNotEqual(replacement["sha256"], original["sha256"])
        historical = assets.get(original["id"], original["version"], self.library)
        self.assertEqual(wf.file_sha(assets.path_for(historical, self.library)), original["sha256"])

    def test_transparent_brand_preview_has_white_matte_without_changing_original(self):
        from PIL import Image
        Image.new("RGBA", (80, 80), (255, 0, 0, 0)).save(self.image)
        r = assets.import_image(self.image, {"title": "透明标识", "kind": "brand"}, self.library)
        original_hash = r["sha256"]
        preview = assets.thumbnail(r, self.library)
        with Image.open(preview) as im:
            self.assertTrue(all(v >= 250 for v in im.getpixel((0, 0))))
        self.assertIn("alpha-white-v2", preview.name)
        self.assertEqual(wf.file_sha(assets.path_for(r, self.library)), original_hash)
        with Image.open(assets.path_for(r, self.library)) as im:
            self.assertEqual(im.getpixel((0, 0))[3], 0)

    def package(self):
        self.scan()
        resource = assets.import_image(self.image, {
            "title": "配套背景", "work": "作品一", "kind": "background",
        }, self.library)
        coding.export_package(self.library, self.root / "coding.json")
        p = wf.read(self.root / "coding.json")
        # import_image uses its own deck identity; bundle only same-deck assets.
        r = next(x for x in p["pages"] if x["asset_id"] != resource["id"])
        other = next(x for x in p["pages"] if x["asset_id"] == resource["id"])
        with assets.database(self.library) as db:
            raw = assets.get(other["asset_id"], library=self.library)
            raw["deck_identity_key"] = assets.get(r["asset_id"], library=self.library)["deck_identity_key"]
            coding.enrich(db, raw, raw["deck_identity_key"])
            assets._store(db, raw)
        coding.export_package(self.library, self.root / "coding.json")
        p = wf.read(self.root / "coding.json")
        pages = p["pages"]
        deck = next(d for d in p["decks"] if d["deck_code"] == pages[0]["deck_code"])
        deck["reference_bundle"] = {
            "schema_version": 1, "name": "同一套关联参考",
            "members": [{"asset_id": x["asset_id"], "page_code": x["page_code"],
                         "image_sha256": x["image_sha256"],
                         "role": "main" if x["asset_id"] == r["asset_id"] else "resource"}
                        for x in pages],
            "links": [{"source": r["asset_id"], "target": other["asset_id"],
                       "relation": "background", "evidence": "OFFLINE fixture"}],
        }
        return p, r["asset_id"], other["asset_id"]

    def test_na_requires_reason_and_cannot_hide_existing_font(self):
        p, _, _ = self.package()
        row = p["pages"][0]
        row["applicability"] = {"typography": {"state": "not_applicable", "reason": ""}}
        with self.assertRaisesRegex(ValueError, "applicability"):
            coding.import_package(self.library, p)
        row["applicability"]["typography"]["reason"] = "纯背景，不作为字体系样本"
        row["typography"] = [{"code": "FT-SANS"}]
        with self.assertRaisesRegex(ValueError, "not_applicable"):
            coding.import_package(self.library, p)

    def test_bundle_rejects_stale_hash_orphan_and_outside_member(self):
        base, _, _ = self.package()
        for mutation in ("hash", "orphan", "outside"):
            p = copy.deepcopy(base)
            b = next(d["reference_bundle"] for d in p["decks"] if d.get("reference_bundle"))
            if mutation == "hash":
                b["members"][0]["image_sha256"] = "0" * 64
            elif mutation == "orphan":
                b["links"] = []
            else:
                b["links"][0]["target"] = "not-in-bundle"
            with self.assertRaisesRegex(ValueError, "bundle"):
                coding.import_package(self.library, p)

    def test_links_are_bidirectional_and_resources_not_presented_as_pages(self):
        p, main, resource = self.package()
        coding.import_package(self.library, p, True)
        self.client()
        main_r = self.web.get("/api/v3/assets/" + main).get_json()
        resource_r = self.web.get("/api/v3/assets/" + resource).get_json()
        self.assertEqual(main_r["bundle_context"]["related"][0]["id"], resource)
        self.assertEqual(resource_r["bundle_context"]["related"][0]["id"], main)
        self.assertEqual(main_r["bundle_context"]["main_count"], 1)
        self.assertEqual(main_r["bundle_context"]["resource_count"], 1)
        self.assertTrue(main_r["bundle_context"]["related"][0]["version"])
        pages = self.web.get("/api/v3/presentation?deck_code=" + main_r["deck_code"]).get_json()["pages"]
        self.assertEqual([x["id"] for x in pages], [main])

    def test_na_does_not_count_as_missing_typography(self):
        p, _, _ = self.package()
        for row in p["pages"]:
            row["typography"] = []
            row["typography_refs"] = []
            row["applicability"] = {"typography": {
                "state": "not_applicable", "reason": "OFFLINE fixture has no text sample"}}
        coding.import_package(self.library, p, True)
        self.assertEqual(coding.coverage(self.library)["missing_typography"], 0)

    def test_changed_image_links_keep_original_snapshot_and_archive_is_not_adoption(self):
        p, main, resource = self.package()
        coding.import_package(self.library, p, True)
        original = assets.get(resource, library=self.library)
        assets.pin(original, self.library)
        with assets.database(self.library) as db:
            changed = copy.deepcopy(original)
            changed["sha256"] = "f" * 64
            changed["title"] = "已变更的源图，不能跟随"
            assets._store(db, changed)
        current = assets.get(resource, library=self.library)
        assets.set_archived(resource, True, current["version"], self.library)
        context = coding.bundle_context(assets.get(main, library=self.library), self.library)
        related = context["related"][0]
        self.assertEqual(related["version"], original["version"])
        self.assertNotEqual(related["version"], current["version"])
        self.assertTrue(related["archived"])
        self.assertEqual(wf.load(self.root)["resource_cart"], [])


if __name__ == "__main__":
    unittest.main()
