"""Offline contracts. Synthetic reviews are fixtures, not real visual acceptance."""
import copy
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ppt_workflow as wf
import ppt_assets as assets
import ppt_cart as cart
import ppt_studio as studio
import ppt_confirm_ui as ui


class V3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        self.library = Path(self.tmp.name) / "library"
        self.source = Path(self.tmp.name) / "source"
        (self.source / "pages").mkdir(parents=True)
        self.image = self.source / "pages/first.png"
        Image.new("RGBA", (640, 360), (50, 100, 120, 100)).save(self.image)
        self.rows = [{"id": 1, "file": "first.png", "work": "作品一", "pageType": "项目背景",
                      "summary": "痛点对比", "tags": ["人工标签", "对比"], "layout": "双栏",
                      "structure": {"page_role": "提出问题"}}]
        self.manifest()
        self.p = wf.upgrade({"test_fixture": True, "project_name": "offline-only",
                             "pages": [{"page_id": "P01", "page_role": "cover", "page_text": "标题"},
                                       {"page_id": "P02", "page_role": "content", "page_text": "机制说明"},
                                       {"page_id": "P03", "page_role": "content", "page_text": "验证"}]})
        self.p["communication"].update(audience="评委", communication_intent="解释机制",
                                       duration_seconds=90, reading_mode="balanced")
        self.p["generation_contract"]["size"] = "640x360"
        for pg in self.p["pages"]:
            pg["logic"].update(purpose="解释", key_message_or_question="关键结论",
                                information_relationship="对比", visual_expression="双栏",
                                duration_seconds=30)
            pg["speaker_notes"] = "这是讲稿的独立解释，不应直接写进图片。"
        wf.save(self.root, self.p)

    def tearDown(self):
        self.tmp.cleanup()

    def manifest(self):
        (self.source / "pages.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in self.rows), encoding="utf-8")

    def scan(self):
        assets.scan(self.source, self.library)
        return assets.search(library=self.library)["items"][0]

    def choose(self, usage="structure"):
        r = self.scan()
        return assets.choose(self.root, self.p, r["id"], r["version"], usage, self.library)

    def candidate(self, pid="P01"):
        return studio.add_candidate(self.root, self.p, pid, self.image)

    def reviewed(self, pid="P01"):
        c = self.candidate(pid)
        studio.audit_candidate(self.root, self.p, pid, c["id"], {
            "subject_hash": c["subject_hash"], "independent": True, "reviewer": "OFFLINE FIXTURE",
            "evidence": ["synthetic assertion; not actual visual review"], "status": "passed", "findings": []})
        return c

    def basics(self):
        wf.confirm(self.root, self.p, "stage1", "OFFLINE FIXTURE")
        wf.confirm(self.root, self.p, "stage2", "OFFLINE FIXTURE")
        for phase in ("content", "prompts"):
            wf.audit(self.root, self.p, {"phase": phase, "subject_hash": wf.subject(self.root, self.p, phase),
                "independent": True, "reviewer": "OFFLINE FIXTURE", "evidence": ["synthetic"], "status": "passed", "findings": []})

    def client(self):
        self.web = ui.create_app(self.root, self.library).test_client()
        s = self.web.get("/api/v3/workbench").get_json()
        self.headers = {"X-Mediagen-CSRF": s["csrf"]}
        return s

    def post(self, endpoint, body):
        state = self.web.get("/api/v3/workbench").get_json()
        return self.web.post(endpoint, json={"revision": state["revision"], **body}, headers=self.headers)

    def test_incremental_readonly_human_tags_and_single_page_discovery(self):
        before = wf.file_sha(self.source / "pages.jsonl")
        first = self.scan()
        self.assertIn("人工标签", first["tags"])
        self.assertEqual(first["structure"]["page_role"], "提出问题")
        self.assertEqual(first["structure_suggestions"]["status"], "suggested")
        Image.new("RGB", (640, 360), "green").save(self.source / "pages/second.png")
        result = assets.scan(self.source, self.library)
        self.assertEqual(result["indexed"], 1)
        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(wf.file_sha(self.source / "pages.jsonl"), before)
        self.assertEqual(len(assets.search("对比", library=self.library)["items"]), 1)

    def test_cart_collection_never_changes_production_or_approval(self):
        self.basics()
        before = wf.design_hash(self.root, self.p)
        self.choose()
        cart.add_link(self.root, self.p, "https://example.org/design", comment="只用结构")
        self.assertEqual(before, wf.design_hash(self.root, self.p))
        self.assertEqual(self.p["asset_selection"], [])
        self.assertTrue(wf.check(self.root, self.p, "samples")["ok"])

    def test_structure_corrections_survive_refresh_and_keep_author_tags(self):
        original = self.scan()
        updated = assets.annotate_structure(original["id"], {
            "author":"offline test","evidence":["fixture label"], "deck_narrative":"问题—方案—验证",
            "page_roles":["提出问题"],"relationships":["对比"],"status":"suggested"},self.library)
        self.assertNotEqual(updated["version"], original["version"])
        assets.scan(self.source,self.library)
        current=assets.get(original["id"],library=self.library)
        self.assertEqual(current["tags"], original["tags"])
        self.assertEqual(current["structure_suggestions"]["deck_narrative"], "问题—方案—验证")
        self.assertEqual(assets.search("问题—方案—验证",library=self.library)["total"],1)

    def test_pinned_version_survives_source_change(self):
        item = self.choose()
        Image.new("RGB", (640, 360), "red").save(self.image)
        self.assertEqual(assets.scan(self.source, self.library)["indexed"], 1)
        self.assertEqual(wf.file_sha(item["path"]), item["sha256"])
        current = assets.get(item["id"], library=self.library)
        self.assertNotEqual(item["version"], current["version"])

    def test_cart_submit_blocks_and_agent_apply_records_decisions(self):
        self.basics()
        item = self.choose("style")
        request = cart.submit(self.root, self.p, "stage2")
        self.assertFalse(wf.check(self.root, self.p, "samples")["ok"])
        result = cart.apply(self.root, self.p, request["id"], [
            {"id": item["id"], "adopt": True, "model_allowed": True, "reason": "只借配色与线条，忽略原文"}],
                           "采用视觉参考，文字和证据仍使用本项目内容")
        self.assertEqual(result["status"], "applied")
        self.assertEqual(len(self.p["asset_selection"]), 1)
        self.assertFalse(wf.valid(self.p["approvals"]["stage2"], wf.subject(self.root, self.p, "stage2")))
        self.assertTrue(wf.valid(self.p["approvals"]["stage1"], wf.subject(self.root, self.p, "stage1")))

    def test_structure_only_is_not_model_reference(self):
        item = self.choose()
        request = cart.submit(self.root, self.p)
        cart.apply(self.root, self.p, request["id"], [
            {"id": item["id"], "model_allowed": True, "reason": "只借问题与解法结构"}], "借鉴逻辑")
        self.assertFalse(self.p["asset_selection"][0]["model_allowed"])
        self.assertNotIn("人工标签", wf.prompts(self.root, self.p)["P01"])

    def test_changed_cart_and_unimported_link_cannot_silently_apply(self):
        item = cart.add_link(self.root, self.p, "https://example.org/template")
        req = cart.submit(self.root, self.p)
        with self.assertRaisesRegex(ValueError, "actual selected file"):
            cart.apply(self.root, self.p, req["id"], [{"id": item["id"], "usage": "style", "reason": "配色"}], "采用")
        cart.update(self.root, self.p, item["id"], {"comment": "换意见"})
        with self.assertRaisesRegex(ValueError, "cart changed"):
            cart.apply(self.root, self.p, req["id"], [], "对齐")

    def test_selections_export_only_not_library_or_links(self):
        item = self.choose()
        cart.add_link(self.root, self.p, "https://example.org/template")
        b = studio.export_bundle(self.root, self.p, [item["id"]], ["P01"])
        with zipfile.ZipFile(b["path"]) as z:
            self.assertEqual(len(z.namelist()), 3)
            manifest = json.loads(z.read("manifest.json"))
            self.assertEqual(len(manifest["assets"]), 1)
            self.assertEqual(manifest["pages"][0]["page_text"], "标题")
        with self.assertRaises(ValueError):
            studio.export_bundle(self.root, self.p, ["unknown"])

    def test_draft_is_not_current_and_restore_does_not_restore_budget(self):
        original = wf.design_hash(self.root, self.p)
        request = studio.create_draft(self.root, self.p, {"design": {"icons": "solid"}}, submit=True)
        self.assertEqual(original, wf.design_hash(self.root, self.p))
        result = studio.resolve(self.root, self.p, request["id"], "仅改图标，保留内容")
        self.assertEqual(result["impact"]["affected_pages"], ["P01", "P02", "P03"])
        old = studio.history(self.root)[-1]
        self.p["generation_calls"].append({"status": "started"})
        wf.save(self.root, self.p)
        request = studio.restore(self.root, self.p, old["id"], "恢复视觉")
        studio.resolve(self.root, self.p, request["id"], "保留计费记录")
        self.assertEqual(len(self.p["generation_calls"]), 1)

    def test_page_change_scope_and_notes_exclusion(self):
        before = {pg["page_id"]: wf.page_design_hash(self.root, self.p, pg) for pg in self.p["pages"]}
        patch_value = studio.proposal(self.p)
        patch_value["pages"][2]["page_text"] += "补充"
        r = studio.create_draft(self.root, self.p, {"pages": patch_value["pages"]})
        result = studio.resolve(self.root, self.p, r["id"], "只改第三页")
        self.assertEqual(result["impact"]["affected_pages"], ["P03"])
        self.p["pages"][0]["speaker_notes"] += "更多解释"
        self.assertEqual(wf.page_design_hash(self.root, self.p, self.p["pages"][0]), before["P01"])
        self.assertNotIn("更多解释", wf.prompts(self.root, self.p)["P01"])

    def test_components_track_title_number_and_order(self):
        self.p["component_pack"].update(enabled=True, chapters=["问题", "方案"],
                                        variants={"content": {"footer": "thin line"}})
        self.p["pages"][1]["chapter"] = "方案"
        v = wf.component_values(self.p, self.p["pages"][1])
        self.assertEqual(v["page_number"], 2)
        self.assertEqual(v["total_pages"], 3)
        self.assertEqual(v["progress"], 1)
        self.p["pages"].reverse()
        self.assertEqual(wf.component_values(self.p, self.p["pages"][0])["page_number"], 1)

    def test_text_free_base_requires_composition_route(self):
        self.p["design"]["text_in_image"] = False
        self.assertFalse(wf.check(self.root, self.p)["ok"])
        self.p["production_route"] = "agent_composite"
        self.assertTrue(wf.check(self.root, self.p)["ok"])
        self.assertNotIn("<visible_text>", wf.prompts(self.root,self.p)["P01"])
        self.assertIn("TEXT-FREE BASE", wf.prompts(self.root,self.p)["P01"])
        self.p["component_pack"]["enabled"] = True
        self.p["pages"][0]["title"] = "只应出现在人工合成层的标题"
        prompt = wf.prompts(self.root, self.p)["P01"]
        self.assertNotIn("只应出现在人工合成层的标题", prompt)
        self.assertNotIn('"page_number"', prompt)
        self.assertEqual(wf.component_values(self.p, self.p["pages"][0])["page_number"], 1)

    def test_candidate_adoption_is_audited_and_does_not_overwrite(self):
        c = self.candidate()
        with self.assertRaisesRegex(ValueError, "visual audit"):
            studio.adopt(self.root, self.p, "P01", c["id"], "fixture")
        reviewed = self.reviewed()
        studio.adopt(self.root, self.p, "P01", reviewed["id"], "fixture")
        self.assertEqual(len(self.p["pages"][0]["output_candidates"]), 2)
        self.assertTrue(Path(c["path"]).exists())
        self.assertTrue(wf.valid(self.p["audits"]["visual:P01"], wf.subject(self.root, self.p, "visual", "P01")))

    def test_stale_or_failed_candidate_cannot_adopt(self):
        c = self.reviewed()
        self.p["pages"][0]["page_text"] += "新"
        with self.assertRaisesRegex(ValueError, "older page"):
            studio.adopt(self.root, self.p, "P01", c["id"], "fixture")

    def test_wrong_ratio_and_false_provenance_rejected(self):
        wrong = self.root / "portrait.png"
        Image.new("RGB", (100, 200)).save(wrong)
        with self.assertRaisesRegex(ValueError, "aspect ratio"):
            studio.add_candidate(self.root, self.p, "P01", wrong)
        for kind in ("generated", "agent_composite"):
            with self.assertRaises(ValueError):
                studio.add_candidate(self.root, self.p, "P01", self.image, kind)

    def test_annotations_bind_version_original_remains_clean(self):
        c = self.candidate()
        original = wf.file_sha(c["path"])
        studio.annotate(self.root, self.p, "P01", original,
                        [{"tool": "ellipse", "points": [[.1,.1],[.3,.3]]}], "统一标题字体", c["id"])
        self.assertEqual(original, wf.file_sha(c["path"]))
        self.assertEqual(self.p["revision_requests"][-1]["kind"], "image")
        with self.assertRaisesRegex(ValueError, "another version"):
            studio.annotate(self.root, self.p, "P01", "wrong", [], candidate_id=c["id"])
        with self.assertRaisesRegex(ValueError, "normalized"):
            studio.annotate(self.root, self.p, "P01", original,
                            [{"tool": "rect", "points": [[2, 1]]}], candidate_id=c["id"])

    def test_agent_composite_provenance_and_transparency(self):
        item = self.choose("material")
        req = cart.submit(self.root, self.p)
        cart.apply(self.root, self.p, req["id"], [{"id":item["id"],"reason":"固定页眉"}], "采用原图合成")
        c = studio.compose(self.root, self.p, "P01", {"layers":[{"asset_id":item["id"],"box":[0,0,1,1]}]})
        self.assertEqual(c["kind"], "agent_composite")
        self.assertEqual(len(self.p["composition_records"]), 1)
        self.assertIsNone(self.p["pages"][0]["selected_output"])

    def test_edit_and_asset_jobs_have_no_implicit_paid_calls(self):
        c = self.candidate()
        self.basics()
        plan = studio.prepare_edit(self.root, self.p, "P01", "仅改标题颜色", c["id"])
        with patch.object(studio.subprocess, "run") as run:
            dry = studio.edit(self.root, self.p, plan["id"])
            self.assertFalse(dry["inference_performed"])
            with self.assertRaises(ValueError):
                studio.edit(self.root, self.p, plan["id"], True, True)
            asset = studio.asset_request({"kind": "header", "prompt": "clean header", "transparent": True}, self.library)
            self.assertFalse(studio.asset_render(asset["id"], library=self.library)["inference_performed"])
            with self.assertRaises(ValueError):
                studio.asset_render(asset["id"], True, True, self.library)
            run.assert_not_called()

    def test_mask_and_protected_evidence_edit_constraints(self):
        c = self.candidate()
        mask = self.root / "mask.png"
        Image.new("RGB", (640, 360), "white").save(mask)
        with self.assertRaisesRegex(ValueError, "RGBA"):
            studio.prepare_edit(self.root, self.p, "P01", "改文字", c["id"], mask)
        self.p["pages"][0]["materials"] = [{"reference_id":"screenshot"}]
        with self.assertRaisesRegex(ValueError, "flattened evidence"):
            studio.prepare_edit(self.root, self.p, "P01", "改文字", c["id"])

    def test_http_catalog_same_as_agent_and_cas(self):
        record = self.scan()
        state = self.client()
        result = self.web.get("/api/v3/assets?q=对比").get_json()
        self.assertEqual(result["items"][0]["id"], assets.search("对比", library=self.library)["items"][0]["id"])
        r = self.post("/api/v3/cart/choose", {"id": record["id"]})
        self.assertEqual(r.status_code, 200)
        stale = self.web.post("/api/v3/cart/link", json={"revision": state["revision"],"url":"https://example.org"}, headers=self.headers)
        self.assertEqual(stale.status_code, 409)
        with self.web.get("/") as response:
            self.assertEqual(response.status_code, 200)
        with self.web.get(result["items"][0]["preview_url"]) as response:
            self.assertEqual(response.status_code, 200)

    def test_upload_is_candidate_or_cart_not_approval(self):
        self.client()
        def upload(page=None):
            s = self.web.get("/api/v3/workbench").get_json()
            data={"revision":str(s["revision"]), "file":(io.BytesIO(self.image.read_bytes()), "custom.png")}
            if page: data["page_id"] = page
            return self.web.post("/api/v3/upload", data=data, headers=self.headers)
        self.assertEqual(upload().status_code, 200)
        self.assertEqual(upload("P01").status_code, 409)
        self.p = wf.load(self.root)
        self.basics()
        import ppt_progress as progress
        progress.review_communication(self.root, self.p, {
            "subject_hash": wf.subject(self.root, self.p, "stage1"), "status": "passed",
            "reviewer": "OFFLINE FIXTURE", "independent": True, "evidence": ["synthetic"]})
        before = copy.deepcopy(self.p["approvals"])
        self.assertEqual(upload("P01").status_code, 200)
        p = wf.load(self.root)
        self.assertEqual(len(p["resource_cart"]), 1)
        self.assertEqual(len(p["pages"][0]["output_candidates"]), 1)
        self.assertEqual(p["approvals"], before)
        self.assertEqual(p["generation_calls"], [])

    def test_public_search_failure_is_honest_and_links_safe(self):
        with patch.object(cart, "urlopen", side_effect=TimeoutError):
            r = cart.public_search("library")
        self.assertEqual(r["status"], "unavailable")
        self.assertEqual(r["items"], [])
        with self.assertRaises(ValueError):
            cart.add_link(self.root, self.p, "javascript:alert(1)")

    def test_curated_directory_is_shared_and_does_not_claim_apis(self):
        categories = {x["id"] for x in cart.SITE_CATEGORIES}
        self.assertEqual(len(cart.SITES), len({x["id"] for x in cart.SITES}))
        self.assertGreaterEqual(len(cart.SITES), 30)
        for site in cart.SITES:
            self.assertIn(site["group"], categories)
            self.assertEqual(cart.safe_url(site["url"]), site["url"])
            self.assertTrue(site["description"])
        self.assertEqual([x["id"] for x in cart.SITES if x.get("api")], ["commons"])
        self.assertEqual(len(cart.site_search(category="colors", library=self.library)), 3)
        self.assertEqual(cart.site_search("aboutppt", library=self.library)[0]["id"], "aboutppt")
        state = self.client()
        self.assertEqual([{k: v for k, v in s.items() if k not in ("favorite", "icon_url")}
                          for s in state["sites"]], cart.site_catalog(self.library)["items"])
        self.assertEqual(state["site_categories"], cart.SITE_CATEGORIES)
        extension = self.library / "channels" / "aboutppt.json"
        extension.parent.mkdir(parents=True, exist_ok=True)
        wf.write(extension, {"sites":[{"id":"about-color","name":"颜色测试","group":"colors","category":"配色工具",
                                       "url":"https://example.org/colors","description":"fixture","api":True}]})
        r = cart.site_search("颜色测试", library=self.library, collection="aboutppt")
        self.assertEqual(len(r), 1)
        self.assertFalse(r[0]["api"])

    def test_old_receipts_not_promoted_and_optimistic_lock(self):
        p = wf.upgrade({"schema_version": 2, "approvals":{"stage1":{"status":"passed"}}})
        self.assertEqual(p["approvals"], {})
        self.assertTrue(p["prior_receipts"]["approvals"])
        a, b = wf.load(self.root), wf.load(self.root)
        wf.save(self.root, a)
        with self.assertRaisesRegex(ValueError, "workspace changed"):
            wf.save(self.root, b)


if __name__ == "__main__":
    unittest.main()
