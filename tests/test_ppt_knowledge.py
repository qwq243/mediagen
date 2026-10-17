import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ppt_knowledge as k
import ppt_design_spec as ds


def sample():
    return k.empty_annotation({
        "id": "a-test", "deck_code": "DK-000001", "page_code": "PG-000002",
        "version": "a" * 64, "sha256": "b" * 64, "title": "测试",
        "work": "测试", "technical": {"width": 1280, "height": 720},
        "tags": ["保留旧标签"],
    })


def test_unknown_is_explicit():
    a = sample()
    assert not k.validate(a)
    assert a["review"]["status"] == "suggested"
    assert a["source"]["permissions"]["model_upload"] == "unknown"


def test_source_version_cannot_escape_stage(tmp_path):
    a = sample()
    a["source"]["version"] = "../../escape"
    with pytest.raises(ValueError):
        k.stage(tmp_path, [a])


def test_geometry_and_duplicate_ids():
    a = sample()
    e = k.element("title", "title", "标题", [.1, .1, .4, .1])
    a["elements"] = [e, copy.deepcopy(e)]
    assert any("duplicate" in s for s in k.validate(a))
    a["elements"] = [e]
    e["bbox"] = [.9, .1, .4, .1]
    assert any("bbox" in s for s in k.validate(a))


def test_font_not_guessed():
    a = sample()
    e = k.element("title", "title", "标题", [.1, .1, .4, .1])
    a["elements"] = [e]
    e["observed"]["font_family"] = k.value("微软雅黑", "fontFamily", "estimated", "看起来像")
    assert any("font_family" in s for s in k.validate(a))


def test_reference_and_parent_cycle():
    a = sample()
    a["elements"] = [k.element("one", "card", "卡", [0, 0, 1, 1])]
    a["elements"][0]["parent_id"] = "one"
    a["relations"] = [{"id": "r1", "type": "connects", "from": "one", "to": "missing",
                       "direction": "forward", "label": None, "evidence": "visible"}]
    errors = k.validate(a)
    assert any("cycle" in s for s in errors)
    assert any("missing" in s for s in errors)


def test_review_cannot_self_certify(tmp_path):
    a = sample()
    k.stage(tmp_path, [a])
    with pytest.raises(ValueError, match="independent"):
        k.record_review(tmp_path, a["asset_id"], a["source"]["version"],
                        {"reviewer": a["review"]["annotator"], "status": "reviewed"})


def test_stage_immutable_history(tmp_path):
    a = sample()
    first = k.stage(tmp_path, [a])
    a["page"]["title"] = "新版本标注"
    second = k.stage(tmp_path, [a])
    assert first[0] != second[0]
    assert len(list((tmp_path / "knowledge" / "candidates").rglob("*.json"))) == 2


def spec():
    return {"version": 1, "canvas": [1280, 720],
            "global": {"tokens": {"ink": {"type": "color", "value": "#123456"}}},
            "templates": {}, "pages": {"P01": {"elements": [
                {"id": "t", "kind": "title", "bbox": [.1, .1, .5, .1], "text": "准确文案"}
            ]}}, "hard_constraints": {"no_fake_evidence": True}}


def test_deterministic_compile_and_units():
    a = spec()
    one = ds.compile_spec(a, "P01")
    assert one == ds.compile_spec(json.loads(json.dumps(a)), "P01")
    assert one["elements"][0]["pixels"] == [128, 72, 640, 72]
    assert ds.compile_spec(a, "P01", canvas=[2560, 1440])["elements"][0]["pixels"] == [256, 144, 1280, 144]


def test_hard_constraint_conflict():
    a = spec()
    a["pages"]["P01"]["hard_constraints"] = {"no_fake_evidence": False}
    with pytest.raises(ValueError, match="hard"):
        ds.compile_spec(a, "P01")


def test_missing_measurement_is_pending():
    assert ds.audit(ds.compile_spec(spec(), "P01"), {})["status"] == "pending"


def test_geometry_and_text_fail():
    target = ds.compile_spec(spec(), "P01")
    result = ds.audit(target, {"elements": {"t": {"bbox": [.15, .1, .5, .1], "text": "错字",
                                                 "text_verified": True}}})
    assert result["status"] == "failed"
    assert any(x["check"] == "center" and x["status"] == "failed" for x in result["checks"])


def test_unknown_color_not_automatically_pass():
    a = spec()
    a["pages"]["P01"]["elements"][0]["flat_color"] = "#123456"
    result = ds.audit(ds.compile_spec(a, "P01"), {})
    assert any(x["check"] == "flat_color" and x["status"] == "pending" for x in result["checks"])


def test_color_delta_e():
    assert ds.delta_e("#123456", "#123456") == pytest.approx(0)
    assert ds.delta_e("#ffffff", "#000000") > 90


def test_alias_and_permission_filter():
    a = sample()
    a["page"].update(role="RL-COVER", layout=["LY-HERO"])
    a["deck"]["styles"] = ["蓝白医疗"]
    a["elements"] = [k.element("t", "title", "毛笔标题", [.1, .1, .5, .1])]
    a["elements"][0]["observed"]["font_class"] = k.value("FT-BRUSH", "enum", "estimated", "视觉")
    assert k.rank([a], "蓝白医疗 书法 封面")["total"] == 1
    assert k.rank([a], "微软雅黑")["total"] == 0
    assert k.rank([a], "", {"usage": "reusable"})["total"] == 0


def test_verdict_strings_do_not_pass():
    with pytest.raises(ValueError, match="boolean"):
        ds.audit(ds.compile_spec(spec(), "P01"), {"hard_constraints_passed": "false"})


def test_text_conflict():
    with pytest.raises(ValueError, match="conflicts"):
        ds.validate_project_spec(spec(), [{"page_id": "P01", "page_text": "其他文案"}])


@pytest.fixture
def project(tmp_path):
    import ppt_workflow as wf
    import ppt_confirm_ui as ui
    import sqlite3
    from PIL import Image
    root, library = tmp_path / "project", tmp_path / "library"
    library.mkdir()
    p = wf.upgrade({"test_fixture": True, "pages": [
        {"page_id": "P01", "page_role": "cover", "page_text": "准确文案"},
        {"page_id": "P02", "page_role": "content", "page_text": "第二页"}
    ]})
    p["communication"]["reading_mode"] = "balanced"
    wf.save(root, p)
    a = sample()
    a["elements"] = [k.element("t", "title", "标题", [.1, .1, .5, .1])]
    image = tmp_path / "test.png"
    Image.new("RGB", (1280, 720), "white").save(image)
    a["source"]["sha256"] = k.file_hash(image)
    k.stage(library, [a])
    record = {"id": a["asset_id"], "deck_code": a["deck_id"], "page_code": a["page_id"],
              "version": a["source"]["version"], "sha256": a["source"]["sha256"], "source_path": str(image)}
    with sqlite3.connect(library / "index.sqlite3") as db:
        db.execute("CREATE TABLE assets_v3(id TEXT, version TEXT, payload TEXT, current INTEGER)")
        db.execute("INSERT INTO assets_v3 VALUES(?,?,?,1)", (record["id"], record["version"], json.dumps(record)))
    client = ui.create_app(root, library).test_client()
    return root, library, client, a


def test_http_filters_detail_and_schema(project):
    _, _, c, a = project
    result = c.get("/api/v3/knowledge").get_json()
    assert result["total"] == 1
    assert result["coverage_summary"]["pages"] == 1
    assert result["coverage_summary"]["independently_reviewed"] == 0
    assert c.get("/api/v3/knowledge?status=reviewed").get_json()["total"] == 0
    detail = c.get("/api/v3/knowledge/" + a["asset_id"]).get_json()
    assert detail["elements"][0]["bbox"] == [.1, .1, .5, .1]
    assert c.get("/api/v3/knowledge/schema").get_json()["$schema"]
    assert c.get("/api/v3/knowledge?hack=true").status_code == 409


def test_http_csrf_revision_conflict_and_save(project):
    root, _, c, _ = project
    state = c.get("/api/v3/design-spec").get_json()
    headers = {"X-Mediagen-CSRF": state["csrf"]}
    body = {"revision": state["revision"], "spec": state["spec"]}
    assert c.post("/api/v3/design-spec", json=body).status_code == 403
    response = c.post("/api/v3/design-spec", json=body, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["affected_pages"] == ["P01", "P02"]
    assert c.post("/api/v3/design-spec", json=body, headers=headers).status_code == 409
    assert (root / "revisions").exists()


def test_borrow_idempotent_no_upload(project):
    import ppt_workflow as wf
    root, _, c, a = project
    state = c.get("/api/v3/design-spec").get_json()
    detail = c.get("/api/v3/knowledge/" + a["asset_id"]).get_json()
    body = {"revision": state["revision"], "annotation_hash": detail["annotation_hash"],
            "element_id": "t", "purpose": "structure"}
    headers = {"X-Mediagen-CSRF": state["csrf"]}
    response = c.post("/api/v3/knowledge/" + a["asset_id"] + "/borrow", json=body, headers=headers)
    assert response.status_code == 200
    body["revision"] = response.get_json()["revision"]
    response = c.post("/api/v3/knowledge/" + a["asset_id"] + "/borrow", json=body, headers=headers)
    assert response.status_code == 200
    p = wf.load(root)
    assert len(p["knowledge_requests"]) == 1
    assert p["knowledge_requests"][0]["send_to_model"] is False


def test_current_source_version_invalidates_annotation(project):
    import sqlite3
    _, library, c, a = project
    with sqlite3.connect(library / "index.sqlite3") as db:
        r = json.loads(db.execute("SELECT payload FROM assets_v3").fetchone()[0])
        r["version"] = "changed"
        db.execute("UPDATE assets_v3 SET payload=?", (json.dumps(r),))
    assert c.get("/api/v3/knowledge").get_json()["total"] == 0
    assert c.get("/api/v3/knowledge/" + a["asset_id"]).status_code == 409


def test_ordered_input_package_matches_render_resolver(project):
    from PIL import Image
    import ppt_workflow as wf
    root, _, _, _ = project
    p = wf.load(root)
    for id in ("style", "evidence"):
        path = root / (id + ".png")
        Image.new("RGB", (100, 100), "red").save(path)
        p["references"].append({"id": id, "path": str(path), "send_to_model": True, "role": "style"})
    p["pages"][0]["reference_ids"] = ["evidence", "style"]
    package = ds.request_package(root, p, "P01", True)
    assert [r["id"] for r in package["inputs"]] == ["evidence", "style"]
    assert package == ds.request_package(root, p, "P01", True)
    path = ds.freeze_package(root, package)
    archived = json.loads(Path(path).read_text(encoding="utf-8"))
    assert len(archived["inputs"]) == 2
    assert all(k.file_hash(Path(path).parent / r["path"]) == r["sha256"] for r in archived["inputs"])


def test_atomic_page_change_keeps_unrelated_page_hash(project):
    import ppt_workflow as wf
    from ppt_knowledge_http import default_spec
    root, _, _, _ = project
    p = wf.load(root)
    p["design"]["atomic_spec"] = default_spec(p)
    before = [wf.page_design_hash(root, p, pg) for pg in p["pages"]]
    p["design"]["atomic_spec"]["pages"]["P01"]["elements"][0]["bbox"][0] = .06
    after = [wf.page_design_hash(root, p, pg) for pg in p["pages"]]
    assert before[0] != after[0]
    assert before[1] == after[1]


def test_browser_numeric_roundtrip_preserves_design_fingerprint(project):
    """JSON.stringify serializes 5.0 as 5; that is not a design change."""
    import ppt_workflow as wf
    from ppt_knowledge_http import default_spec
    root, _, c, _ = project
    p = wf.load(root)
    p["design"]["atomic_spec"] = default_spec(p)
    wf.save(root, p)
    state = c.get("/api/v3/design-spec").get_json()
    original = ds.request_package(root, wf.load(root), "P02")
    state["spec"]["tolerances"]["flat_delta_e00"] = 5
    state["spec"]["pages"]["P01"]["elements"][0]["bbox"][0] = .06
    result = c.post("/api/v3/design-spec", json={"revision": state["revision"], "spec": state["spec"]},
                    headers={"X-Mediagen-CSRF": state["csrf"]})
    assert result.status_code == 200
    assert result.get_json()["affected_pages"] == ["P01"]
    assert ds.request_package(root, wf.load(root), "P02") == original


def test_deviation_gate_recomputes_and_binds_output(project):
    import ppt_workflow as wf
    from ppt_knowledge_http import default_spec
    from PIL import Image
    root, _, _, _ = project
    p = wf.load(root)
    p["design"]["atomic_spec"] = default_spec(p)
    image = root / "synthetic-test.png"
    Image.new("RGB", (1280, 720), "white").save(image)
    p["pages"][0]["selected_output"] = {"path": str(image)}
    assert wf.deviation_errors(root, p, ["P01"])
    target = ds.compile_spec(p["design"]["atomic_spec"], "P01")
    measured = {"reviewer": "test-fixture", "evidence": "synthetic fixture, not real visual validation",
                "elements": {e["id"]: {"bbox": e["bbox"], "text": e["text"], "text_verified": True,
                                      "typography_matches": True} for e in target["elements"]},
                "safe_zones_and_occlusion_passed": True, "hard_constraints_passed": True}
    report = ds.audit(target, measured)
    report["output_sha256"] = k.file_hash(image)
    p["design_deviation_reports"] = {"P01": report}
    assert wf.deviation_errors(root, p, ["P01"]) == []
    report["measurements"]["elements"]["title"].pop("bbox")
    assert wf.deviation_errors(root, p, ["P01"])  # status="passed" alone cannot bypass measurements.
    p["design_deviation_reports"]["P01"] = ds.audit(target, measured)
    assert wf.deviation_errors(root, p, ["P01"])  # missing output hash
    p["design"].pop("atomic_spec")
    assert wf.deviation_errors(root, p, ["P01"]) == []  # legacy projects unchanged


def test_atomic_prompt_does_not_emit_competing_legacy_metrics(project):
    import ppt_workflow as wf
    from ppt_knowledge_http import default_spec
    root, _, _, _ = project
    p = wf.load(root)
    p["design"]["typography"]["body"] = "LEGACY_FONT_SENTINEL"
    p["design"]["atomic_spec"] = default_spec(p)
    p["design"]["atomic_spec"]["global"]["tokens"]["primary"]["value"] = "#203C36"
    prompt = wf.prompts(root, p)["P01"]
    assert "LEGACY_FONT_SENTINEL" not in prompt
    assert "#203C36" in prompt


def test_borrow_proposal_keeps_text_and_content_coordinates():
    a = sample()
    a["annotation_hash"] = "c" * 64
    a["source"]["content_box"] = [.1, .1, .8, .8]
    e = k.element("source-title", "title", "原标题", [.2, .2, .4, .08])
    e["observed"]["text"] = k.value("绝不照搬的原文", status="verified", evidence="可见")
    a["elements"] = [e]
    proposal = ds.borrow_proposal(spec(), "P01", "t", a, "source-title", "structure")
    target = proposal["spec"]["pages"]["P01"]["elements"][0]
    assert target["bbox"] == [.125, .125, .5, .1]
    assert target["text"] == "准确文案"
    assert "绝不照搬的原文" not in k.canonical(proposal)
    assert proposal["source"]["send_to_model"] is False
    assert spec()["pages"]["P01"]["elements"][0]["bbox"] == [.1, .1, .5, .1]


def test_borrow_typography_avoids_conflicting_family_and_glyph_size():
    a = sample()
    a["annotation_hash"] = "c" * 64
    e = k.element("source-title", "title", "原标题", [.1, .1, .5, .1])
    e["observed"]["font_class"] = k.value("FT-BRUSH", "enum", "estimated", "可见字型")
    e["observed"]["glyph_height"] = k.value(175, "dimension", "measured", "可见像素高度")
    a["elements"] = [e]
    s = spec()
    s["global"]["tokens"]["title-type"] = {"type": "typography", "value": {
        "class": "FT-SANS", "family": "OriginalTargetFamily", "size_px": 44, "weight": 700,
        "line_height": 1.2, "letter_spacing_px": 0}}
    s["pages"]["P01"]["elements"][0]["style"] = {"typography": {"token": "title-type"}}
    proposal = ds.borrow_proposal(s, "P01", "t", a, "source-title", "typography_appearance")
    t = ds.compile_spec(proposal["spec"], "P01")["elements"][0]["style"]["typography"]["value"]
    assert t["class"] == "FT-BRUSH" and t["family"] is None and t["size_px"] == 44
    assert not any("glyph" in key for key in proposal["changes"])
    with pytest.raises(ValueError, match="color sample"):
        ds.borrow_proposal(s, "P01", "t", a, "source-title", "palette")
    e["kind"] = "brand"
    with pytest.raises(ValueError, match="neutral"):
        ds.borrow_proposal(s, "P01", "t", a, "source-title", "component")


def test_borrow_apply_requires_preview_confirmation_and_current_revision(project):
    import ppt_workflow as wf
    from ppt_knowledge_http import default_spec
    root, _, c, a = project
    p = wf.load(root)
    p["design"]["atomic_spec"] = default_spec(p)
    wf.save(root, p)
    state = c.get("/api/v3/design-spec").get_json()
    headers = {"X-Mediagen-CSRF": state["csrf"]}
    detail = c.get("/api/v3/knowledge/" + a["asset_id"]).get_json()
    response = c.post("/api/v3/knowledge/" + a["asset_id"] + "/borrow", headers=headers, json={
        "revision": state["revision"], "annotation_hash": detail["annotation_hash"],
        "element_id": "t", "purpose": "structure"})
    assert response.status_code == 200
    body = {"revision": response.get_json()["revision"], "request_index": 0,
            "page_id": "P01", "target_element_id": "title"}
    before = wf.load(root)
    response = c.post("/api/v3/knowledge/borrow-preview", headers=headers, json=body)
    assert response.status_code == 200 and response.get_json()["saved"] is False
    assert wf.load(root) == before
    body["proposal_hash"] = response.get_json()["proposal_hash"]
    assert c.post("/api/v3/knowledge/borrow-apply", headers=headers, json=body).status_code == 409
    body["confirmation_reason"] = "Synthetic fixture confirmation, not actual user approval"
    applied = c.post("/api/v3/knowledge/borrow-apply", headers=headers, json=body)
    assert applied.status_code == 200
    assert applied.get_json()["affected_pages"] == ["P01"]
    after = wf.load(root)
    assert after["pages"] == before["pages"] and after["references"] == before["references"]
    assert after["generation_calls"] == before["generation_calls"]
    assert after["knowledge_requests"][0]["status"] == "applied_parameters_only"
    assert c.post("/api/v3/knowledge/borrow-apply", headers=headers, json=body).status_code == 409


@pytest.mark.parametrize("token", [
    {"type": "dimension", "value": "12", "unit": "px"},
    {"type": "dimension", "value": True, "unit": "px"},
    {"type": "dimension", "value": float("nan"), "unit": "px"},
    {"type": "ratio", "value": 4, "unit": "ratio"},
    {"type": "fontWeight", "value": 2000},
    {"type": "gradient", "value": {"kind": "linear", "angle_deg": 90, "stops": [
        {"color": "#ffffff", "position": .8}, {"color": "#000000", "position": .2}]}},
    {"type": "shadow", "value": {"x_px": 0, "y_px": 2, "blur_px": -2, "spread_px": 0, "opacity": .5, "color": "#000000"}},
])
def test_bad_typed_targets_rejected(token):
    a = spec()
    a["global"]["tokens"]["bad"] = token
    with pytest.raises(ValueError):
        ds.compile_spec(a, "P01")


def test_template_hard_protection_survives_overridden_element_list():
    a = spec()
    a["templates"]["content"] = {"elements": [{"id": "brand", "bbox": [.8, .1, .1, .1],
                                               "hard_constraints": {"brand": "protected"}}]}
    a["pages"]["P01"]["template"] = "content"
    a["pages"]["P01"]["elements"][0]["hard_constraints"] = {"brand": "redraw"}
    with pytest.raises(ValueError, match="hard"):
        ds.compile_spec(a, "P01")


def test_typography_style_token_resolution():
    a = spec()
    a["global"]["tokens"]["title"] = {"type": "typography", "value": {
        "class": "FT-SANS", "family": None, "size_px": 42, "weight": 700, "line_height": 1.1, "letter_spacing_px": 0}}
    a["pages"]["P01"]["elements"][0]["style"] = {"typography": {"token": "title"}}
    assert ds.compile_spec(a, "P01")["elements"][0]["style"]["typography"]["value"]["size_px"] == 42


def test_history_rollback_keeps_both_candidates(tmp_path):
    a = sample()
    k.stage(tmp_path, [a])
    first = k.digest(a)
    a["page"]["title"] = "second"
    k.stage(tmp_path, [a])
    second = k.digest(a)
    k.select_version(tmp_path, a["asset_id"], a["source"]["version"], second, first, "restore original candidate")
    assert k.load(tmp_path)[0]["annotation_hash"] == first
    assert len(k.history(tmp_path, a["asset_id"], a["source"]["version"])) == 2
    with pytest.raises(ValueError, match="changed"):
        k.select_version(tmp_path, a["asset_id"], a["source"]["version"], second, first, "stale")


def test_candidate_tampering_is_rejected(tmp_path):
    a = sample()
    path = Path(k.stage(tmp_path, [a])[0])
    a["page"]["title"] = "tampered"
    path.write_text(json.dumps(a), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        k.load(tmp_path)


def test_false_alpha_is_a_hard_filter():
    a = sample()
    a["source"]["alpha"] = True
    assert k.rank([a], filters={"alpha": False})["total"] == 0


def test_preview_and_zip_do_not_change_project(project):
    import hashlib
    import io
    import zipfile
    root, _, c, _ = project
    before = (root / "prompt-pack.json").read_bytes()
    state = c.get("/api/v3/design-spec").get_json()
    response = c.post("/api/v3/design-spec/preview",
                      json={"spec": state["spec"], "revision": state["revision"]},
                      headers={"X-Mediagen-CSRF": state["csrf"]})
    assert response.status_code == 200
    assert response.get_json()["resolved"]["P01"]["elements"][0]["pixels"] == [64, 36, 1152, 86.4]
    zipped = c.get("/api/v3/design-spec/P01/export?lane=samples")
    assert zipped.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zipped.data)) as z:
        manifest = json.loads(z.read("request.json"))
        assert hashlib.sha256(z.read("prompt.txt")).hexdigest() == manifest["prompt_sha256"]
        assert manifest["seed"] is None
    assert (root / "prompt-pack.json").read_bytes() == before


def test_incomplete_candidate_never_reviewed(tmp_path):
    a = sample()
    k.stage(tmp_path, [a])
    receipt = {"reviewer": "Independent-reader", "annotation_hash": k.digest(a), "source_sha256": a["source"]["sha256"],
               "status": "reviewed", "visual_evidence": "fixture evidence only",
               "checks": {x: "passed" for x in ["coverage", "coordinates", "text", "font_evidence", "relations", "contamination", "rights"]}}
    with pytest.raises(ValueError, match="partial"):
        k.record_review(tmp_path, a["asset_id"], a["source"]["version"], receipt)
