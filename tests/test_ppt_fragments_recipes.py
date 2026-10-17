"""Offline crop, inline-comment handoff and image-engine recording contracts."""
import base64
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_ppt_v3 as fixtures
import ppt_fragments as fragments
import ppt_assets as assets
import ppt_studio as studio
import ppt_workflow as wf
import ppt_annotation_io as annotations
import image_recipe as recipes
import newapi_image as engine


class FragmentRecipeTests(unittest.TestCase):
    setUp, tearDown = fixtures.V3Tests.setUp, fixtures.V3Tests.tearDown
    manifest, scan, client, post = fixtures.V3Tests.manifest, fixtures.V3Tests.scan, fixtures.V3Tests.client, fixtures.V3Tests.post

    def crop_body(self):
        r = self.scan()
        return dict(target_kind="reference", asset_id=r["id"], asset_version=r["version"],
                    sha256=r["sha256"], box=[.1, .2, .6, .7], title="上方导航", kind="header", tags=["进度"])

    def test_crop_pixels_lineage_and_source_unchanged(self):
        b = self.crop_body()
        before = self.image.read_bytes()
        r = fragments.crop(self.root, self.p, b, self.library)
        self.assertEqual(self.image.read_bytes(), before)
        self.assertEqual((r["technical"]["width"], r["technical"]["height"]), (320, 180))
        self.assertEqual(r["parent"], {"id": b["asset_id"], "version": b["asset_version"]})
        d = r["original_metadata"]["derivation"]
        self.assertEqual(d["box_pixels"], [64, 72, 384, 252])
        self.assertEqual(wf.file_sha(d["original_path"]), b["sha256"])
        self.assertTrue(Path(d["original_path"]).is_relative_to(self.library))
        self.assertEqual(r["kind"], "header")
        self.assertFalse(self.p["resource_cart"])
        self.assertFalse(self.p["generation_calls"])
        self.assertFalse(r["coding"]["palette"]["swatches"])
        self.assertEqual(assets.search("局部参考 进度", library=self.library)["total"], 1)

    def test_crop_invalid_coordinates_and_stale_image_rejected(self):
        b = self.crop_body()
        for box in ([-1, 0, 1, 1], [0, 0, float("nan"), 1], [1, 1, 0, 0], [0, 0, .001, .001]):
            with self.assertRaises(ValueError):
                fragments.crop(self.root, self.p, {**b, "box": box}, self.library)
        with self.assertRaises(ValueError):
            fragments.crop(self.root, self.p, {**b, "sha256": "stale"}, self.library)

    def test_crop_keeps_old_version_and_evidence_boundary(self):
        r = assets.import_image(self.image, {"title": "真实证据", "kind": "slide", "role": "evidence"}, self.library)
        b = self.crop_body() | {"asset_id": r["id"], "asset_version": r["version"], "sha256": r["sha256"]}
        result = fragments.crop(self.root, self.p, b, self.library)
        chosen = assets.choose(self.root, self.p, result["id"], result["version"], "material", self.library)
        self.assertTrue(chosen["protected_evidence"])
        self.assertFalse(chosen["model_allowed"])
        with self.assertRaises(ValueError):
            studio.asset_request({"prompt": "不要重画证据", "kind": "header",
                                  "references": [{"id": result["id"]}]}, self.library)

    def test_output_crop_and_api_no_generation_or_confirmation(self):
        c = studio.add_candidate(self.root, self.p, "P01", self.image)
        self.client()
        result = self.post("/api/v3/assets/crop", dict(target_kind="page", page_id="P01",
            candidate_id=c["id"], sha256=c["sha256"], box=[0, 0, .5, .5], title="成图中的一角", kind="illustration"))
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assertEqual(result.get_json()["original_metadata"]["derivation"]["source"]["candidate_id"], c["id"])
        self.assertFalse(wf.load(self.root)["approvals"])
        self.assertFalse(wf.load(self.root)["generation_calls"])

    def test_inline_comment_survives_handoff(self):
        b = self.crop_body()
        r = annotations.reference(self.root, self.p, b["asset_id"], b["asset_version"], b["sha256"],
            [{"tool": "rect", "points": [[.1, .1], [.3, .4]], "comment": "只参考此处章节进度"}],
            "1. 只参考此处章节进度", self.library, False)
        h = wf.read(r["handoff_path"])
        self.assertEqual(h["geometry"][0]["pixel_points"], [[64, 36], [192, 144]])
        self.assertEqual(h["geometry"][0]["comment"], "只参考此处章节进度")
        self.assertTrue(Path(r["overlay_path"]).is_file())

    def mocked_engine(self, mode="generate", extra=None, fail=False):
        out = self.root / "engine-output.png"
        args = [mode, "--prompt", "原文标题；英文视觉指令", "--out", str(out), "--model", "offline-test-model",
                "--size", "640x360", "--quality", "high", "--output-format", "png", "--retries", "0"]
        if mode != "generate":
            args += ["--image", str(self.image)]
        args += extra or []
        parsed = engine.build_parser().parse_args(args)
        body = {"model": "upstream-test-alias", "data": [{"b64_json": base64.b64encode(self.image.read_bytes()).decode(),
                                                       "revised_prompt": "原文标题；修订视觉指令"}]}
        method = "request_with_transport" if mode == "generate" else "request_multipart_with_transport"
        with patch.object(engine, "get_api_key", return_value="test-only"), \
                patch.object(engine, method, side_effect=RuntimeError("offline failed") if fail else None, return_value=body) as call, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            if fail:
                with self.assertRaises(RuntimeError):
                    parsed.func(parsed)
            else:
                self.assertEqual(parsed.func(parsed), 0)
        return out, call, output.getvalue()

    def test_generate_actual_request_and_separate_reported_model(self):
        out, call, _ = self.mocked_engine(extra=["--extra", "seed=123"])
        r = recipes.sidecar(out)
        self.assertEqual(r["parameters"]["seed"], 123)
        self.assertEqual(r["requested_model"], "offline-test-model")
        self.assertEqual(r["reported_model"], "upstream-test-alias")
        self.assertEqual(r["prompt"], call.call_args.args[3]["prompt"])
        self.assertEqual(r["inputs"], [])
        self.assertEqual(recipes.digest(r["outputs"][0]["path"]), recipes.digest(out))
        self.assertNotIn("test-only", Path(r["recipe_path"]).read_text(encoding="utf-8"))

    def test_edit_input_snapshots_reused_and_asset_recipe_pinned(self):
        out, call, _ = self.mocked_engine("edit")
        r = recipes.sidecar(out)
        old = self.image.read_bytes()
        self.assertEqual(Path(r["inputs"][0]["path"]).read_bytes(), old)
        self.assertIn(old, call.call_args.args[3])
        Image.new("RGB", (640, 360), "red").save(self.image)
        self.assertEqual(Path(r["inputs"][0]["path"]).read_bytes(), old)
        a = assets.import_image(out, {"title": "生成素材", "kind": "header"}, self.library)
        info = a["original_metadata"]["generation_recipe"]
        archived = wf.read(info["path"])
        self.assertTrue(Path(info["path"]).is_relative_to(self.library))
        self.assertTrue(Path(archived["inputs"][0]["path"]).is_file())

    def test_recipe_api_images_and_unknown_history(self):
        c = studio.add_candidate(self.root, self.p, "P01", self.image)
        self.client()
        client = self.web
        self.assertEqual(client.get("/api/v3/recipe?page_id=P01&candidate_id="+c["id"]).json["status"], "unavailable")
        out, _, _ = self.mocked_engine("edit")
        a = assets.import_image(out, {"title": "offline recipe", "kind": "header"}, self.library)
        q = "?asset_id="+a["id"]+"&version="+a["version"]
        self.assertEqual(client.get("/api/v3/recipe"+q).json["requested_model"], "offline-test-model")
        with client.get("/api/v3/recipe/input/0"+q) as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get("/api/v3/recipe/input/99"+q).status_code, 404)

    def test_dry_run_no_archive_no_network_and_failure_recorded(self):
        out, call, _ = self.mocked_engine(extra=["--dry-run"])
        call.assert_not_called()
        self.assertFalse((out.parent / "generation-records").exists())
        out, _, _ = self.mocked_engine(fail=True)
        rows = list((out.parent / "generation-records").glob("*/recipe.json"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(wf.read(rows[0])["status"], "failed")

    def test_variation_and_secret_rejection(self):
        # Variations retain their image and parameters, never manufacture a prompt.
        args = engine.build_parser().parse_args(["variation", "--image", str(self.image), "--out", str(self.root/"v.png"), "--dry-run"])
        with patch.object(engine, "request_multipart_with_transport") as call, contextlib.redirect_stdout(io.StringIO()):
            args.func(args)
        call.assert_not_called()
        with self.assertRaises(ValueError):
            recipes.begin(self.root/"bad.png", "generate", {"model": "x", "api_key": "private"})
        self.assertFalse((self.root/"generation-records").exists())

    def test_engine_models_unaffected(self):
        with patch.object(engine, "get_api_key", return_value="test-only"), patch.object(engine, "request_with_transport", return_value={"data":[]}), contextlib.redirect_stdout(io.StringIO()):
            args=engine.build_parser().parse_args(["models"])
            self.assertEqual(args.func(args), 0)

    def test_candidate_recipe_copies_inputs_and_preserves_parent_generation(self):
        out, _, _ = self.mocked_engine("edit")
        c = studio.add_candidate(self.root, self.p, "P01", out)
        pointer = c["metadata"]["generation_recipe"]
        self.assertEqual(wf.file_sha(pointer["path"]), pointer["sha256"])
        archived = recipes.sidecar(c["path"])
        self.assertEqual(archived["id"], recipes.sidecar(out)["id"])
        again = recipes.begin(self.root/"variant.png", "edit", {"model":"offline-test-model"},
                              [c["path"]])
        self.assertEqual(again["inputs"][0]["parent_recipe_id"], archived["id"])
        self.assertEqual(again["inputs"][0]["sha256"], c["sha256"])

    def test_variation_real_stub_records_no_prompt(self):
        out = self.root / "variation.png"
        args = engine.build_parser().parse_args(["variation", "--image", str(self.image), "--out", str(out),
                                                "--size", "640x360", "--output-format", "png"])
        response = {"data":[{"b64_json":base64.b64encode(self.image.read_bytes()).decode()}]}
        with patch.object(engine, "get_api_key", return_value="test-only"), patch.object(engine, "request_multipart_with_transport", return_value=response), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        r = recipes.sidecar(out)
        self.assertEqual(r["mode"], "variation")
        self.assertEqual(r["prompt"], "")
        self.assertIsNone(r["reported_model"])

    def test_recipe_archive_reimport_is_idempotent_and_crop_retains_parent_recipe(self):
        out, _, _ = self.mocked_engine("edit")
        dest = self.library / "generation-records"
        first = recipes.bundle_to(out, dest)
        self.assertEqual(first, recipes.bundle_to(out, dest))
        c = studio.add_candidate(self.root, self.p, "P01", out)
        self.assertEqual(first, recipes.bundle_to(c["path"], dest))
        r = fragments.crop(self.root, self.p, {
            "target_kind": "page", "page_id": "P01", "candidate_id": c["id"], "sha256": c["sha256"],
            "box": [0, 0, .4, .3], "title": "生成图的局部", "kind": "header"}, self.library)
        kept = r["original_metadata"]["derivation"]["source_generation_recipe"]
        self.assertEqual(first, kept)
        self.assertNotIn("generation_recipe", r["original_metadata"])


if __name__ == "__main__":
    unittest.main()
