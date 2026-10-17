"""Offline coding/navigation/annotation contracts; not real design or model acceptance."""
import copy
import json
import sys
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_ppt_v3 as fixtures
import ppt_assets as assets
import ppt_coding as coding
import ppt_progress as progress
import ppt_annotation_io as ann
import ppt_workflow as wf
import ppt_studio as studio


class CodingTests(unittest.TestCase):
    setUp, tearDown = fixtures.V3Tests.setUp, fixtures.V3Tests.tearDown
    manifest, scan, client, post, basics = fixtures.V3Tests.manifest, fixtures.V3Tests.scan, fixtures.V3Tests.client, fixtures.V3Tests.post, fixtures.V3Tests.basics

    def package(self):
        self.scan()
        path = self.root / "coding.json"
        coding.export_package(self.library, path)
        return wf.read(path)

    def review_communication(self):
        return progress.review_communication(self.root, self.p, {
            "subject_hash": wf.subject(self.root, self.p, "stage1"),
            "status": "passed", "reviewer": "OFFLINE FIXTURE", "independent": True,
            "evidence": ["Synthetic navigation fixture"]})

    def test_ids_stable_order_and_work_metadata_real(self):
        first = self.scan()
        wf.write(self.source / "works.json", [{"work": "作品一", "pages": ["second.png", "first.png"],
            "style": "人工标记风格", "deckIntro": "真实整套说明"}])
        Image.new("RGB", (640, 360), "red").save(self.source / "pages/second.png")
        self.rows.insert(0, {"file": "second.png", "work": "作品一", "summary": "第二张"})
        self.manifest()
        assets.scan(self.source, self.library)
        current = assets.get(first["id"], library=self.library)
        self.assertEqual(current["order"], 2)
        self.assertEqual(current["page_code"], first["page_code"])
        self.assertEqual(current["deck_code"], first["deck_code"])
        self.assertEqual(current["style"], "人工标记风格")
        self.assertEqual(current["deck_metadata"]["deckIntro"], "真实整套说明")
        self.assertEqual(current["tags"], first["tags"])
        self.assertEqual(assets.search(first["page_code"], library=self.library)["total"], 1)
        self.assertGreater(assets.search("LY-SPLIT-2", library=self.library)["total"], 0)

    def test_roundtrip_partial_review_and_unknown_fonts(self):
        pack = self.package()
        row = pack["pages"][0]
        self.assertEqual(row["typography"], [])
        self.assertEqual(row["palette"]["swatches"], [])
        row.update(status="reviewed", reviewer="OFFLINE FIXTURE", evidence=["layout observed only"])
        pack["decks"][0].update(narrative=[{"code": "NT-ARG", "status": "suggested"}])
        r = coding.import_package(self.library, pack)
        self.assertFalse(r["applied"])
        self.assertEqual(coding.coverage(self.library)["reviewed"], 0)
        coding.import_package(self.library, pack, True)
        coding.export_package(self.library, self.root / "again.json")
        again = wf.read(self.root / "again.json")
        self.assertEqual(again["pages"][0]["reviewer"], "OFFLINE FIXTURE")
        self.assertEqual(again["decks"][0]["narrative"][0]["code"], "NT-ARG")
        self.assertEqual(coding.coverage(self.library)["missing_typography"], 1)
        before = assets.get(row["asset_id"], library=self.library)["version"]
        coding.import_package(self.library, again, True)
        after = assets.get(row["asset_id"], library=self.library)["version"]
        self.assertEqual(before, after)  # unchanged recoding roundtrip is idempotent

    def test_stale_metadata_and_image_reject_and_original_kept(self):
        pack = self.package()
        coding.import_package(self.library, pack, True)
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            coding.import_package(self.library, pack, True)
        r = assets.get(pack["pages"][0]["asset_id"], library=self.library)
        assets.pin(r, self.library)
        Image.new("RGB", (640, 360), "blue").save(self.image)
        assets.scan(self.source, self.library)
        current = assets.get(r["id"], library=self.library)
        self.assertTrue(current["coding"]["previous_coding_stale"])
        self.assertEqual(current["page_code"], r["page_code"])
        self.assertEqual(wf.file_sha(assets.path_for(r, self.library)), r["sha256"])
        with self.assertRaisesRegex(ValueError, "image changed"):
            coding.import_package(self.library, pack)

    def test_invalid_coding_rejected(self):
        base = self.package()
        for key, value in [("page_code", "PG-999999"), ("role", {"code": "LY-HERO"}),
                           ("layout", {"regions": [{"bbox": [0, 0, 2, 1]}]}),
                           ("typography", [{"code": "FT-SANS", "family": "Guessed font"}])]:
            pack = copy.deepcopy(base); pack["pages"][0][key] = value
            with self.assertRaises(ValueError):
                coding.import_package(self.library, pack)
        pack = copy.deepcopy(base); pack["definitions"] = [{"code": "PAL-000001-01", "name": "bad", "swatches": [{"hex": "blue"}]}]
        with self.assertRaises(ValueError):
            coding.import_package(self.library, pack)

    def test_definitions_versioned_pinned(self):
        pack = self.package()
        pack["definitions"] = [{"code": "CMP-000001-TOPBAR-01", "name": "测试顶栏",
            "type_code": "CP-TOPBAR", "bbox": [0, 0, 1, .12], "variable_fields": ["title", "page_number"]}]
        pack["pages"][0]["component_refs"] = ["CMP-000001-TOPBAR-01"]
        coding.import_package(self.library, pack, True)
        r = assets.get(pack["pages"][0]["asset_id"], library=self.library)
        cart = assets.choose(self.root, self.p, r["id"], r["version"], "style", self.library)
        self.assertEqual(cart["coding"]["definitions"]["CMP-000001-TOPBAR-01"]["name"], "测试顶栏")
        coding.export_package(self.library, self.root / "again.json")
        pack = wf.read(self.root / "again.json")
        pack["definitions"][0]["name"] = "新名称"
        coding.import_package(self.library, pack, True)
        self.assertEqual(self.p["resource_cart"][0]["coding"]["definitions"]["CMP-000001-TOPBAR-01"]["name"], "测试顶栏")

    def test_stage_lock_server_review_invalidation_and_revisit(self):
        state = self.client()
        self.assertFalse(state["progress"][1]["accessible"])
        self.assertEqual(self.post("/api/v3/draft", {"stage": "stage2", "comment": "bypass"}).status_code, 409)
        wf.confirm(self.root, self.p, "stage1", "OFFLINE FIXTURE")
        self.assertEqual(progress.state(self.root, self.p)[0]["status"], "waiting_agent")
        self.review_communication()
        self.assertTrue(progress.state(self.root, self.p)[1]["accessible"])
        self.basics()
        studio.create_draft(self.root, self.p, {"communication": {"audience": "新观众"}},
                            "修改观众", "stage1", True)
        states = progress.state(self.root, self.p)
        self.assertTrue(states[1]["accessible"])
        self.assertEqual(states[1]["status"], "revision_required")
        self.assertIn("pending revision", " ".join(wf.check(self.root, self.p, "render")["errors"]))
        self.p["communication"]["audience"] = "changed"
        self.assertFalse(progress.state(self.root, self.p)[0]["complete"])

    def test_failed_review_does_not_unlock(self):
        wf.confirm(self.root, self.p, "stage1", "OFFLINE FIXTURE")
        report = {"subject_hash": wf.subject(self.root, self.p, "stage1"), "status": "failed",
            "independent": True, "reviewer": "FIXTURE", "evidence": ["missing info"]}
        progress.review_communication(self.root, self.p, report)
        self.assertFalse(progress.state(self.root, self.p)[1]["accessible"])
        report["status"] = "passed"; report["findings"] = [{"severity": "major"}]
        with self.assertRaises(ValueError):
            progress.review_communication(self.root, self.p, report)

    def test_sample_preview_opens_before_whole_proposal_without_authorizing_production(self):
        self.client()
        wf.confirm(self.root, self.p, "stage1", "OFFLINE FIXTURE")
        self.review_communication()
        before = copy.deepcopy(self.p)
        item = next(x for x in progress.state(self.root, self.p) if x["id"] == "samples")
        self.assertTrue(item["accessible"])
        self.assertTrue(item["preview_only"])
        self.assertEqual(item["status"], "preview")
        self.assertFalse(item["complete"])
        overview = next(x for x in progress.state(self.root, self.p) if x["id"] == "deck")
        self.assertTrue(overview["accessible"])
        self.assertTrue(overview["preview_only"])
        self.assertFalse(overview["complete"])
        self.assertEqual(self.p, before)
        self.assertFalse(wf.check(self.root, self.p, "samples")["ok"])
        self.assertEqual(self.post("/api/v3/confirm", {"stage": "samples"}).status_code, 409)
        self.assertNotIn("samples", wf.load(self.root)["approvals"])
        studio.create_draft(self.root, self.p, {"design": {"icons": "outline"}}, "待对齐", "stage2")
        self.assertTrue(next(x for x in progress.state(self.root, self.p)
                             if x["id"] == "samples")["accessible"])
        self.assertFalse(wf.check(self.root, self.p, "render")["ok"])
        self.assertFalse(self.p["generation_calls"])

    def test_reference_annotation_pixel_handoff_and_version(self):
        r = self.scan(); before = wf.file_sha(self.image)
        shapes = [{"tool": "rect", "points": [[.1, .2], [.5, .6]]}]
        item = ann.reference(self.root, self.p, r["id"], r["version"], r["sha256"],
            shapes, "保留顶栏，不用原文字", self.library, True)
        data = wf.read(item["handoff_path"])
        self.assertEqual(data["geometry"][0]["pixel_points"], [[64, 72], [320, 216]])
        self.assertEqual(item["asset_version"], r["version"])
        self.assertTrue(Path(item["overlay_path"]).is_file())
        self.assertEqual(wf.file_sha(self.image), before)
        self.assertEqual(self.p["revision_requests"][-1]["details"]["annotation_id"], item["id"])
        self.assertEqual(self.p["generation_calls"], [])
        with self.assertRaises(ValueError):
            ann.reference(self.root, self.p, r["id"], r["version"], "stale", shapes, "", self.library)
        with self.assertRaises(ValueError):
            ann.validate([{"tool": "pen", "points": [[float("nan"), 0]]}])

    def test_api_annotation_favorites_and_complete_deck(self):
        r = self.scan(); self.client()
        self.assertEqual(self.post("/api/v3/sites/favorite", {"id": "aboutppt", "enabled": True}).status_code, 200)
        self.assertEqual(self.post("/api/v3/assets/favorite", {"id": r["id"], "enabled": True}).status_code, 200)
        self.assertEqual(wf.load(self.root)["resource_cart"], [])
        response = self.post("/api/v3/annotations", {"target_kind": "reference",
            "asset_id": r["id"], "asset_version": r["version"], "sha256": r["sha256"], "stage": "stage1",
            "shapes": [{"tool": "ellipse", "points": [[.1, .1], [.2, .2]]}], "comment": "形状", "submit": False})
        self.assertEqual(response.status_code, 200)
        aid = response.get_json()["id"]
        for mode in ("record", "overlay"):
            with self.web.get(f"/api/v3/annotations/{aid}/{mode}") as res:
                self.assertEqual(res.status_code, 200)
        deck = self.web.get("/api/v3/presentation?deck_code=" + r["deck_code"]).get_json()
        self.assertEqual(deck["pages"][0]["version"], r["version"])
        with self.web.get(deck["pages"][0]["url"]) as res:
            self.assertEqual(res.status_code, 200)
        self.assertEqual(self.web.get("/api/v3/site-icons/unknown").status_code, 404)
        self.assertIsNone(self.web.get("/api/v3/presentation").get_json()["pages"][0]["url"])

    def test_generation_only_consumes_adopted_reviewed_design_coding(self):
        item = {"id": "a-test", "usage": "structure", "page_code": "PG-000001", "coding": {
            "status": "suggested", "relations": [{"code": "IR-COMPARE", "status": "reviewed"}],
            "title": "DO NOT COPY SOURCE FACTS", "definitions": {
                "PAL-001": {"code": "PAL-001", "status": "reviewed", "swatches": [{"hex": "#123456"}]}}}}
        self.assertEqual(coding.prompt_constraints([item]), [])
        item["coding"]["status"] = "reviewed"
        text = json.dumps(coding.prompt_constraints([item]))
        self.assertIn("IR-COMPARE", text)
        self.assertNotIn("SOURCE FACTS", text)
        self.assertNotIn("#123456", text)  # structure-only never silently borrows style
        item["usage"] = "style"
        self.assertIn("#123456", json.dumps(coding.prompt_constraints([item])))
