#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from project_paths import ALPASIM_DATA_ROOT, MANIFEST_ROOT, REPORT_ROOT, SCHEMA_ROOT
from step10.contract import canonical_sha256
from step10.schema import sample_manifest_schema
from step11.schema import dataset_split_schema
from step12.schema import final_audit_schema, write_schema
from step12.human_review import audit_human_reviews

SAMPLE = MANIFEST_ROOT / "sample_manifest_v0.1.jsonl"
SAMPLE_CONTRACT = MANIFEST_ROOT / "sample_manifest_contract_v0.1.json"
SPLIT = MANIFEST_ROOT / "dataset_split_v0.1.jsonl"
SPLIT_CONTRACT = MANIFEST_ROOT / "dataset_split_contract_v0.1.json"
AUDIT = REPORT_ROOT / "final_dataset_audit_v0.1.json"
STATS = REPORT_ROOT / "final_dataset_statistics_v0.1.json"
DELIVERY = REPORT_ROOT / "final_dataset_delivery_summary_v0.1.md"
CONTRACT = MANIFEST_ROOT / "final_dataset_contract_v0.1.json"
SCHEMA = SCHEMA_ROOT / "final_dataset_audit_schema_v0.1-draft.json"
REVIEW_ROOT = REPORT_ROOT / "step12_review"

RARE = {
    "lateral": ("change_lane_left", "change_lane_right", "turn_left", "turn_right"),
    "longitudinal": ("stop",),
    "navigation": ("left", "right"),
    "road_context": ("intersection",),
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: Path, text: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing output: {path}; use --force")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def dimensions(sample: dict[str, Any]) -> dict[str, str]:
    return {
        "lateral": sample["supervision"]["driving_decision"]["joint_action"]["lateral"],
        "longitudinal": sample["supervision"]["driving_decision"]["joint_action"]["longitudinal"],
        "navigation": sample["model_input"]["navigation"]["navigation"]["action"],
        "road_context": sample["supervision"]["scene_facts"]["road_context"]["type"],
        "meta_action_quality": sample["quality"]["meta_action"],
        "navigation_quality": sample["quality"]["navigation"],
        "scene_fact_quality": sample["quality"]["scene_facts"],
        "structured_coc_quality": sample["quality"]["structured_causality"],
        "reasoning_quality": sample["quality"]["reasoning"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    samples = read_jsonl(SAMPLE)
    splits = read_jsonl(SPLIT)
    sample_contract = json.loads(SAMPLE_CONTRACT.read_text(encoding="utf-8"))
    split_contract = json.loads(SPLIT_CONTRACT.read_text(encoding="utf-8"))
    errors, warnings = [], []
    checks: dict[str, Any] = {}

    sample_validator = Draft202012Validator(sample_manifest_schema())
    split_validator = Draft202012Validator(dataset_split_schema())
    sample_by_id = {}
    image_count = history_count = absolute_paths = missing_images = 0
    leakage_terms = ("static_occupancy", "ground_truth_future", "planner_output", "complete_recording_ground_truth")
    leakage_hits = Counter()
    provenance_mismatches = Counter()
    finite_failures = 0
    for row in samples:
        anchor = row["anchor_id"]
        if anchor in sample_by_id:
            errors.append({"code": "duplicate_sample_anchor", "anchor_id": anchor})
        sample_by_id[anchor] = row
        validation = list(sample_validator.iter_errors(row))
        if validation:
            errors.append({"code": "sample_schema_error", "anchor_id": anchor, "message": validation[0].message})
        serialized_input = json.dumps(row["model_input"], ensure_ascii=False)
        for term in leakage_terms:
            if term in serialized_input:
                leakage_hits[term] += 1
        visual = row["model_input"]["visual"]
        for camera in visual["camera_names"]:
            frames = visual["frames"][camera]
            if len(frames) != 3:
                errors.append({"code": "camera_frame_count", "anchor_id": anchor, "camera": camera, "count": len(frames)})
            for frame in frames:
                relative = Path(frame["image_path"])
                absolute_paths += int(relative.is_absolute() or ".." in relative.parts)
                missing_images += int(not (ALPASIM_DATA_ROOT / relative).is_file())
                image_count += 1
        points = row["model_input"]["ego_history"]["points"]
        history_count += len(points)
        for point in points:
            for value in point.values():
                if isinstance(value, float) and not math.isfinite(value):
                    finite_failures += 1
        prov = row["provenance"]
        embedded = {
            "keyframe_record_sha256": {"anchor_id": row["anchor_id"], "clip_id": row["clip_id"], "anchor_ns": row["anchor_ns"], **row["selection"]},
            "meta_action_record_sha256": {"anchor_id": row["anchor_id"], "clip_id": row["clip_id"], "anchor_ns": row["anchor_ns"], **row["supervision"]["driving_decision"]},
            "navigation_record_sha256": {"anchor_id": row["anchor_id"], "clip_id": row["clip_id"], "anchor_ns": row["anchor_ns"], **row["model_input"]["navigation"]},
            "scene_fact_record_sha256": {"anchor_id": row["anchor_id"], "clip_id": row["clip_id"], "anchor_ns": row["anchor_ns"], **row["supervision"]["scene_facts"]},
            "structured_causality_record_sha256": {"anchor_id": row["anchor_id"], "clip_id": row["clip_id"], "anchor_ns": row["anchor_ns"], **row["supervision"]["structured_causality"]},
        }
        reasoning = row["optional_auxiliary"]["reasoning"]["record"]
        if reasoning is not None:
            embedded["reasoning_record_sha256"] = {"anchor_id": row["anchor_id"], "clip_id": row["clip_id"], "anchor_ns": row["anchor_ns"], **reasoning}
        for key, source in embedded.items():
            if canonical_sha256(source) != prov[key]:
                provenance_mismatches[key] += 1

    split_by_id, clip_splits = {}, defaultdict(set)
    for row in splits:
        anchor = row["anchor_id"]
        if anchor in split_by_id:
            errors.append({"code": "duplicate_split_anchor", "anchor_id": anchor})
        split_by_id[anchor] = row["split"]
        clip_splits[row["clip_id"]].add(row["split"])
        validation = list(split_validator.iter_errors(row))
        if validation:
            errors.append({"code": "split_schema_error", "anchor_id": anchor, "message": validation[0].message})
    cross = {clip: sorted(values) for clip, values in clip_splits.items() if len(values) != 1}
    if set(sample_by_id) != set(split_by_id):
        errors.append({"code": "sample_split_anchor_mismatch", "missing": len(set(sample_by_id)-set(split_by_id)), "extra": len(set(split_by_id)-set(sample_by_id))})
    if cross:
        errors.append({"code": "clip_cross_split", "count": len(cross), "examples": dict(list(cross.items())[:10])})

    split_counts = Counter(split_by_id.values())
    stats = {name: {"sample_count": split_counts[name], "clip_count": sum(values == {name} for values in clip_splits.values()), "dimensions": defaultdict(Counter), "selection_sources": Counter()} for name in ("train", "validation", "test")}
    global_dims = defaultdict(Counter)
    for anchor, sample in sample_by_id.items():
        split = split_by_id[anchor]
        for dimension, value in dimensions(sample).items():
            stats[split]["dimensions"][dimension][value] += 1
            global_dims[dimension][value] += 1
        for source in sample["selection"]["selection_sources"]:
            stats[split]["selection_sources"][source] += 1
    for dimension, classes in RARE.items():
        for label in classes:
            total = global_dims[dimension][label]
            for split in ("validation", "test"):
                count = stats[split]["dimensions"][dimension][label]
                if total and count == 0:
                    warnings.append({"warning_code": "rare_class_missing_from_split", "dimension": dimension, "class": label, "global_count": total, "split": split, "split_count": 0})

    checks.update({
        "sample_manifest_record_count": len(samples), "split_record_count": len(splits),
        "sample_contract_hash_valid": sha256(SAMPLE) == sample_contract["output_sha256"],
        "split_contract_hash_valid": sha256(SPLIT) == split_contract["output_sha256"],
        "image_reference_count": image_count, "missing_image_count": missing_images,
        "absolute_or_escaping_image_path_count": absolute_paths,
        "ego_history_point_count": history_count, "nonfinite_ego_value_count": finite_failures,
        "model_input_leakage_hits": dict(leakage_hits),
        "provenance_mismatch_counts": dict(provenance_mismatches),
        "clip_cross_split_count": len(cross),
    })
    if not checks["sample_contract_hash_valid"]:
        errors.append({"code": "sample_contract_hash_mismatch"})
    if not checks["split_contract_hash_valid"]:
        errors.append({"code": "split_contract_hash_mismatch"})
    if missing_images or absolute_paths or finite_failures or leakage_hits or provenance_mismatches:
        errors.append({"code": "sample_content_audit_failure", "missing_images": missing_images, "absolute_paths": absolute_paths, "nonfinite_values": finite_failures, "leakage_hits": dict(leakage_hits), "provenance_mismatches": dict(provenance_mismatches)})

    human_checks, human_warnings, human_errors, human_artifacts = audit_human_reviews(REVIEW_ROOT, sample_by_id)
    checks.update(human_checks)
    warnings.extend(human_warnings)
    errors.extend(human_errors)

    statistics = {
        "statistics_version": "0.1", "record_count": len(samples), "clip_count": len(clip_splits),
        "split_counts": dict(split_counts),
        "global_dimensions": {key: dict(sorted(value.items())) for key, value in global_dims.items()},
        "splits": {name: {"sample_count": value["sample_count"], "clip_count": value["clip_count"], "dimensions": {key: dict(sorted(counter.items())) for key, counter in value["dimensions"].items()}, "selection_sources": dict(sorted(value["selection_sources"].items()))} for name, value in stats.items()},
    }
    status = "FAIL" if errors else "PASS_WITH_WARNINGS" if warnings else "PASS"
    write_schema(SCHEMA)
    audit = {"audit_version": "0.1", "status": status, "record_count": len(samples), "clip_count": len(clip_splits), "checks": checks, "warnings": warnings, "errors": errors, "artifacts": {"sample_manifest": str(SAMPLE), "dataset_split": str(SPLIT), "statistics": str(STATS), "delivery_summary": str(DELIVERY), "human_reviews": human_artifacts}}
    Draft202012Validator(final_audit_schema()).validate(audit)
    delivery = f"""# Final Dataset Delivery Summary v0.1\n\n- Audit status: **{status}**\n- Samples: **{len(samples)}**\n- Clips: **{len(clip_splits)}**\n- Train / validation / test: **{split_counts['train']} / {split_counts['validation']} / {split_counts['test']}**\n- Image references: **{image_count}**, missing: **{missing_images}**\n- Ego-history points: **{history_count}**\n- Clip cross-split count: **{len(cross)}**\n- Audit warnings: **{len(warnings)}**\n- Audit errors: **{len(errors)}**\n- Human reviews completed / pass / warn / fail: **{human_checks['human_review_completed_count']} / {human_checks['human_review_pass_count']} / {human_checks['human_review_warning_count']} / {human_checks['human_review_fail_count']}**\n- Human reviews pending / stale: **{human_checks['human_review_pending_count']} / {human_checks['human_review_stale_count']}**\n\nStep 9 reasoning remains non-authoritative and excluded from the default training view.\n"""
    contract = {"contract_version": "0.1", "producer_step": 12, "status": status, "record_count": len(samples), "clip_count": len(clip_splits), "sample_manifest_sha256": sha256(SAMPLE), "dataset_split_sha256": sha256(SPLIT), "audit_path": str(AUDIT), "audit_sha256": None, "statistics_path": str(STATS), "statistics_sha256": None, "delivery_summary_path": str(DELIVERY), "delivery_summary_sha256": None, "audit_schema_path": str(SCHEMA), "audit_schema_sha256": sha256(SCHEMA), "machine_audit_errors": len(errors), "machine_audit_warnings": len(warnings), "human_review_directory": str(REVIEW_ROOT), "human_review_checks": human_checks, "human_review_artifacts": human_artifacts}
    atomic_write(STATS, json.dumps(statistics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.force)
    atomic_write(DELIVERY, delivery, args.force)
    atomic_write(AUDIT, json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.force)
    contract["audit_sha256"] = sha256(AUDIT); contract["statistics_sha256"] = sha256(STATS); contract["delivery_summary_sha256"] = sha256(DELIVERY)
    atomic_write(CONTRACT, json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.force)
    print("Step 12 final dataset audit")
    print("status:", status); print("records:", len(samples)); print("clips:", len(clip_splits)); print("warnings:", len(warnings)); print("errors:", len(errors))
    for warning in warnings: print("WARNING:", warning)
    print("audit:", AUDIT); print("statistics:", STATS); print("delivery summary:", DELIVERY); print("contract:", CONTRACT)
    if errors: raise SystemExit(2)
    print("PASS: Step 12 machine audit completed.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
