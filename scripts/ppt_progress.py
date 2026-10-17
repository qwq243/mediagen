"""Workflow navigation state. Browsing history never authorizes production."""
import argparse
import json
from pathlib import Path
import ppt_workflow as wf

STAGES = ("stage1", "stage2", "samples", "deck", "delivery", "feedback")
LABELS = ("沟通与参考", "完整方案", "逐页创作", "整套统稿", "讲稿与交付", "使用反馈")


def state(root, p):
    def ok(phase, kind="audits", page=None):
        try:
            key = phase + ":" + page if page else phase
            return wf.valid(p.get(kind, {}).get(key), wf.subject(root, p, phase, page))
        except (KeyError, ValueError, StopIteration):
            return False
    communication_review = wf.valid(p.get("stage_reviews", {}).get("stage1"), wf.subject(root, p, "stage1"))
    done = {
        "stage1": ok("stage1", "approvals") and communication_review,
        "stage2": ok("stage2", "approvals") and ok("content") and ok("prompts"),
        "samples": ok("samples", "approvals"),
        "deck": bool(p["pages"]) and ok("deck") and all(ok("visual", page=x["page_id"]) for x in p["pages"]),
        "delivery": bool(p.get("deliveries") or p.get("deliverables")) and ok("deck") and (not p["notes_policy"]["enabled"] or ok("notes")),
        "feedback": bool(p.get("feedback")),
    }
    # Evidence is version-scoped. Past receipts let users revisit, not bypass prerequisites.
    reached = {
        "stage1": True, "stage2": bool(p.get("approvals", {}).get("stage2")),
        "samples": any(x.get("selected_output") or x.get("output_candidates") for x in p["pages"]),
        "deck": bool(p.get("approvals", {}).get("samples")),
        "delivery": bool(p.get("audits", {}).get("deck") or p.get("deliveries") or p.get("deliverables")),
        "feedback": bool(p.get("feedback")),
    }
    pending = [x for x in p.get("revision_requests", []) if x["status"] in ("draft", "submitted")]
    rows, previous = [], True
    for index, key in enumerate(STAGES):
        related = any(STAGES.index(x.get("stage", "stage1")) <= index for x in pending
                      if x.get("stage") in STAGES)
        complete = bool(previous and done[key] and not related)
        # Single-page sample alignment may start while the full proposal is a draft.
        # This is navigation only; wf.confirm/check still enforce production gates.
        preview_only = key in ("samples", "deck") and not previous and rows[0]["complete"]
        accessible = previous or reached[key] or preview_only
        reason = "" if previous else "前序阶段已变更或尚未完成，请先回到 Agent 对齐。"
        if not accessible:
            status, reason = "locked", "先完成前一阶段的用户确认和 Agent 审核。"
        elif complete:
            status = "completed"
        elif preview_only:
            status, reason = "preview", ("可先逐页对齐；制作与确认仍需通过审核。" if key == "samples"
                                        else "可查看整套进度；浏览不代表整套通过审核。")
        elif not previous or related:
            status = "revision_required"
        elif key in ("stage1", "stage2") and ok(key, "approvals"):
            status, reason = "waiting_agent", "用户已确认；等待 Agent 独立审核。请回到 Codex，不会自动启动下一阶段。"
        else:
            status = "active"
        rows.append({"id": key, "label": LABELS[index], "status": status, "accessible": accessible,
                     "complete": complete, "reason": reason, "preview_only": bool(preview_only)})
        previous = complete
    return rows


def require_stage(root, p, stage):
    item = next((x for x in state(root, p) if x["id"] == stage), None)
    if not item or not item["accessible"]:
        raise ValueError("该阶段尚未解锁；请先与 Agent 完成前序阶段。")


def review_communication(root, p, report):
    if not wf.valid(p["approvals"].get("stage1"), wf.subject(root, p, "stage1")):
        raise ValueError("用户须先确认当前沟通版本")
    if report.get("subject_hash") != wf.subject(root, p, "stage1"):
        raise ValueError("review version is stale")
    if report.get("status") not in ("passed", "failed", "pending"):
        raise ValueError("review status required")
    if not report.get("reviewer") or not report.get("evidence") or not report.get("independent"):
        raise ValueError("独立复核人和具体依据必填")
    if report["status"] == "passed" and any(x.get("severity") in ("major", "blocker") and x.get("resolution") != "fixed"
                                           for x in report.get("findings", [])):
        raise ValueError("blocking review findings remain")
    p.setdefault("stage_reviews", {})["stage1"] = {**report, "at": wf.now()}
    wf.save(root, p)
    return state(root, p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job", required=True, type=Path)
    ap.add_argument("--review", type=Path, help="沟通阶段独立审核报告；没有此项时只查看")
    a = ap.parse_args(); p = wf.load(a.job)
    result = review_communication(a.job, p, wf.read(a.review)) if a.review else state(a.job, p)
    print(json.dumps(result, ensure_ascii=False, indent=2))
