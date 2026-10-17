"""Offline layout/component contracts. No image-model requests or synthetic approval of real work."""
import copy
import sys
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_ppt_v3 as fixtures
import ppt_assets as assets
import ppt_coding as coding
import ppt_components as components
import ppt_regions as regions
import ppt_studio as studio
import ppt_workflow as wf


class ComponentRegionTests(unittest.TestCase):
    setUp, tearDown = fixtures.V3Tests.setUp, fixtures.V3Tests.tearDown
    manifest, scan, client, post = fixtures.V3Tests.manifest, fixtures.V3Tests.scan, fixtures.V3Tests.client, fixtures.V3Tests.post

    def selection(self, strategy="variant"):
        r = self.scan()
        return {"asset_id": r["id"], "asset_version": r["version"], "sha256": r["sha256"],
                "slot": "header", "scope": "content", "strategy": strategy,
                "box": [0, 0, 1, .15] if strategy == "composite" else None}

    def test_examples_are_real_versioned_and_same_for_agent_and_http(self):
        r = self.scan()
        result = coding.examples(self.library, "layout", "LY-SPLIT-2")
        ex = result["items"][0]["examples"][0]
        self.assertEqual((ex["id"], ex["version"], ex["sha256"]), (r["id"], r["version"], r["sha256"]))
        self.assertEqual(ex["status"], "suggested")
        self.assertTrue(Path(ex["path"]).exists())
        self.client()
        self.assertEqual(self.web.get("/api/v3/coding/examples?group=layout&code=LY-SPLIT-2").get_json(), result)
        self.assertFalse(coding.examples(self.library, "font_style", "FT-BRUSH")["items"][0]["examples"])
        with self.assertRaises(ValueError):
            coding.examples(self.library, "foo")

    def test_component_selection_collects_but_does_not_approve_or_generate(self):
        body = self.selection()
        self.client()
        response = self.post("/api/v3/components/request", body)
        self.assertEqual(response.status_code, 200, response.get_json())
        p = wf.load(self.root)
        self.assertTrue(p["resource_cart"])
        self.assertFalse(p["component_pack"]["enabled"])
        self.assertFalse(p["asset_selection"])
        self.assertFalse(p["generation_calls"])
        self.assertTrue(any("pending revision" in s for s in wf.check(self.root, p, "samples")["errors"]))
        with self.assertRaises(ValueError):
            studio.resolve(self.root, p, response.get_json()["id"], "不能空处理")

    def test_variant_requires_new_parent_linked_asset(self):
        b = self.selection()
        req = components.request_selection(self.root, self.p, b, self.library)
        with self.assertRaisesRegex(ValueError, "变体尚未"):
            components.apply_selection(self.root, self.p, req["id"], "对齐", model_allowed=True, library=self.library)
        wrong = assets.import_image(self.image, {"title": "未关联父素材", "kind": "header"}, self.library)
        with self.assertRaisesRegex(ValueError, "父版本"):
            components.apply_selection(self.root, self.p, req["id"], "对齐",
                wrong["id"], wrong["version"], True, library=self.library)
        im = self.source / "variant.png"
        Image.new("RGB", (640, 90), "#998833").save(im)
        variant = assets.import_image(im, {"title": "新风格导航", "kind": "header",
            "parent": {"id": b["asset_id"], "version": b["asset_version"]}}, self.library)
        result = components.apply_selection(self.root, self.p, req["id"], "OFFLINE FIXTURE aligned",
            variant["id"], variant["version"], True, library=self.library)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(wf.component_values(self.p, self.p["pages"][1])["items"][0]["asset_id"], variant["id"])
        self.assertFalse(wf.component_values(self.p, self.p["pages"][0])["items"])
        self.assertFalse(self.p["generation_calls"])

    def test_components_included_despite_page_asset_filter_and_current_page_slots(self):
        req = components.request_selection(self.root, self.p, self.selection("reference"), self.library)
        components.apply_selection(self.root, self.p, req["id"], "已对齐", model_allowed=True, library=self.library)
        pg = self.p["pages"][1]; pg["asset_ids"] = ["other"]
        self.assertTrue(wf.uses_asset(self.p, pg, self.p["asset_selection"][0]))
        self.assertIn(self.p["asset_selection"][0]["id"], wf.prompts(self.root, self.p)["P02"])
        self.assertNotIn(self.p["asset_selection"][0]["title"], wf.prompts(self.root, self.p)["P02"])
        self.assertEqual(wf.component_values(self.p, pg)["page_number"], 2)
        self.p["pages"] = [pg, self.p["pages"][0], self.p["pages"][2]]
        self.assertEqual(wf.component_values(self.p, pg)["page_number"], 1)

    def test_composite_keeps_upload_off_and_exact_canvas(self):
        req = components.request_selection(self.root, self.p, self.selection("composite"), self.library)
        components.apply_selection(self.root, self.p, req["id"], "位置已确认", library=self.library)
        self.assertFalse(self.p["asset_selection"][0]["model_allowed"])
        out = self.root / "base.png"
        Image.new("RGB", (640, 360), "white").save(out)
        regions.finish_layout(self.root, self.p, self.p["pages"][1], out)
        with Image.open(out) as im:
            self.assertEqual(im.size, (640, 360))
            self.assertEqual(im.getpixel((10, 300)), (255, 255, 255, 255))
            self.assertNotEqual(im.getpixel((320, 20)), (255, 255, 255, 255))
        self.p["component_pack"]["items"][0]["sha256"] = "wrong"
        self.assertTrue(any("组件" in s for s in wf.check(self.root, self.p)["errors"]))

    def test_invalid_component_does_not_enter_cart(self):
        body = self.selection()
        for change in ({"scope": "anything"}, {"slot": "x"}, {"sha256": "stale"}):
            with self.assertRaises(ValueError):
                components.request_selection(self.root, self.p, {**body, **change}, self.library)
        self.assertFalse(self.p["resource_cart"])

    def test_blank_zone_is_draft_then_invalidates_content_and_only_affected_page(self):
        old = {x["page_id"]: wf.page_design_hash(self.root, self.p, x) for x in self.p["pages"]}
        content = wf.subject(self.root, self.p, "content")
        req = regions.request_region(self.root, self.p, {"page_id": "P02", "mode": "solid",
            "box": [.25, .25, .5, .5], "color": "#CCAA88", "purpose": "留给真实图表"})
        self.assertFalse(self.p["pages"][1].get("reserved_regions"))
        studio.resolve(self.root, self.p, req["id"], "已核对文字移出留空区")
        self.assertNotEqual(content, wf.subject(self.root, self.p, "content"))
        self.assertNotEqual(old["P02"], wf.page_design_hash(self.root, self.p, self.p["pages"][1]))
        self.assertEqual(old["P03"], wf.page_design_hash(self.root, self.p, self.p["pages"][2]))
        self.assertIn("留给真实图表", wf.prompts(self.root, self.p)["P02"])

    def test_masks_pixel_boundary_and_exact_version_original(self):
        c = studio.add_candidate(self.root, self.p, "P01", self.image)
        original_hash = wf.file_sha(self.image)
        req = regions.request_region(self.root, self.p, {"page_id": "P01", "candidate_id": c["id"],
            "sha256": c["sha256"], "mode": "edit_mask", "box": [.1, .2, .5, .5], "purpose": "修改装饰"})
        d = req["details"]
        with Image.open(d["mask"]["path"]) as mask:
            self.assertEqual(mask.size, (640, 360))
            self.assertEqual(mask.mode, "RGBA")
            self.assertEqual(mask.getpixel((64, 72))[3], 0)
            self.assertEqual(mask.getpixel((383, 251))[3], 0)
            self.assertEqual(mask.getpixel((384, 252))[3], 255)
        self.assertEqual(wf.file_sha(d["original"]["path"]), original_hash)
        self.assertFalse(req["patch"])
        self.assertEqual(d["model_capability"], "not_verified")
        with self.assertRaises(ValueError):
            studio.resolve(self.root, self.p, req["id"], "不能自动空确认")
        self.client()
        with self.web.get(f"/api/v3/regions/{d['id']}/mask") as response:
            self.assertEqual(response.status_code, 200)

    def test_region_bounds_stale_evidence_and_missing_image_rejected(self):
        body = {"page_id": "P01", "mode": "solid", "box": [0, 0, .2, .3], "purpose": "局部留空"}
        for change in ({"box": [1, 0, .5, 1]}, {"box": [0, 0, float("nan"), 1]}, {"mode": "bad"}, {"mode": "edit_mask"}):
            with self.assertRaises(ValueError):
                regions.request_region(self.root, self.p, {**body, **change})
        c = studio.add_candidate(self.root, self.p, "P01", self.image, metadata={"contains_evidence": True})
        for sha in ("stale", c["sha256"]):
            with self.assertRaises(ValueError):
                regions.request_region(self.root, self.p, {**body, "mode": "edit_mask", "candidate_id": c["id"], "sha256": sha})

    def test_transparent_and_solid_are_exact_and_original_unmodified(self):
        original = Image.new("RGBA", (640, 360), (70, 90, 110, 255))
        zones = [{"box": [.1, .2, .5, .5], "mode": "transparent", "purpose": "logo"}]
        result = regions.render_regions(original, zones)
        self.assertEqual(result.getpixel((64, 72))[3], 0)
        self.assertEqual(result.getpixel((63, 72)), original.getpixel((63, 72)))
        result = regions.render_regions(original, [dict(zones[0], mode="solid", color="#123456")])
        self.assertEqual(result.getpixel((64, 72)), (18, 52, 86, 255))
        self.assertEqual(original.getpixel((64, 72)), (70, 90, 110, 255))

    def test_materialized_base_is_new_candidate_no_approval(self):
        c = studio.add_candidate(self.root, self.p, "P01", self.image)
        self.p["pages"][0]["reserved_regions"] = [{"box": [.2, .2, .4, .4], "mode": "transparent", "purpose": "后贴品牌"}]
        self.p["production_route"] = "external"
        result = regions.materialize(self.root, self.p, "P01", c["id"])
        self.assertNotEqual(c["id"], result["id"])
        self.assertEqual(result["kind"], "agent_composite")
        self.assertFalse(self.p["pages"][0].get("selected_output"))
        self.assertFalse(self.p["generation_calls"])
        with Image.open(result["path"]) as im:
            self.assertEqual(im.getpixel((200, 180))[3], 0)


if __name__ == "__main__":
    unittest.main()
