#!/usr/bin/env python3
"""Build and validate Step 7L final scene_facts.jsonl."""
from __future__ import annotations
import hashlib, json, os, time
from project_paths import ANNOTATION_ROOT, INTERMEDIATE_ROOT, SCHEMA_ROOT
from step7.scene_facts import summarize_final_scene_facts, CAMERA_NAMES
from step7.scene_facts import build_final_scene_fact_record
from step7.scene_facts import load_scene_fact_validator, validate_scene_fact_record, write_scene_fact_schema
from step7.observability import evaluate_frozen_dynamic_occlusion_policy

KEYFRAMES = ANNOTATION_ROOT / "keyframes.jsonl"
FEATURES = INTERMEDIATE_ROOT / "scene_fact_features_v0.1.jsonl"
OCCLUSION_EVIDENCE = ANNOTATION_ROOT / "step7e_geometric_occlusion_evidence_v02.jsonl"
OUTPUT = ANNOTATION_ROOT / "scene_facts.jsonl"
SUMMARY = ANNOTATION_ROOT / "step7l_scene_facts_summary_v01.json"
SCHEMA = SCHEMA_ROOT / "scene_fact_schema_v0.1-draft.json"


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]



def build_visible_camera_index(evidence_rows):
    """Return frozen-policy visible cameras keyed by (anchor_id, track_id)."""
    decisions = evaluate_frozen_dynamic_occlusion_policy(
        evidence_rows=evidence_rows
    )
    if len(decisions) != len(evidence_rows):
        raise RuntimeError("dynamic-occlusion decisions do not close to evidence")

    allowed_cameras = set(CAMERA_NAMES)
    result = {}
    for evidence, decision in zip(evidence_rows, decisions):
        identity = (
            str(evidence["anchor_id"]),
            str(evidence["track_id"]),
        )
        if identity in result:
            raise ValueError(f"duplicate occlusion identity: {identity}")
        if decision.anchor_id != identity[0] or decision.track_id != identity[1]:
            raise ValueError(f"occlusion decision identity mismatch: {identity}")

        cameras = tuple(sorted({
            str(value)
            for value in evidence.get("occlusion_winning_camera_names", ())
        }))
        unknown = sorted(set(cameras) - allowed_cameras)
        if unknown:
            raise ValueError(
                f"unsupported visible cameras for {identity}: {unknown}"
            )

        if decision.shadow_status == "shadow_visible":
            if not cameras:
                raise ValueError(
                    f"shadow-visible Actor lacks winning camera: {identity}"
                )
            result[identity] = cameras
        else:
            result[identity] = tuple()
    return result

def unique_by_anchor(rows, name):
    result = {}
    for row in rows:
        anchor = str(row["anchor_id"])
        if anchor in result:
            raise ValueError(f"duplicate {name} Anchor: {anchor}")
        result[anchor] = row
    return result


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def duration_text(seconds):
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def progress(completed, total, started):
    elapsed = time.monotonic() - started
    rate = completed / elapsed if elapsed else 0.0
    eta = (total - completed) / rate if rate else 0.0
    print(
        f"[Step 7L] {completed}/{total} Scene Facts | {100.0*completed/total:5.1f}% | "
        f"elapsed {duration_text(elapsed)} | rate {rate:.2f}/s | ETA {duration_text(eta)}",
        flush=True,
    )


def main():
    started = time.monotonic()
    print("[Step 7L:load] materializing JSON Schema and reading inputs", flush=True)
    write_scene_fact_schema(SCHEMA)
    keyframes = sorted(read_jsonl(KEYFRAMES), key=lambda row: (
        str(row["clip_id"]), int(row["anchor_ns"]), str(row["anchor_id"])
    ))
    features = unique_by_anchor(read_jsonl(FEATURES), "feature")
    expected = {str(row["anchor_id"]) for row in keyframes}
    if set(features) != expected:
        raise ValueError("feature Anchors do not close to Keyframes")
    evidence_rows = read_jsonl(OCCLUSION_EVIDENCE)
    visible_cameras = build_visible_camera_index(evidence_rows)
    validator = load_scene_fact_validator(SCHEMA)
    rows = []
    temporary = OUTPUT.with_suffix(".jsonl.tmp")
    last_progress = started
    with temporary.open("w", encoding="utf-8") as output:
        for index, keyframe in enumerate(keyframes, start=1):
            anchor = str(keyframe["anchor_id"])
            feature = features[anchor]
            visible_cameras_by_track_id = {}
            for role in ("lead_actors", "left_nearby_actors", "right_nearby_actors"):
                for selected in feature["actor_context"][role]:
                    track_id = str(selected["track_id"])
                    identity = (anchor, track_id)
                    camera_names = visible_cameras.get(identity)
                    if camera_names is None:
                        raise ValueError(
                            f"selected Actor lacks occlusion evidence: {identity}"
                        )
                    if not camera_names:
                        raise ValueError(
                            f"selected Actor is not visible under frozen policy: {identity}"
                        )
                    visible_cameras_by_track_id[track_id] = camera_names
            row = build_final_scene_fact_record(
                feature=feature,
                visible_cameras_by_track_id=visible_cameras_by_track_id,
            )
            validate_scene_fact_record(row, validator=validator)
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            rows.append(row)
            now = time.monotonic()
            if index == len(keyframes) or index % 250 == 0 or now - last_progress >= 10.0:
                progress(index, len(keyframes), started)
                last_progress = now
    os.replace(temporary, OUTPUT)
    report = summarize_final_scene_facts(keyframes=keyframes, rows=rows)
    report.update({
        "output_path": str(OUTPUT),
        "output_sha256": digest(OUTPUT),
        "schema_path": str(SCHEMA),
        "schema_sha256": digest(SCHEMA),
        "source_feature_path": str(FEATURES),
        "source_feature_sha256": digest(FEATURES),
        "source_occlusion_evidence_path": str(OCCLUSION_EVIDENCE),
        "source_occlusion_evidence_sha256": digest(OCCLUSION_EVIDENCE),
        "elapsed_seconds": time.monotonic() - started,
        "future_data_used": False,
    })
    temporary_summary = SUMMARY.with_suffix(".json.tmp")
    temporary_summary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary_summary, SUMMARY)
    print("Step 7L final Scene-Fact export")
    print("rows:", report["scene_fact_row_count"])
    print("schema validation errors:", report["schema_validation_error_count"])
    print("road contexts:", report["road_context_type_counts"])
    print("quality statuses:", report["quality_status_counts"])
    print("sha256:", report["output_sha256"])
    print("elapsed:", duration_text(report["elapsed_seconds"]))
    print("output:", OUTPUT)
    print("summary:", SUMMARY)
    print("PASS: final Scene Facts generated and validated against Draft 2020-12 schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
