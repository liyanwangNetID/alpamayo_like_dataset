from __future__ import annotations

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
