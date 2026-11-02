# Step 7 Scene-Fact Generator Design and Contract

**Document status:** Current reusable Step 7 design  
**Formal artifact:** `outcome/annotations/v0.1-draft/scene_facts.jsonl`

## 1. Purpose

Step 7 produces structured Scene Facts at `anchor_ns` from current and past evidence. It does not generate Structured CoC or natural-language reasoning. Missing evidence becomes explicit uncertainty rather than an invented fact.

Current scale, distributions, versions, and hashes are read from generated artifacts and contracts.

## 2. Evidence boundary

Allowed evidence includes the selected Keyframe, synchronized current images, calibration, Anchor-time Ego state, current/past Actor snapshots, and static VectorMap.

Forbidden evidence includes Actor future, Ego future, complete-recording future trajectory, planner output, future executed behavior, Meta-action supervision as scene evidence, and optional static occupancy as formal evidence in the current design.

## 3. Reliable Ego speed invariant

Step 7H computes `reference_ego_speed_mps`. The same value propagates through Actor-role selection, Actor geometry, Scene-Fact feature assembly, and final materialization.

```text
actor.ego_speed_mps == actor_context.reference_ego_speed_mps
```

Actor-relative velocity, speed gap, relative longitudinal speed, and relative-speed category use the same reliable Ego speed. Recomputing geometry with a frozen raw speed after reference-speed selection is forbidden. Step 7L rejects mismatches before formal output.

## 4. Geometry and observability

Coordinates are Anchor Ego-local. The implementation uses recorded F-theta calibration, oriented Actor boxes, projected geometry, and Actor-to-Actor occlusion reasoning. Simulator Actor truth is not automatically visual supervision.

Static-scene mesh occlusion, rendered depth, and pixel-accurate masks are not part of the contract. Review offsets affect visualization only.

## 5. Actor roles

Formal lists are `lead_actors`, `left_nearby_actors`, and `right_nearby_actors`. An Actor appears in at most one list and receives deterministic `role_rank`.

Capacities, horizons, geometric thresholds, and motion thresholds are frozen implementation rules. Read exact values from current Step 7 code and tests rather than duplicating them in scale-dependent documentation.

## 6. Road Context

Vocabulary includes `lane_following`, `intersection_approach`, `intersection`, and `unknown`. Map-derived proximity is conservative.

Wait-line type may be unavailable. A visible STOP sign is not automatically a formal stop-line fact. Traffic-light color and brake-light state are not trustworthy formal states and must not be invented.

## 7. Record and downstream contract

Each Actor includes identity, class, geometry, distance, motion categories, reliable Ego speed, Actor speed, lane relation, visibility, quality, and reasons.

Step 8 joins Navigation, Meta-action, and Scene Facts by exact Anchor identity. Current rules include Road Context support for appropriate longitudinal responses, one eligible primary Rank-1 Lead Actor, no fallback to lower Lead ranks, conservative Far Lead and Side Actor behavior, and stage consistency between route-level straight intent and lane-level lane change.

Step 9 converts confirmed Structured CoC facts into non-authoritative language. Step 10 embeds the complete Scene-Fact object and its provenance; training does not join `scene_facts.jsonl`.

## 8. Human review protocol

Step 12 generates final review materials. A completed Decision uses `review_status: completed`, six string-valued dimensions using `pass`, `warn`, or `fail`, explicit issues, and reviewer notes. Boolean review values and unrecognized statuses are invalid.

## 9. Known limitations

- no static-scene occlusion evaluation;
- no rendered depth or pixel-accurate masks;
- some visible objects lack usable identity or projection;
- wait-line type may remain unavailable;
- traffic-light and brake-light states are not formal facts;
- lane relation may remain unknown;
- Scene Facts are context, not causality or reasoning.

## 10. Rebuild rule

An approved Step 7 change requires tests, rebuild of affected Step 7 stages, invariant and Schema validation, Step 8 frozen-input update, rebuild of all dependent downstream stages, refreshed human review, and final Step 12 closure.

Current content, scale, distributions, versions, and hashes are authoritative only in formal `outcome/` artifacts.
