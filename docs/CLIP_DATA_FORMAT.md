# AlpaSim Recorded Clip Data Format

**Document status:** Current raw Clip contract and dataset-consumer guidance  
**Scope:** Raw `test_clip_NNN` data consumed by the standalone dataset repository  
**Current raw format:** `dataset_format_version = "0.2-batch"`

## 1. Identity and layout

A completed rollout is `test_clip_NNN`. A `.tmp` directory is incomplete. Camera streams are independent and must be synchronized by timestamps, never by cross-camera frame index.

```text
test_clip_NNN/
├── metadata.json
├── validation.json
├── calibration/
├── cameras/<camera_name>/
├── ego/
├── actors/
├── route/
├── map/vector_map.json
└── static_occupancy/       # optional
```

Static occupancy is optional and is not consumed by the current camera-only Sample Manifest.

## 2. Time, units, and frames

Canonical simulation time is integer nanoseconds:

```text
stamp_ns = sec * 1,000,000,000 + nanosec
```

Distances use metres, speed uses metres per second, acceleration uses metres per second squared, and angles use radians. Ego-local x points forward and y points left. Readers must respect declared frames.

## 3. Cameras and calibration

The supported streams are `front_wide`, `front_tele`, `cross_left`, and `cross_right`. Calibration uses recorded F-theta intrinsics and `rig_to_camera` extrinsics. Review-only offsets never modify formal calibration or labels.

## 4. Ego-state reliability

Reported Ego dynamics may be stale or frozen even while Pose moves. RViz may show a vehicle remaining stationary and then jumping to a newer position.

Therefore:

- `speed == 0` does not prove that the vehicle is stationary;
- zero velocity or acceleration may be unreliable when Pose changes;
- motion consistency compares reported dynamics with Pose-time displacement;
- the Step 2 reader derives Ego-history speed from Pose and timestamps;
- Ego-history acceleration derives from the Pose-time speed sequence;
- Step 4 may independently choose Pose-time-derived speed for supervision;
- downstream stages must not mix reliable Pose-derived motion with frozen reported dynamics.

Raw files remain unchanged. Reliability handling belongs to the reader and feature layers.

## 5. Source semantics

- `ego_state.jsonl`: current Ego state; reported dynamics require reliability checks.
- `executed_path_points.jsonl`: executed Pose sequence; attached dynamics may be stale.
- `ground_truth_future.jsonl`: future supervision only.
- `planner_output.jsonl`: not current Scene-Fact evidence.
- `actors/current.jsonl`: current Actor snapshots.
- `actors/history.jsonl`: optional history.
- `actors/future.jsonl`: future truth; forbidden for current Scene Facts.
- `navigation_route_local.jsonl`: Route input.
- `vector_map.json`: static map context.

Simulator Actor truth is not automatically camera-observable. Missing identity, projection, or lane evidence must not be fabricated.

## 6. Leakage boundaries

Step 4 may use future Ego execution for supervision. Steps 6 and 7 use Anchor-time/current/past evidence. Step 8 combines explicit evidence and supervision without reclassifying supervision as model input. Step 9 is non-authoritative. Step 10 creates the self-contained record. Step 11 groups by Clip. Step 12 audits content and review freshness.

Forbidden as final model input:

```text
actors/future.jsonl
ego/ground_truth_future.jsonl
ego/complete_recording_ground_truth.json
ego/planner_output.jsonl
static_occupancy/
```

## 7. Consumption

Training reads the Sample Manifest and split artifact and resolves relative image paths against the configured raw Clip root. Training must not join Step 4-9 JSONL files.

Current frame counts, offsets, Ego-history length, dataset scale, hashes, and builder versions are read from current contracts and schemas rather than duplicated here.

## 8. Reader requirements

A compatible reader validates metadata, rejects incomplete Clips, handles supported row envelopes, validates timestamps, synchronizes cameras by time, respects frames, derives reliable Ego motion when reported dynamics conflict with Pose, supports optional static occupancy, and never fabricates missing data.

## 9. Format evolution and authority

A raw-format change requires a new format version, reader update, Step 1 validation update, tests, and compatibility guidance. This document does not override formal Sample Manifest, split, or audit contracts. Current scale and delivery status come from `outcome/` artifacts.
