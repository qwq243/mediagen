"""Offline fixtures only. These reports are NOT real user approvals or visual audits."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ppt_workflow as wf
import ppt_confirm_ui as ui


class ImagePptWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.library = self.root / "library"
        self.p = wf.upgrade({"project_name": "offline fixture", "test_fixture": True, "pages": [
            {"page_id": "P01", "page_role": "cover", "page_text": "标题一"},
            {"page_id": "P02", "page_role": "content", "page_text": "结论二\n说明"},
        ]})
        self.p["communication"].update(audience="评委", communication_intent="说明实际方法",
                                        duration_seconds=60, reading_mode="balanced")
        for pg in self.p["pages"]:
            pg["logic"].update(purpose="说明", key_message_or_question="结论",
                                information_relationship="contrast", visual_expression="左右对照",
                                duration_seconds=20)
            pg["speaker_notes"] = "解释原始证据，说明适用边界，再引出下一页。"
        wf.save(self.root, self.p)

    def tearDown(self):
        self.tmp.cleanup()

    def approve_basics(self):
        wf.confirm(self.root, self.p, "stage1", "OFFLINE TEST ONLY")
        wf.confirm(self.root, self.p, "stage2", "OFFLINE TEST ONLY")
        for phase in ("content", "prompts"):
            self.report(phase)

    def report(self, phase, page=None):
        r = {"phase": phase, "page_id": page, "independent": True,
             "reviewer": "offline fixture, NOT an actual reviewer",
             "subject_hash": wf.subject(self.root, self.p, phase, page), "status": "passed",
             "evidence": ["synthetic test assertion"], "findings": []}
        return wf.audit(self.root, self.p, r)

    def images(self):
        for pg in self.p["pages"]:
            path = self.root / (pg["page_id"] + ".png")
            Image.new("RGB", (640, 360), "white").save(path)
            wf.select_output(self.root, self.p, pg["page_id"], path, "mock", "OFFLINE FIXTURE, NOT model result")
            self.report("visual", pg["page_id"])

    def delivery_ready(self):
        self.approve_basics(); self.images()
        wf.confirm(self.root, self.p, "samples", "OFFLINE TEST ONLY")
        self.report("deck"); self.report("notes")

    def test_legacy_never_approves(self):
        p = wf.upgrade({"requirement_alignment": {"status": "confirmed"}, "pages": []})
        self.assertEqual(p["approvals"], {})

    def test_explicit_legacy_schema_is_normalized(self):
        p = wf.upgrade({"schema_version": 1, "pages": []})
        self.assertEqual(p["schema_version"], 3)
        self.assertEqual(p["legacy_schema_version"], 1)
        self.assertEqual(wf.upgrade(p), p)

    def test_null_optional_transition_inherits_defaults(self):
        self.p["pages"][0]["transition"] = None
        normalized = wf.upgrade(self.p)
        self.assertNotIn("transition", normalized["pages"][0])
        self.assertTrue(wf.check(self.root, normalized)["ok"])
        normalized["pages"][0]["transition"] = "invalid"
        self.assertTrue(any("override must" in x for x in wf.check(self.root, normalized)["errors"]))

    def test_positive_negative_prompt_conflicts_block(self):
        pg = self.p["pages"][1]
        pg["required_elements"] = ["timeline"]
        pg["forbidden_elements"] = ["timeline"]
        pg["visual_instructions"] = "Use a full-width color band"
        pg["forbidden_items"] = ["full-width color band"]
        errors = wf.check(self.root, self.p)["errors"]
        self.assertTrue(any("required and forbidden" in e for e in errors))
        self.assertTrue(any("also forbidden" in e for e in errors))

    def test_revised_draft_does_not_reset_to_original_design(self):
        self.p["design_candidates"] = [{"id": "initial", "visual_style": "dark-tech"}]
        self.p["design_choice_recorded"] = True
        self.p["design"]["typography"]["display"] = "STKaiti"
        rec = wf.recommendations(self.root, self.p, 2)
        self.assertEqual(rec["design_directions"]["candidates"][0]["visual_style"], "swiss-minimal")
        self.assertEqual(rec["design_directions"]["candidates"][0]["display_font"], "STKaiti")
        self.assertEqual(len(rec["design_directions"]["candidates"]), 2)

    def test_web_audit_states_label_stale_instead_of_passed(self):
        self.approve_basics()
        self.p["design"]["palette"]["primary"] = "#123456"
        states = wf.recommendations(self.root, self.p, 2)["mediagen"]["audit_states"]
        self.assertEqual(states["content"]["effective_status"], "passed")
        self.assertEqual(states["prompts"]["effective_status"], "stale")

    def test_art_font_global_ban_conflict_not_literal_text(self):
        self.p["design"]["typography"]["display"] = "STZhongsong"
        self.p["pages"][0]["forbidden_items"] = ["宋体楷体书法体"]
        self.assertTrue(any("font prohibition" in e for e in wf.check(self.root, self.p)["errors"]))
        self.p["pages"][0]["forbidden_items"] = []
        self.p["pages"][0]["page_text"] = "宋体与真人政策作为讨论内容，不是绘图命令"
        self.assertTrue(wf.check(self.root, self.p)["ok"])

    def test_native_direction_comparison_has_no_side_effects(self):
        app = (wf.HERE / "vendor/ppt_master/static/app.js").read_text(encoding="utf-8")
        signature = app.split("function directionStateSignature(candidate)", 1)[1].split(
            "function activeDirectionAdjusted", 1)[0]
        self.assertNotIn("mediagenApplyDirection", signature)
        apply = app.split("function applyDesignDirection(candidate", 1)[1].split(
            "function renderDesignDirections", 1)[0]
        self.assertIn("mediagenApplyDirection", apply)

    def test_defaults_humans_notes_transition_text(self):
        self.assertEqual(self.p["design"]["human_policy"], "none")
        self.assertTrue(self.p["notes_policy"]["enabled"])
        self.assertFalse(self.p["transition"]["enabled"])
        self.assertTrue(self.p["design"]["text_in_image"])

    def test_prompt_keeps_chinese_excludes_notes(self):
        prompt = wf.prompts(self.root, self.p)["P02"]
        self.assertIn("结论二\n说明", prompt)
        self.assertNotIn(self.p["pages"][1]["speaker_notes"], prompt)
        self.assertIn("No people", prompt)
        self.assertIn("Microsoft YaHei", prompt)

    def test_page_edit_invalidates_production_not_communication(self):
        self.approve_basics()
        self.p["pages"][1]["page_text"] += "修改"
        r = wf.check(self.root, self.p, "samples")
        self.assertFalse(r["ok"])
        self.assertTrue(wf.valid(self.p["approvals"]["stage1"], wf.subject(self.root, self.p, "stage1")))
        self.assertTrue(any("stage2:" in x for x in r["errors"]))
        self.assertTrue(any("prompts:" in x for x in r["errors"]))

    def test_palette_edit_keeps_content_but_invalidates_design(self):
        self.approve_basics()
        self.p["design"]["palette"]["accent"] = "#FF4400"
        self.assertTrue(wf.valid(self.p["approvals"]["stage1"], wf.subject(self.root, self.p, "stage1")))
        self.assertFalse(wf.valid(self.p["approvals"]["stage2"], wf.subject(self.root, self.p, "stage2")))

    def test_reference_file_change_invalidates_style(self):
        f = self.root / "ref.png"; Image.new("RGB", (10, 10)).save(f)
        self.p["references"] = [{"id": "style1", "role": "style", "path": str(f)}]
        old = wf.design_hash(self.root, self.p)
        Image.new("RGB", (10, 10), "red").save(f)
        self.assertNotEqual(old, wf.design_hash(self.root, self.p))

    def test_image_change_invalidates_visual_review(self):
        self.images()
        f = self.root / "P02.png"; Image.new("RGB", (640, 360), "red").save(f)
        self.assertFalse(wf.valid(self.p["audits"]["visual:P02"], wf.subject(self.root, self.p, "visual", "P02")))

    def test_notes_change_invalidates_only_notes_review(self):
        self.delivery_ready()
        self.p["pages"][0]["speaker_notes"] += "改稿"
        self.assertTrue(wf.valid(self.p["audits"]["deck"], wf.subject(self.root, self.p, "deck")))
        self.assertFalse(wf.valid(self.p["audits"]["notes"], wf.subject(self.root, self.p, "notes")))

    def test_missing_review_blocks_paid_call(self):
        with patch.object(wf.subprocess, "run") as engine:
            with self.assertRaises(ValueError):
                wf.render(self.root, self.p, ["P01"], True, True)
            engine.assert_not_called()

    def test_dry_run_never_calls_engine(self):
        self.approve_basics()
        with patch.object(wf.subprocess, "run") as engine:
            result = wf.render(self.root, self.p, ["P01"])
            self.assertTrue(result["dry_run"]); engine.assert_not_called()

    def test_no_authorization_blocks_cost(self):
        self.approve_basics()
        with self.assertRaises(ValueError):
            wf.render(self.root, self.p, ["P01"], True, True)

    def test_independent_audit_required(self):
        with self.assertRaises(ValueError):
            wf.audit(self.root, self.p, {"phase": "content", "status": "passed", "evidence": ["x"]})

    def test_stale_audit_rejected(self):
        with self.assertRaises(ValueError):
            wf.audit(self.root, self.p, {"phase": "content", "status": "passed", "evidence": ["x"],
                                        "independent": True, "reviewer": "test", "subject_hash": "stale"})

    def test_blocking_issue_cannot_pass(self):
        with self.assertRaises(ValueError):
            wf.audit(self.root, self.p, {"phase": "content", "status": "passed", "evidence": ["x"],
                                        "independent": True, "reviewer": "test",
                                        "subject_hash": wf.subject(self.root, self.p, "content"),
                                        "findings": [{"severity": "major", "resolution": "pending"}]})

    def test_time_budget_and_human_conflict(self):
        self.p["communication"]["duration_seconds"] = 10
        self.p["pages"][0]["visual_instructions"] = "photorealistic person"
        errors = wf.check(self.root, self.p)["errors"]
        self.assertTrue(any("human" in x for x in errors))
        self.assertTrue(any("time budget" in x for x in errors))

    def test_artistic_display_allowed(self):
        self.p["design"]["typography"]["display"] = "华文行楷"
        self.assertTrue(wf.check(self.root, self.p)["ok"])

    def test_file_path_in_page_id_rejected(self):
        with self.assertRaises(ValueError):
            wf.upgrade({"pages": [{"page_id": "../escape"}]})

    def test_evidence_upload_forbidden(self):
        f = self.root / "real.png"; Image.new("RGB", (10, 10)).save(f)
        self.p["references"] = [{"id": "real", "role": "evidence", "path": str(f),
                                "upload_allowed": True, "send_to_model": True}]
        self.assertFalse(wf.check(self.root, self.p)["ok"])

    def test_deterministic_evidence_preserved(self):
        real = self.root / "real.png"; Image.new("RGB", (50, 50), "red").save(real)
        output = self.root / "slide.png"; Image.new("RGB", (640, 360), "white").save(output)
        self.p["references"] = [{"id": "real", "role": "evidence", "path": str(real)}]
        self.p["pages"][0]["materials"] = [{"reference_id": "real", "box": [0.1, 0.1, 0.5, 0.5]}]
        original = wf.file_sha(real)
        wf.compose_evidence(self.root, self.p, "P01", output)
        self.assertEqual(original, wf.file_sha(real))
        with Image.open(output) as im:
            self.assertEqual(im.getpixel((224, 126)), (255, 0, 0))

    def test_sample_before_visual_review_rejected(self):
        self.approve_basics()
        for pg in self.p["pages"]:
            f = self.root / (pg["page_id"] + ".png"); Image.new("RGB", (640, 360)).save(f)
            wf.select_output(self.root, self.p, pg["page_id"], f, "mock", "test")
        with self.assertRaises(ValueError):
            wf.confirm(self.root, self.p, "samples", "OFFLINE TEST")

    def test_export_notes_transitions_roundtrip(self):
        self.p["transition"]["enabled"] = True
        self.delivery_ready()
        with patch.object(wf, "index_project", return_value="test"):
            result = wf.export(self.root, self.p, self.root / "test.pptx")
        self.assertEqual(len(result["slides"]), 2)
        self.assertEqual(result["slides"][0]["effect"], "fade")
        self.assertEqual(result["slides"][0]["duration_ms"], 400)
        self.assertIsNone(result["slides"][0]["advance_after_ms"])
        self.assertTrue((self.root / "test.notes.md").exists())

    def test_notes_off_export(self):
        self.p["notes_policy"]["enabled"] = False
        self.delivery_ready()
        with patch.object(wf, "index_project", return_value="test"):
            result = wf.export(self.root, self.p, self.root / "no-notes.pptx")
        self.assertIsNone(result["slides"][0]["effect"])
        self.assertFalse((self.root / "no-notes.notes.md").exists())

    def test_library_search_and_secrets(self):
        wf.library_record("feedback", {"comment": "同类标题字体应一致", "scope": "this_project"}, self.library)
        self.assertEqual(len(wf.library_search("标题", "feedback", self.library)), 1)
        with self.assertRaises(ValueError):
            wf.library_record("reference", {"api_key": "do-not-store"}, self.library)

    def client(self):
        self.app = ui.create_app(self.root)
        self.c = self.app.test_client()
        token = self.c.get("/api/session").get_json()["csrf"]
        return {"X-Mediagen-CSRF": token}

    def test_web_silence_is_not_approval(self):
        self.client()
        self.c.get("/api/recommendations")
        self.assertEqual(wf.load(self.root)["approvals"], {})

    def test_web_host_origin_csrf(self):
        headers = self.client()
        self.assertEqual(self.c.get("/", headers={"Host": "evil.invalid"}).status_code, 403)
        self.assertEqual(self.c.post("/api/confirm", json={}).status_code, 403)
        self.assertEqual(self.c.post("/api/confirm", json={}, headers={
            **headers, "Origin": "http://evil.invalid"}).status_code, 403)

    def test_web_stage1_preserves_content_divergence_proposal(self):
        self.p["communication"]["content_divergence"] = "允许重组初稿，但不得把愿景写成已实现。"
        wf.save(self.root, self.p)
        self.client()
        rec = self.c.get("/api/recommendations").get_json()
        self.assertEqual(rec["content_divergence"]["value"],
                         self.p["communication"]["content_divergence"])
        self.assertEqual(wf.load(self.root)["approvals"], {})

    def test_web_stage1_receipt_and_stage2_recommendations(self):
        headers = self.client()
        rec = self.c.get("/api/recommendations").get_json()
        payload = {"stage": "stage1", "_source_hash": rec["mediagen"]["source_hash"],
                   "audience": "评委", "mediagen_choices": {"pages": self.p["pages"]}}
        response = self.c.post("/api/confirm", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["origin"], "web")
        self.assertEqual(self.c.get("/api/recommendations").get_json()["stage"], "stage2")
        self.assertEqual(self.c.get("/api/session").get_json()["recommendation_stage_number"], 2)

    def test_web_stale_submission_rejected(self):
        headers = self.client()
        self.assertEqual(self.c.post("/api/confirm", json={
            "stage": "stage1", "_source_hash": "stale"}, headers=headers).status_code, 409)

    def test_web_reference_and_human_notes_motion_choices(self):
        updated = ui.apply_choices(copy.deepcopy(self.p), {
            "mediagen_choices": {"human_policy": "illustrated", "display": "华文行楷",
                                "notes_policy": {"enabled": False, "mode": "generate", "audio": False},
                                "transition": {"enabled": True, "effect": "push", "duration": 0.5, "advance": "manual"},
                                "references": [{"id": "user", "role": "style", "url": "https://example.org",
                                                "send_to_model": False}]}}, "stage2")
        self.assertTrue(wf.check(self.root, updated)["ok"])
        self.assertEqual(updated["design"]["human_policy"], "illustrated")
        self.assertFalse(updated["notes_policy"]["enabled"])

    def test_web_native_font_and_palette_roundtrip(self):
        updated = ui.apply_choices(copy.deepcopy(self.p), {
            "color": {"palette": {"body_text": "#112233", "secondary_accent": "#445566"}},
            "typography": {"heading": {"primary": "STZhongsong", "english": "Georgia"},
                           "body": {"primary": "DengXian", "english": "Arial"}, "body_size": 28}}, "stage2")
        self.assertEqual(updated["design"]["typography"]["heading"], "STZhongsong")
        self.assertEqual(updated["design"]["typography"]["body"], "DengXian")
        self.assertEqual(updated["design"]["palette"]["text"], "#112233")
        self.assertTrue(wf.check(self.root, updated)["ok"])
        rec = wf.recommendations(self.root, updated, 2)
        self.assertEqual(rec["typography"]["candidates"][0]["heading"]["primary"], "STZhongsong")
        self.assertEqual(rec["color"]["candidates"][0]["palette"]["body_text"], "#112233")

    def test_per_page_invalid_transition_blocks(self):
        self.p["pages"][0]["transition"] = {"duration": -2, "advance": "auto", "sound": True}
        self.assertFalse(wf.check(self.root, self.p)["ok"])

    def test_all_curated_effects_export_readback(self):
        for effect in ("push", "wipe", "split", "cover"):
            with self.subTest(effect=effect):
                self.p["transition"].update(enabled=True, effect=effect)
                self.delivery_ready()
                with patch.object(wf, "index_project", return_value="test"):
                    result = wf.export(self.root, self.p, self.root / (effect + ".pptx"))
                self.assertEqual(result["slides"][0]["effect"], effect)
                self.assertEqual(result["slides"][0]["duration_ms"], 400)

    def test_failed_engine_not_retried_and_counted(self):
        self.approve_basics()
        self.p["generation_authorization"] = {"id": "test", "max_calls": 2,
                                               "design_hash": wf.design_hash(self.root, self.p),
                                               "user_evidence": "OFFLINE TEST ONLY"}
        with patch.object(wf.subprocess, "run", return_value=type("Result", (), {"returncode": 9})()) as engine:
            with self.assertRaises(ValueError):
                wf.render(self.root, self.p, ["P01", "P02"], True, True)
            self.assertEqual(engine.call_count, 1)
            self.assertEqual(wf.load(self.root)["generation_calls"][0]["status"], "failed")

    def test_feedback_index_scoped_children(self):
        ids = wf.record_feedback(self.root, self.p, {
            "comment": "标题字体应统一", "scope": "similar_projects",
            "preferences": [{"description": "同角色同字体"}],
            "issues": [{"description": "标题漂移", "status": "open"}],
            "lessons": [{"description": "先确认代表页"}]}, self.library)
        self.assertEqual(len(ids["issues"]), 1)
        self.assertEqual(wf.library_search("同角色", "preference", self.library)[0]["payload"]["scope"],
                         "similar_projects")

    def test_retrospective_cannot_produce(self):
        self.approve_basics()
        self.p["retrospective_only"] = True
        with self.assertRaises(ValueError):
            wf.render(self.root, self.p, ["P01"])

    def test_reading_change_returns_to_stage1_without_fake_receipt(self):
        self.approve_basics()
        headers = self.client()
        rec = self.c.get("/api/recommendations").get_json()
        response = self.c.post("/api/confirm", json={
            "stage": "stage2", "_source_hash": rec["mediagen"]["source_hash"],
            "delivery_purpose": "text"}, headers=headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.c.get("/api/recommendations").get_json()["stage"], "stage1")
        self.assertFalse((self.root / "confirm_ui/receipt.stage2.json").exists())

    def test_stale_writer_does_not_clobber_newer_changes(self):
        a, b = wf.load(self.root), wf.load(self.root)
        a["communication"]["audience"] = "newer edit"
        wf.save(self.root, a)
        b["communication"]["audience"] = "stale edit"
        with self.assertRaises(ValueError):
            wf.save(self.root, b)
        self.assertEqual(wf.load(self.root)["communication"]["audience"], "newer edit")

    def test_browser_new_path_is_pending_not_readable(self):
        updated = ui.apply_choices(copy.deepcopy(self.p), {"mediagen_choices": {"references": [{
            "id": "newfile", "role": "style", "path": str(self.root / "private.png"),
            "upload_allowed": True, "send_to_model": True}]}}, "stage2")
        ref = updated["references"][0]
        self.assertNotIn("path", ref)
        self.assertFalse(ref["send_to_model"])
        self.assertEqual(ref["registration"], "pending_agent_inspection")

    def test_browser_cannot_relabel_registered_evidence(self):
        self.p["references"] = [{"id": "real", "role": "evidence", "path": "real.png"}]
        with self.assertRaises(ValueError):
            ui.apply_choices(copy.deepcopy(self.p), {"mediagen_choices": {"references": [{
                "id": "real", "role": "style", "path": "real.png", "send_to_model": True}]}}, "stage2")

    def test_agent_reference_import_managed_copy(self):
        src = self.root / "original.png"; Image.new("RGB", (100, 100), "red").save(src)
        ref = wf.register_reference(self.root, self.p, {
            "id": "r1", "role": "style", "path": str(src), "license": "user-owned",
            "use": "palette reference", "upload_allowed": True, "send_to_model": True})
        self.assertTrue(Path(ref["path"]).is_relative_to(self.root / "assets"))
        self.assertEqual(wf.file_sha(src), wf.file_sha(ref["path"]))

    def test_generated_kind_needs_matching_call(self):
        src = self.root / "imported.png"; Image.new("RGB", (640, 360)).save(src)
        with self.assertRaises(ValueError):
            wf.select_output(self.root, self.p, "P01", src, "generated", "claimed engine call")

    def test_mock_preview_cannot_approve_real_job(self):
        self.delivery_ready()
        self.p["test_fixture"] = False
        with self.assertRaises(ValueError):
            wf.confirm(self.root, self.p, "samples", "NOT REAL")
        self.assertFalse(wf.check(self.root, self.p, "export")["ok"])

    def test_samples_need_server_side_design_approval(self):
        wf.confirm(self.root, self.p, "stage1", "TEST")
        self.report("content"); self.report("prompts"); self.images()
        with self.assertRaises(ValueError):
            wf.confirm(self.root, self.p, "samples", "TEST")

    def test_after_sample_approval_cover_rerender_is_edit_lane(self):
        self.delivery_ready()
        result = wf.render(self.root, self.p, ["P01"])
        self.assertIn("edit", result["calls"][0])
        self.assertIn("--image", result["calls"][0])
        with self.assertRaises(ValueError):
            wf.render(self.root, self.p, ["P01", "P02", "P03"], lane="samples")

    def test_logic_human_conflict_is_checked(self):
        self.p["pages"][0]["logic"]["visual_expression"] = "portrait of a student"
        self.assertFalse(wf.check(self.root, self.p)["ok"])

    def test_feedback_nonlist_child_rejected(self):
        with self.assertRaises(ValueError):
            wf.record_feedback(self.root, self.p, {"comment": "test", "issues": "bad string"}, self.library)


if __name__ == "__main__":
    unittest.main()
