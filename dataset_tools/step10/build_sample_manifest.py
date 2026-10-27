#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from project_paths import ALPASIM_DATA_ROOT, ANNOTATION_ROOT, MANIFEST_ROOT, REPORT_ROOT, SCHEMA_ROOT
from step2.clip_reader import CAMERA_NAMES, DrivingClipReader
from step10.contract import canonical_json, canonical_sha256, file_sha256, index_by_anchor, read_jsonl, require_identity, without_identity
from step10.schema import BUILDER_VERSION, FORMAT_VERSION, FRAME_OFFSETS_NS, sample_manifest_schema, write_schema

CANDIDATES = ANNOTATION_ROOT / "candidate_anchors.jsonl"
KEYFRAMES = ANNOTATION_ROOT / "keyframes.jsonl"
META_ACTIONS = ANNOTATION_ROOT / "meta_actions_v0.2.jsonl"
NAVIGATION = ANNOTATION_ROOT / "navigation.jsonl"
SCENE_FACTS = ANNOTATION_ROOT / "scene_facts.jsonl"
STRUCTURED = ANNOTATION_ROOT / "structured_causality.jsonl"
REASONING = ANNOTATION_ROOT / "reasoning.jsonl"
OUTPUT = MANIFEST_ROOT / "sample_manifest_v0.1.jsonl"
CONTRACT = MANIFEST_ROOT / "sample_manifest_contract_v0.1.json"
SUMMARY = REPORT_ROOT / "sample_manifest_summary_v0.1.json"
SCHEMA = SCHEMA_ROOT / "sample_manifest_schema_v0.1-draft.json"

REASONING_POLICY = {
    "authoritative": False,
    "default_training_usage": "excluded",
    "optional_experimental_usage": "auxiliary_only",
    "sample_membership_dependency": False,
    "action_target_dependency": False,
    "dataset_split_dependency": False,
}


def atomic_write(path: Path, text: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing output: {path}; use --force")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def frame_record(data_root: Path, camera_name: str, offset_ns: int, group: Any) -> dict[str, Any]:
    match = group.matches[camera_name]
    frame = match.value
    relative = frame.image_path.relative_to(data_root)
    return {
        "camera_name": camera_name,
        "relative_time_ns": offset_ns,
        "target_stamp_ns": int(group.target_ns),
        "frame_stamp_ns": int(match.timestamp_ns),
        "time_error_ns": int(match.error_ns),
        "frame_index": int(frame.frame_index),
        "image_path": relative.as_posix(),
        "width": int(frame.width),
        "height": int(frame.height),
        "encoding": str(frame.encoding),
        "frame_id": str(frame.frame_id),
    }


def build_visual(reader: DrivingClipReader, candidate: Mapping[str, Any], data_root: Path) -> dict[str, Any]:
    offsets = tuple(int(value) for value in candidate["frame_offsets_ns"])
    if offsets != FRAME_OFFSETS_NS:
        raise ValueError(f"unsupported frame offsets for {candidate['anchor_id']}: {offsets}")
    sequence = reader.get_multicamera_frames(int(candidate["anchor_ns"]), offsets_ns=offsets, prefer_exact=True)
    if sequence is None:
        raise ValueError(f"multicamera synchronization failed: {candidate['anchor_id']}")
    modes = [str(group.mode) for group in sequence.groups]
    maximum_skew = max(int(group.maximum_skew_ns) for group in sequence.groups)
    maximum_error = max(int(group.maximum_target_error_ns) for group in sequence.groups)
    expected_modes = [str(value) for value in candidate["visual_group_modes"]]
    if modes != expected_modes or str(candidate["visual_sequence_mode"]) != "all_exact":
        raise ValueError(f"visual mode mismatch: {candidate['anchor_id']}")
    if maximum_skew != int(candidate["maximum_camera_skew_ns"]):
        raise ValueError(f"camera skew mismatch: {candidate['anchor_id']}")
    if maximum_error != int(candidate["maximum_camera_target_error_ns"]):
        raise ValueError(f"camera target error mismatch: {candidate['anchor_id']}")
    frames = {name: [] for name in CAMERA_NAMES}
    for offset, group in zip(offsets, sequence.groups):
        for name in CAMERA_NAMES:
            frames[name].append(frame_record(data_root, name, offset, group))
    return {
        "visual_profile": str(candidate["visual_profile"]),
        "camera_names": list(CAMERA_NAMES),
        "frame_offsets_ns": list(offsets),
        "visual_sequence_mode": str(candidate["visual_sequence_mode"]),
        "visual_group_modes": modes,
        "maximum_camera_skew_ns": maximum_skew,
        "maximum_camera_target_error_ns": maximum_error,
        "frames": frames,
    }


def build_history(reader: DrivingClipReader, candidate: Mapping[str, Any]) -> dict[str, Any]:
    history = reader.get_ego_history(int(candidate["anchor_ns"]), num_waypoints=16, interval_ns=100_000_000)
    if history is None:
        raise ValueError(f"Ego history unavailable: {candidate['anchor_id']}")
    points = reader.ego_history_to_dicts(history)
    if len(points) != 16:
        raise ValueError(f"Ego history count mismatch: {candidate['anchor_id']}")
    return {
        "profile": str(candidate["ego_history_profile"]),
        "frame": "anchor_ego",
        "point_count": 16,
        "interval_ns": 100_000_000,
        "span_ns": 1_500_000_000,
        "points": points,
    }


def quality_value(value: Any, fallback: str = "unknown") -> str:
    return str(value) if value in {"usable", "partial", "unknown", "unavailable"} else fallback


def build_record(*, keyframe: Mapping[str, Any], candidate: Mapping[str, Any], meta_action: Mapping[str, Any], navigation: Mapping[str, Any], scene_fact: Mapping[str, Any], structured: Mapping[str, Any], reasoning: Mapping[str, Any] | None, reader: DrivingClipReader, data_root: Path) -> dict[str, Any]:
    for name, source in (("candidate", candidate), ("meta_action", meta_action), ("navigation", navigation), ("scene_fact", scene_fact), ("structured_causality", structured)):
        require_identity(keyframe, source, name)
    if reasoning is not None:
        require_identity(keyframe, reasoning, "reasoning")
    selection = without_identity(keyframe)
    model_navigation = without_identity(navigation)
    decision = without_identity(meta_action)
    facts = without_identity(scene_fact)
    coc = without_identity(structured)
    reason_record = without_identity(reasoning) if reasoning is not None else None
    return {
        "sample_manifest_format_version": FORMAT_VERSION,
        "builder_version": BUILDER_VERSION,
        "anchor_id": str(keyframe["anchor_id"]),
        "clip_id": str(keyframe["clip_id"]),
        "anchor_ns": int(keyframe["anchor_ns"]),
        "selection": selection,
        "model_input": {
            "visual": build_visual(reader, candidate, data_root),
            "ego_history": build_history(reader, candidate),
            "navigation": model_navigation,
        },
        "supervision": {
            "driving_decision": decision,
            "scene_facts": facts,
            "structured_causality": coc,
        },
        "optional_auxiliary": {
            "reasoning": {
                "available": reasoning is not None,
                "record": reason_record,
                "usage_policy": REASONING_POLICY,
            }
        },
        "quality": {
            "meta_action": quality_value(meta_action.get("overall_quality_status")),
            "navigation": quality_value(navigation.get("navigation", {}).get("quality_status")),
            "scene_facts": quality_value(scene_fact.get("quality", {}).get("status")),
            "structured_causality": quality_value(structured.get("quality", {}).get("status")),
            "reasoning": quality_value(reasoning.get("quality_status")) if reasoning is not None else "unavailable",
        },
        "provenance": {
            "candidate_anchor_record_sha256": canonical_sha256(candidate),
            "keyframe_record_sha256": canonical_sha256(keyframe),
            "meta_action_record_sha256": canonical_sha256(meta_action),
            "navigation_record_sha256": canonical_sha256(navigation),
            "scene_fact_record_sha256": canonical_sha256(scene_fact),
            "structured_causality_record_sha256": canonical_sha256(structured),
            "reasoning_record_sha256": canonical_sha256(reasoning) if reasoning is not None else None,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=ALPASIM_DATA_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--contract-output", type=Path, default=CONTRACT)
    parser.add_argument("--summary-output", type=Path, default=SUMMARY)
    parser.add_argument("--schema-output", type=Path, default=SCHEMA)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    paths = {
        "candidate_anchors": CANDIDATES, "keyframes": KEYFRAMES, "meta_actions": META_ACTIONS,
        "navigation": NAVIGATION, "scene_facts": SCENE_FACTS,
        "structured_causality": STRUCTURED, "reasoning": REASONING,
    }
    loaded = {name: read_jsonl(path) for name, path in paths.items()}
    indexes = {name: index_by_anchor(rows, name) for name, rows in loaded.items()}
    keyframes = loaded["keyframes"]
    keyframe_ids = [str(row["anchor_id"]) for row in keyframes]
    expected = set(keyframe_ids)
    if len(keyframe_ids) != len(expected):
        raise ValueError("Keyframes contain duplicate anchor_id values")
    for name in ("navigation", "scene_facts", "structured_causality", "reasoning"):
        actual = set(indexes[name])
        if actual != expected:
            raise ValueError(f"{name} coverage mismatch missing={len(expected-actual)} extra={len(actual-expected)}")
    for name in ("candidate_anchors", "meta_actions"):
        missing = expected - set(indexes[name])
        if missing:
            raise ValueError(f"{name} missing Keyframes: {sorted(missing)[:5]}")

    schema = sample_manifest_schema()
    validator = Draft202012Validator(schema)
    records = []
    readers: dict[str, DrivingClipReader] = {}
    quality_counts = {key: Counter() for key in ("meta_action", "navigation", "scene_facts", "structured_causality", "reasoning")}
    for index, keyframe in enumerate(keyframes, 1):
        anchor_id = str(keyframe["anchor_id"])
        clip_id = str(keyframe["clip_id"])
        reader = readers.setdefault(clip_id, DrivingClipReader(args.dataset_root / clip_id))
        record = build_record(
            keyframe=keyframe,
            candidate=indexes["candidate_anchors"][anchor_id],
            meta_action=indexes["meta_actions"][anchor_id],
            navigation=indexes["navigation"][anchor_id],
            scene_fact=indexes["scene_facts"][anchor_id],
            structured=indexes["structured_causality"][anchor_id],
            reasoning=indexes["reasoning"].get(anchor_id),
            reader=reader,
            data_root=args.dataset_root.resolve(),
        )
        errors = sorted(validator.iter_errors(record), key=lambda error: list(error.absolute_path))
        if errors:
            error = errors[0]
            location = ".".join(str(item) for item in error.absolute_path) or "$"
            raise ValueError(f"{anchor_id}: schema error at {location}: {error.message}")
        records.append(record)
        for name, value in record["quality"].items():
            quality_counts[name][value] += 1
        if index == 1 or index % 250 == 0 or index == len(keyframes):
            print(f"[Step 10] {index}/{len(keyframes)}: {anchor_id}", flush=True)

    output_text = "".join(canonical_json(row) + "\n" for row in records)
    output_hash = __import__("hashlib").sha256(output_text.encode("utf-8")).hexdigest()
    write_schema(args.schema_output)
    schema_hash = file_sha256(args.schema_output)
    summary = {
        "summary_version": "0.1", "record_count": len(records),
        "unique_anchor_count": len({row["anchor_id"] for row in records}),
        "camera_count_per_sample": 4, "frames_per_camera": 3,
        "image_reference_count": len(records) * 12,
        "ego_history_points_per_sample": 16,
        "ego_history_point_count": len(records) * 16,
        "reasoning_available_count": sum(row["optional_auxiliary"]["reasoning"]["available"] for row in records),
        "quality_counts": {name: dict(sorted(counter.items())) for name, counter in quality_counts.items()},
        "output_path": str(args.output), "output_sha256": output_hash,
        "schema_path": str(args.schema_output), "schema_sha256": schema_hash,
        "elapsed_seconds": time.monotonic() - started,
        "static_occupancy_used": False,
        "future_actor_data_used_as_model_input": False,
        "future_ego_data_used_as_model_input": False,
        "planner_output_used_as_model_input": False,
    }
    contract = {
        "contract_version": "0.1", "producer_step": 10,
        "sample_manifest_format_version": FORMAT_VERSION,
        "builder_version": BUILDER_VERSION,
        "record_count": len(records), "output_path": str(args.output), "output_sha256": output_hash,
        "schema_path": str(args.schema_output), "schema_sha256": schema_hash,
        "summary_path": str(args.summary_output),
        "source_paths": {name: str(path) for name, path in paths.items()},
        "source_sha256": {name: file_sha256(path) for name, path in paths.items()},
        "training_views": {
            "default": "structured_only",
            "optional_experimental": "reasoning_assisted",
            "identical_sample_membership": True,
            "identical_primary_inputs_and_supervision": True,
        },
        "reasoning_usage_policy": REASONING_POLICY,
        "model_input_policy": {
            "camera_count": 4, "frames_per_camera": 3,
            "frame_offsets_ns": list(FRAME_OFFSETS_NS),
            "ego_history_profile": "ego_history_16x10hz_v0.1",
            "static_occupancy_used": False,
            "future_actor_data_used": False,
            "future_ego_data_used": False,
            "planner_output_used": False,
        },
    }
    atomic_write(args.output, output_text, args.force)
    atomic_write(args.summary_output, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.force)
    atomic_write(args.contract_output, json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.force)
    print("Step 10 self-contained Sample Manifest")
    print("records:", len(records))
    print("image references:", summary["image_reference_count"])
    print("Ego history points:", summary["ego_history_point_count"])
    print("reasoning available:", summary["reasoning_available_count"])
    print("sha256:", output_hash)
    print("output:", args.output)
    print("schema:", args.schema_output)
    print("summary:", args.summary_output)
    print("contract:", args.contract_output)
    print("PASS: Step 10 Sample Manifest built, validated, summarized, and contracted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
