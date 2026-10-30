#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HUMAN_REVIEW = r'''from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from step10.contract import canonical_sha256

REVIEW_FIELDS = (
    "visual_alignment",
    "navigation_consistency",
    "action_consistency",
    "scene_fact_consistency",
    "structured_coc_consistency",
    "reasoning_consistency",
)
VALID_RESULTS = frozenset({"pass", "warn", "fail", "not_applicable"})


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def audit_human_reviews(
    review_root: Path,
    sample_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    counters = Counter()

    bundle_paths = sorted(review_root.glob("*/review_bundle.json")) if review_root.is_dir() else []
    counters["bundle_count"] = len(bundle_paths)
    if not bundle_paths:
        errors.append({"code": "human_review_missing", "review_root": str(review_root)})

    seen_anchors: set[str] = set()
    for bundle_path in bundle_paths:
        review_dir = bundle_path.parent
        decision_path = review_dir / "review_decision.json"
        counters["decision_count"] += int(decision_path.is_file())
        try:
            bundle = _load_object(bundle_path)
        except Exception as exc:
            counters["invalid_count"] += 1
            errors.append({"code": "human_review_bundle_invalid", "path": str(bundle_path), "message": str(exc)})
            continue

        anchor = str(bundle.get("anchor_id", ""))
        sample = bundle.get("sample")
        current = sample_by_id.get(anchor)
        entry: dict[str, Any] = {
            "anchor_id": anchor,
            "review_directory": str(review_dir),
            "bundle_path": str(bundle_path),
            "bundle_sha256": file_sha256(bundle_path),
            "decision_path": str(decision_path),
        }
        artifacts.append(entry)

        if not anchor or anchor in seen_anchors:
            counters["invalid_count"] += 1
            errors.append({"code": "human_review_duplicate_or_empty_anchor", "anchor_id": anchor, "path": str(bundle_path)})
        seen_anchors.add(anchor)

        if current is None:
            counters["anchor_missing_count"] += 1
            errors.append({"code": "human_review_anchor_missing", "anchor_id": anchor})
            continue
        if not isinstance(sample, dict) or canonical_sha256(sample) != canonical_sha256(current):
            counters["stale_count"] += 1
            errors.append({"code": "human_review_stale_bundle", "anchor_id": anchor})

        generated = bundle.get("generated_outputs", {})
        for name in ("overview_image", "video"):
            raw_path = generated.get(name) if isinstance(generated, dict) else None
            if raw_path is None and name == "video":
                continue
            path = Path(str(raw_path)) if raw_path else None
            if path is None or not path.is_file():
                counters["missing_artifact_count"] += 1
                errors.append({"code": "human_review_artifact_missing", "anchor_id": anchor, "artifact": name, "path": raw_path})
            else:
                entry[f"{name}_path"] = str(path)
                entry[f"{name}_sha256"] = file_sha256(path)

        if not decision_path.is_file():
            counters["pending_count"] += 1
            errors.append({"code": "human_review_decision_missing", "anchor_id": anchor})
            continue
        entry["decision_sha256"] = file_sha256(decision_path)
        try:
            decision = _load_object(decision_path)
        except Exception as exc:
            counters["invalid_count"] += 1
            errors.append({"code": "human_review_decision_invalid", "anchor_id": anchor, "message": str(exc)})
            continue
        if str(decision.get("anchor_id", "")) != anchor:
            counters["invalid_count"] += 1
            errors.append({"code": "human_review_decision_anchor_mismatch", "anchor_id": anchor})
            continue
        if decision.get("review_status") != "completed":
            counters["pending_count"] += 1
            errors.append({"code": "human_review_pending", "anchor_id": anchor})
            continue

        results = {field: decision.get(field) for field in REVIEW_FIELDS}
        invalid = {field: value for field, value in results.items() if value not in VALID_RESULTS}
        if invalid:
            counters["invalid_count"] += 1
            errors.append({"code": "human_review_result_invalid", "anchor_id": anchor, "values": invalid})
            continue

        counters["completed_count"] += 1
        if "fail" in results.values():
            counters["fail_count"] += 1
            errors.append({"code": "human_review_failed", "anchor_id": anchor, "results": results, "issues": decision.get("issues", [])})
        elif "warn" in results.values():
            counters["warning_count"] += 1
            warnings.append({"warning_code": "human_review_warning", "anchor_id": anchor, "results": results, "issues": decision.get("issues", [])})
        else:
            counters["pass_count"] += 1

    checks = {
        "human_review_bundle_count": counters["bundle_count"],
        "human_review_decision_count": counters["decision_count"],
        "human_review_completed_count": counters["completed_count"],
        "human_review_pending_count": counters["pending_count"],
        "human_review_pass_count": counters["pass_count"],
        "human_review_warning_count": counters["warning_count"],
        "human_review_fail_count": counters["fail_count"],
        "human_review_stale_count": counters["stale_count"],
        "human_review_anchor_missing_count": counters["anchor_missing_count"],
        "human_review_invalid_count": counters["invalid_count"],
        "human_review_missing_artifact_count": counters["missing_artifact_count"],
    }
    return checks, warnings, errors, artifacts
'''

TEST_HUMAN_REVIEW = r'''import json
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
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_audit(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "from step12.human_review import audit_human_reviews" in text:
        print(f"already patched: {path}")
        return

    text = replace_once(
        text,
        "from step12.schema import final_audit_schema, write_schema\n",
        "from step12.schema import final_audit_schema, write_schema\nfrom step12.human_review import audit_human_reviews\n",
        "human review import",
    )
    text = replace_once(
        text,
        'SCHEMA = SCHEMA_ROOT / "final_dataset_audit_schema_v0.1-draft.json"\n',
        'SCHEMA = SCHEMA_ROOT / "final_dataset_audit_schema_v0.1-draft.json"\nREVIEW_ROOT = REPORT_ROOT / "step12_review"\n',
        "review root",
    )
    marker = '    statistics = {\n'
    insertion = '''    human_checks, human_warnings, human_errors, human_artifacts = audit_human_reviews(REVIEW_ROOT, sample_by_id)\n    checks.update(human_checks)\n    warnings.extend(human_warnings)\n    errors.extend(human_errors)\n\n'''
    text = replace_once(text, marker, insertion + marker, "human audit call")
    text = replace_once(
        text,
        '"delivery_summary": str(DELIVERY)}}\n',
        '"delivery_summary": str(DELIVERY), "human_reviews": human_artifacts}}\n',
        "audit artifacts",
    )
    text = replace_once(
        text,
        '- Audit errors: **{len(errors)}**\\n\\nStep 9 reasoning remains non-authoritative',
        '- Audit errors: **{len(errors)}**\\n- Human reviews completed / pass / warn / fail: **{human_checks[\'human_review_completed_count\']} / {human_checks[\'human_review_pass_count\']} / {human_checks[\'human_review_warning_count\']} / {human_checks[\'human_review_fail_count\']}**\\n- Human reviews pending / stale: **{human_checks[\'human_review_pending_count\']} / {human_checks[\'human_review_stale_count\']}**\\n\\nStep 9 reasoning remains non-authoritative',
        "delivery human summary",
    )
    text = replace_once(
        text,
        '"human_review_directory": str(REPORT_ROOT / "step12_review")}\n',
        '"human_review_directory": str(REVIEW_ROOT), "human_review_checks": human_checks, "human_review_artifacts": human_artifacts}\n',
        "contract human review",
    )
    path.write_text(text, encoding="utf-8")
    print(f"patched: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Complete Step 12 human-review integration and tests.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    repo = args.repo.resolve()
    step12 = repo / "step12"
    tests = repo / "tests" / "step12"
    if not (step12 / "audit_dataset.py").is_file():
        raise FileNotFoundError(f"not a dataset_tools repo: {repo}")
    (step12 / "human_review.py").write_text(HUMAN_REVIEW, encoding="utf-8")
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_step12_human_review.py").write_text(TEST_HUMAN_REVIEW, encoding="utf-8")
    patch_audit(step12 / "audit_dataset.py")
    print("wrote:", step12 / "human_review.py")
    print("wrote:", tests / "test_step12_human_review.py")
    print("PASS: Step 12 final-closure source patch applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
