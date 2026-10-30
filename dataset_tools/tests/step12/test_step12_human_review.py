import json
from pathlib import Path

from step12.human_review import audit_human_reviews


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def sample(anchor="a"):
    return {"anchor_id": anchor, "builder_version": "0.2.0", "value": 1}


def make_review(tmp_path, *, status="completed", result="pass", stale=False):
    anchor = "a"
    review = tmp_path / anchor
    current = sample(anchor)
    bundled = dict(current)
    if stale:
        bundled["value"] = 2
    overview = review / "sample_overview.png"
    video = review / "synchronized_context.mp4"
    overview.parent.mkdir(parents=True, exist_ok=True)
    overview.write_bytes(b"png")
    video.write_bytes(b"mp4")
    write_json(review / "review_bundle.json", {
        "anchor_id": anchor,
        "sample": bundled,
        "generated_outputs": {"overview_image": str(overview), "video": str(video)},
    })
    write_json(review / "review_decision.json", {
        "anchor_id": anchor,
        "review_status": status,
        "visual_alignment": result,
        "navigation_consistency": result,
        "action_consistency": result,
        "scene_fact_consistency": result,
        "structured_coc_consistency": result,
        "reasoning_consistency": result,
        "issues": [],
        "reviewer_notes": "",
    })
    return {anchor: current}


def test_completed_human_review_passes(tmp_path):
    checks, warnings, errors, artifacts = audit_human_reviews(tmp_path, make_review(tmp_path))
    assert errors == []
    assert warnings == []
    assert checks["human_review_completed_count"] == 1
    assert checks["human_review_pass_count"] == 1
    assert artifacts[0]["decision_sha256"]


def test_pending_human_review_blocks_delivery(tmp_path):
    checks, _, errors, _ = audit_human_reviews(tmp_path, make_review(tmp_path, status="pending"))
    assert checks["human_review_pending_count"] == 1
    assert any(error["code"] == "human_review_pending" for error in errors)


def test_stale_bundle_blocks_delivery(tmp_path):
    checks, _, errors, _ = audit_human_reviews(tmp_path, make_review(tmp_path, stale=True))
    assert checks["human_review_stale_count"] == 1
    assert any(error["code"] == "human_review_stale_bundle" for error in errors)


def test_human_warning_is_nonblocking_warning(tmp_path):
    checks, warnings, errors, _ = audit_human_reviews(tmp_path, make_review(tmp_path, result="warn"))
    assert errors == []
    assert checks["human_review_warning_count"] == 1
    assert warnings[0]["warning_code"] == "human_review_warning"


def test_human_failure_blocks_delivery(tmp_path):
    checks, _, errors, _ = audit_human_reviews(tmp_path, make_review(tmp_path, result="fail"))
    assert checks["human_review_fail_count"] == 1
    assert any(error["code"] == "human_review_failed" for error in errors)
