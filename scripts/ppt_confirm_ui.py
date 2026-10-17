#!/usr/bin/env python3
"""Image-PPT adapter for the MIT ppt-master confirmation UI.

Retains upstream UI controls, previews and two-stage receipt semantics;
replaces native template-install/SVG-production routes with the image job.
Loopback only; same-origin + per-session CSRF; no model calls.
"""
from __future__ import annotations

import argparse
import secrets
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.serving import make_server

import ppt_workflow as wf

STATIC = Path(__file__).resolve().parent / "vendor/ppt_master/static"


def apply_choices(p, payload, stage):
    mg = payload.get("mediagen_choices", {})
    if stage == "stage1":
        for key in ("audience", "communication_intent", "audience_outcome", "core_message",
                    "delivery_context", "artifact_afterlife", "content_divergence"):
            if key in payload:
                p["communication"][key] = str(payload[key])
        if payload.get("primary_language"):
            p["primary_language"] = payload["primary_language"]
        if payload.get("canvas"):
            canvases = {"ppt169": ("2048x1152", "1280x720"), "ppt43": ("1536x1152", "1024x768")}
            if payload["canvas"] not in canvases:
                raise ValueError("prepare a supported canvas with the agent before confirmation (16:9 or 4:3)")
            p["generation_contract"]["size"], p["design"]["baseline_canvas"] = canvases[payload["canvas"]]
        if isinstance(mg.get("communication"), dict):
            p["communication"].update(mg["communication"])
        if isinstance(mg.get("pages"), list):
            if [x.get("page_id") for x in mg["pages"]] != [x["page_id"] for x in p["pages"]]:
                raise ValueError("page IDs/order must remain stable; ask the agent to repaginate")
            for current, updated in zip(p["pages"], mg["pages"]):
                current["logic"] = updated["logic"]
                current["page_text"] = updated.get("page_text", current.get("page_text", ""))
    else:
        p["design_choice_recorded"] = True
        if payload.get("page_count") and int(payload["page_count"]) != len(p["pages"]):
            raise ValueError("page count changed: ask the agent to prepare a matching storyboard before confirmation")
        if payload.get("delivery_purpose"):
            # Reading mode affects the content budget: stage1 must be reviewed again if it changes.
            p["communication"]["reading_mode"] = payload["delivery_purpose"]
        if payload.get("mode"):
            p["communication"]["organization"] = payload.get("mode_behavior") or payload["mode"]
        if payload.get("visual_style"):
            p["design"]["visual_style"] = payload["visual_style"]
        if payload.get("visual_style_behavior"):
            p["design"]["visual_style_behavior"] = payload["visual_style_behavior"]
        if payload.get("color", {}).get("palette"):
            colors = payload["color"]["palette"]
            p["design"]["palette"].update(colors)
            if colors.get("body_text"):
                p["design"]["palette"]["text"] = colors["body_text"]
        typ = payload.get("typography", {})
        if typ:
            p["design"]["typography"].update({
                "heading": typ.get("heading", {}).get("primary", typ.get("heading", {}).get("cjk", p["design"]["typography"]["heading"])),
                "body": typ.get("body", {}).get("primary", typ.get("body", {}).get("cjk", p["design"]["typography"]["body"])),
                "numbers": typ.get("body", {}).get("english", typ.get("body", {}).get("latin", p["design"]["typography"]["numbers"])),
                "sizes": {**p["design"]["typography"]["sizes"], **typ.get("sizes", {}),
                          "body": typ.get("body_size", p["design"]["typography"]["sizes"]["body"])},
            })
        if payload.get("icons"):
            p["design"]["icons"] = payload["icons"]
        strategy = payload.get("image_strategy", {})
        if strategy:
            p["design"]["material"] = strategy.get("behavior") or strategy.get("rendering", p["design"]["material"])
        for field in ("display", "human_policy", "grid", "material"):
            if field in mg:
                if field == "display":
                    p["design"]["typography"]["display"] = mg[field]
                else:
                    p["design"][field] = mg[field]
        if "notes_policy" in mg:
            p["notes_policy"] = mg["notes_policy"]
        if "transition" in mg:
            p["transition"] = mg["transition"]
        if isinstance(mg.get("pages"), list):
            if [pg.get("page_id") for pg in mg["pages"]] != [pg["page_id"] for pg in p["pages"]]:
                raise ValueError("page IDs/order must remain stable for page-specific motion")
            for current, submitted in zip(p["pages"], mg["pages"]):
                if "transition" in submitted:
                    current["transition"] = submitted["transition"]
                else:
                    current.pop("transition", None)
        if "references" in mg:
            if not isinstance(mg["references"], list):
                raise ValueError("references must be a list")
            known = {r["id"]: r for r in p["references"]}
            merged = []
            for submitted in mg["references"]:
                wf.safe_id(submitted["id"])
                original = known.get(submitted["id"])
                if original:
                    if submitted.get("path") != original.get("path"):
                        raise ValueError("registered material paths cannot be changed in the browser; ask the agent")
                    if original.get("role") == "evidence" and submitted.get("role") != "evidence":
                        raise ValueError("protected evidence cannot be relabeled as style")
                    record = {**original, **submitted}
                    if original.get("role") == "evidence":
                        record.update(upload_allowed=False, send_to_model=False)
                else:
                    record = dict(submitted)
                    # Local paths typed into the page are requests, not arbitrary file-read/upload permissions.
                    if record.get("path"):
                        record["requested_path"] = record.pop("path")
                        record["registration"] = "pending_agent_inspection"
                        record["requested_upload_allowed"] = bool(record.get("upload_allowed"))
                        record.update(upload_allowed=False, send_to_model=False)
                merged.append(record)
            p["references"] = merged
    return p


def create_app(job, library=None):
    root = Path(job).resolve()
    app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
    token = secrets.token_hex(24)

    @app.before_request
    def security():
        if request.host.split(":")[0] not in ("localhost", "127.0.0.1"):
            return jsonify(error="loopback Host required"), 403
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            return jsonify(error="same-origin required"), 403
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-Mediagen-CSRF") != token:
            return jsonify(error="CSRF token required"), 403

    @app.after_request
    def cache(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob: https://upload.wikimedia.org https://thumb.wikimedia.org; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        return response

    @app.errorhandler(ValueError)
    def invalid(exc):
        return jsonify(error=str(exc)), 409

    @app.route("/")
    def index():
        return send_from_directory(Path(__file__).parent / "static/ppt-workbench", "index.html")

    @app.route("/workbench/<path:filename>")
    def workbench_static(filename):
        return send_from_directory(Path(__file__).parent / "static/ppt-workbench", filename)

    @app.route("/legacy")
    def legacy():
        return send_from_directory(STATIC, "index.html")

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    @app.route("/api/health")
    def health():
        return jsonify(status="ready", inference_performed=False)

    @app.route("/api/session")
    def session():
        p = wf.load(root)
        ready = wf.valid(p["approvals"].get("stage1"), wf.subject(root, p, "stage1"))
        return jsonify(stage=2 if ready else 1, recommendation_stage_number=2 if ready else 1,
                       status="waiting_user",
                       csrf=token, adapter="mediagen", source_hash=wf.design_hash(root, p))

    @app.route("/api/catalogs")
    def catalogs():
        c = wf.read(STATIC / "catalogs.json")
        # Image-production route is fixed; native provider/auto-agent controls are not consent.
        c["image_usage"] = [{"id": "ai", "label_zh": "整页生图（中文字在图中）",
                             "label_en": "Full-page image with baked text"}]
        c["canvas"] = [x for x in c["canvas"] if x["id"] in ("ppt169", "ppt43")]
        return jsonify(c)

    @app.route("/api/icon-previews")
    @app.route("/api/ai-image-comparison")
    def previews():
        return jsonify({})

    @app.route("/api/recommendations")
    def recommendations():
        p = wf.load(root)
        stage = 2 if wf.valid(p["approvals"].get("stage1"), wf.subject(root, p, "stage1")) else 1
        return jsonify(wf.recommendations(root, p, stage))

    @app.route("/api/image/<key>")
    def image(key):
        p = wf.load(root)
        if key.startswith("ref-"):
            selected = next((r for r in p["references"] if r["id"] == key[4:]), {})
        else:
            selected = next((pg.get("selected_output") or {} for pg in p["pages"] if pg["page_id"] == key), {})
        if not selected.get("path"):
            return jsonify(error="registered image not found"), 404
        path = wf.local(root, selected["path"])
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
            return jsonify(error="image-only preview"), 400
        # Only already registered paths are eligible; new browser paths are never stored as `path`.
        # Make a managed preview copy rather than serving an arbitrary path outside the job.
        if not path.is_relative_to(root):
            if path.suffix.lower() != ".svg":
                from PIL import Image
                with Image.open(path) as im:
                    im.verify()
            dest = root / "confirm_ui/preview-assets" / (wf.file_sha(path) + path.suffix.lower())
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copyfile(path, dest)
            path = dest
        return send_file(path)

    @app.route("/api/confirm", methods=["POST"])
    def confirm():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValueError("JSON object required")
        p = wf.load(root)
        if body.get("_source_hash") != wf.design_hash(root, p):
            raise ValueError("proposal changed while editing; reload before confirming")
        stage = body.get("stage")
        if stage not in ("stage1", "stage2"):
            raise ValueError("explicit stage1 or stage2 required")
        if stage == "stage2" and not wf.valid(p["approvals"].get("stage1"), wf.subject(root, p, "stage1")):
            raise ValueError("stage1 confirmation missing")
        updated = apply_choices(p, body, stage)
        inspection = wf.check(root, updated)
        if not inspection["ok"]:
            raise ValueError("; ".join(inspection["errors"]))
        # Never persist a draft that invalidates stage1 while saying stage2 passed.
        if stage == "stage2" and not wf.valid(updated["approvals"].get("stage1"),
                                             wf.subject(root, updated, "stage1")):
            wf.save(root, updated)
            raise ValueError("story/reading context changed and the revised draft was saved; reload and confirm "
                             "the communication stage again before approving design")
        receipt = wf.confirm(root, updated, stage, "用户在网页点击确认", "web")
        wf.write(root / "confirm_ui" / f"receipt.{stage}.json", receipt)
        return jsonify(receipt)

    @app.route("/api/sample-confirm", methods=["POST"])
    def samples():
        p = wf.load(root)
        body = request.get_json(silent=True) or {}
        expected = wf.subject(root, p, "samples")
        if body.get("subject_hash") != expected:
            raise ValueError("sample images changed; reload before approving")
        return jsonify(wf.confirm(root, p, "samples", "用户在网页确认实际样张", "web", expected))

    @app.route("/api/feedback", methods=["POST"])
    def feedback():
        p = wf.load(root)
        body = request.get_json(silent=True) or {}
        if not body.get("comment", "").strip():
            raise ValueError("feedback comment is empty")
        if body.get("scope", "this_project") not in ("this_project", "similar_projects", "all_ppt"):
            raise ValueError("unknown feedback scope")
        result = wf.record_feedback(root, p, {"source": "user_web", "comment": body["comment"],
                                            "scope": body.get("scope", "this_project"),
                                            **{k: body[k] for k in ("preferences", "issues", "lessons") if k in body}},
                                    root / "fixture-library" if p.get("test_fixture") else wf.LIBRARY)
        return jsonify(result)

    @app.route("/api/shutdown", methods=["POST"])
    def shutdown():
        # Keep the preview open after design confirmation: samples and feedback follow.
        return jsonify(status="kept_open_for_samples", note="stop the owned UI process when finished")

    import ppt_workbench
    ppt_workbench.register(app, root, token, library or wf.LIBRARY)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    server = make_server("127.0.0.1", args.port, create_app(args.job))
    print(f"http://127.0.0.1:{server.server_port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
