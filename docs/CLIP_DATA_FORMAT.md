# AlpaSim Recorded Clip Data Format

**Document status:** Current raw Clip contract and final dataset-consumer notes, updated 2026-10-30  
**Scope:** Raw `test_clip_NNN` data consumed by the standalone dataset repository  
**Current raw format:** `dataset_format_version = "0.2-batch"`

## 1. Identity and lifecycle

A completed rollout is `test_clip_NNN`. A `test_clip_NNN.tmp` directory is incomplete and must not be treated as production-ready. Camera streams are independent. Synchronize cameras by timestamps, never by cross-camera frame index.

## 2. Core directory layout

```text
test_clip_NNN/
├── metadata.json
├── validation.json
├── calibration/
│   ├── front_wide.json
│   ├── front_tele.json
│   ├── cross_left.json
│   └── cross_right.json
├── cameras/<camera_name>/
│   ├── *.jpg
│   └── timestamps.jsonl
├── ego/
│   ├── ego_state.jsonl
│   ├── ground_truth_future.jsonl
│   ├── planner_output.jsonl
│   ├── executed_path_points.jsonl
│   ├── executed_path_final.json
│   └── complete_recording_ground_truth.json
├── actors/
│   ├── current.jsonl
│   ├── history.jsonl
│   └── future.jsonl
├── route/
│   ├── map_route.jsonl
│   └── navigation_route_local.jsonl
├── map/vector_map.json
└── static_occupancy/                 # optional
    ├── columns.npz
    └── metadata.json
```

`static_occupancy/` is optional. A Clip without mesh-derived static occupancy remains valid for the current camera-only dataset pipeline. Collection may proceed after the USDZ asset is downloaded; it does not require mesh acknowledgement. If no mesh/static occupancy is available, the folder is not created. The current Sample Manifest does not consume static occupancy.

## 3. Time, units, and frames

Canonical simulation time is integer nanoseconds:

```text
stamp_ns = sec * 1,000,000,000 + nanosec
```

- Distance: metres
- Speed: metres per second
- Acceleration: metres per second squared
- Angles: radians
- Ego-local planar axes: x forward, y left
- Positive planar yaw: counter-clockwise/left

Wall-clock lifecycle times are diagnostic only. Readers must respect declared frames and must not mix map and Ego-local values without the shared coordinate utilities.

## 4. Cameras and calibration

Cameras:

```text
front_wide
front_tele
cross_left
cross_right
```

Each timestamp row records frame index, `stamp_ns`, frame ID, dimensions, encoding, stride, relative image path, and JPEG byte count. Calibration contains F-theta intrinsics and `rig_to_camera` extrinsics. A pinhole approximation is not valid.

Review-only alignment offsets belong to visualization tooling and never modify raw calibration or formal labels.

## 5. Ego, Actor, Route, and map semantics

- `ego_state.jsonl`: current Ego state and motion.
- `ground_truth_future.jsonl`: future supervision only; never current model input.
- `planner_output.jsonl`: not valid current Scene-Fact evidence.
- `actors/current.jsonl`: current simulator Actor snapshots.
- `actors/history.jsonl`: optional recorded history; Step 7 derives formal short history from current snapshots at or before the Anchor.
- `actors/future.jsonl`: future truth; forbidden for current Scene Facts and observability.
- `navigation_route_local.jsonl`: model-input Route in Ego-local coordinates.
- `vector_map.json`: lanes, road edges, signs, wait lines, map bounds, and scene identifiers.

Simulator Actor truth is not automatically camera-observable. Step 7 applies the frozen observability gate. Missing Actor identity or projection must not be fabricated.

## 6. Leakage policy by stage

- Step 3 may require future-GT availability for Anchor eligibility.
- Step 4 may use future Ego execution for supervision labels.
- Step 6 Navigation uses only Anchor-time-or-earlier Route, Anchor-time Ego state, and static VectorMap.
- Step 7 Scene Facts use current/past evidence at or before the Anchor, synchronized cameras, calibration, and static VectorMap.
- Step 8 Structured CoC combines explicit model-input evidence and supervision, without reclassifying supervision as model input.
- Step 9 rewrites confirmed Structured CoC information for people; it is non-authoritative.
- Step 10 embeds three camera frames, Ego history, Navigation, supervision, Structured CoC, and optional reasoning in one Sample Manifest record.
- Step 11 groups by Clip for an exclusive 80/10/10 split.
- Step 12 audits paths, images, finite values, provenance, leakage, split integrity, and human review.

Forbidden as model input in the final dataset:

```text
actors/future.jsonl
ego/ground_truth_future.jsonl
ego/complete_recording_ground_truth.json
ego/planner_output.jsonl
static_occupancy/
```

## 7. Final Sample Manifest consumption

The final training sample uses four cameras and three exact frames per camera:

```text
relative_time_ns = [-400000000, -200000000, 0]
```

It also embeds 16 Ego-history points at 10 Hz over 1.5 seconds. Image paths remain relative to `/home/lab/data_from_alpasim`. The final audit verified 22368 image references with zero missing, absolute, or escaping paths.

Training should read:

```text
/home/lab/alpamayo_like_dataset/outcome/manifests/sample_manifest_v0.1.jsonl
/home/lab/alpamayo_like_dataset/outcome/manifests/dataset_split_v0.1.jsonl
```

and resolve image paths against:

```text
/home/lab/data_from_alpasim
```

Training should not join the Step 4-9 JSONL files.

## 8. Reader compatibility requirements

A compatible reader must:

- validate `metadata.json` and supported format versions;
- reject or separately classify `.tmp` Clips;
- distinguish topic envelopes from direct rows;
- validate timestamp order and duplicates;
- use camera timestamp indexes;
- prefer exact-time matches and use bounded fallback only where the consuming contract allows it;
- respect frame declarations;
- support optional `static_occupancy/` without requiring it;
- never fabricate missing data.

## 9. Format evolution

Do not silently change raw directory names, file names, row envelopes, time meaning, coordinate meaning, or validation semantics. A raw-format change requires a new `dataset_format_version`, reader changes, Step 1 validation changes, tests, and a compatibility statement.

Annotation versions, output-root changes, Sample Manifest changes, and review overlays do not by themselves change the raw Clip format.

## 10. Related code and documents

```text
/home/lab/alpamayo_like_dataset/dataset_tools/project_paths.py
/home/lab/alpamayo_like_dataset/dataset_tools/step2/
/home/lab/alpamayo_like_dataset/dataset_tools/step7/
/home/lab/alpamayo_like_dataset/dataset_tools/step10/
/home/lab/alpamayo_like_dataset/dataset_tools/step11/
/home/lab/alpamayo_like_dataset/dataset_tools/step12/
```

Primary handoff: `AI_DATASET_DEVELOPMENT_HANDOFF.md`  
Scene-Fact contract: `SCENE_FACT_DESIGN.md`

## 11. Source-of-truth note

This document explains the raw Clip contract. It does not override the final Sample Manifest, split, or audit contracts. Historical backup reports are non-authoritative. For training membership and delivery status, follow `AI_DATASET_DEVELOPMENT_HANDOFF.md` and the final JSON contracts under `outcome/manifests/`.
