# Step 7 Scene-Fact Generator Design and Frozen Contract

**Document status:** Final-delivery interface, updated 2026-10-30  
**Status:** PASS / FROZEN  
**Formal artifact:** `/home/lab/alpamayo_like_dataset/outcome/annotations/v0.1-draft/scene_facts.jsonl`  
**Source SHA-256 recorded by Step 10:** `d9f1c772d1538b33153a06af492f3afe873255d57bf8a9606698e98cad3586bc`

## 1. Purpose and final boundary

Step 7 produces one structured Scene-Fact record per selected final Keyframe. It describes the scene at `anchor_ns` without using future execution. It does not generate Structured CoC or natural-language reasoning.

The final Step 10 Sample Manifest contains 1864 Scene-Fact records, one for every final `anchor_id`. Missing or incomplete evidence is represented conservatively through quality fields and reasons, never by dropping the sample or inventing a fact.

## 2. Allowed and forbidden evidence

Allowed:

- selected Keyframe identity;
- synchronized camera images and calibration;
- Anchor-time Ego state;
- exact/current Actor snapshots;
- current and past Actor snapshots at or before the Anchor;
- static VectorMap.

Forbidden for current Scene Facts:

- Actor future;
- Ego future;
- complete-recording future trajectory;
- planner output;
- future executed behavior;
- Meta-action labels as scene evidence;
- optional static-occupancy columns as formal Step 7 evidence in the current delivery.

## 3. Geometry, observability, and occlusion

Coordinates are Anchor Ego-local: x forward, y left. Cameras are `front_wide`, `front_tele`, `cross_left`, and `cross_right`. The implementation uses recorded F-theta calibration, Actor oriented 3D boxes, projected surface geometry, depth rasterization, and Actor-to-Actor Z-buffer competition.

Simulator Actor truth is not automatically visual supervision. An Actor must pass the frozen observability policy before entering a final list.

The implementation evaluates Actor-to-Actor occlusion but does not evaluate arbitrary static-scene mesh occlusion, rendered depth, or pixel-accurate instance masks. Final records therefore retain:

```json
{"static_occlusion_evaluated": false}
```

## 4. Final Actor lists and semantics

```text
lead_actors:         maximum 4
left_nearby_actors:  maximum 6
right_nearby_actors: maximum 6
```

An Actor appears in at most one list per Anchor and receives deterministic `role_rank`.

Eligible independent classes include automobiles, buses, heavy trucks, other vehicles, trailers, train/tram cars, riders, and people. Non-independent labels such as `protruding_object` are excluded.

Selection ranges:

- Lead corridor: ahead by more than 0.5 m, absolute lateral offset no more than 2.5 m.
- Lead horizon: `max(20 m, reference_ego_speed * 10 s)`.
- Side lateral range: `0.5 m < |y| <= 12 m`.
- Side forward horizon: `clamp(reference_ego_speed * 5 s, 20 m, 120 m)`.
- Rear horizon: `clamp(reference_ego_speed * 2 s, 15 m, 50 m)`.
- Side-person forward distance is capped at 30 m.

Relative distance:

- near: no more than 10 m;
- medium: above 10 m and no more than 30 m;
- far: above 30 m.

Motion thresholds:

- stable distance-rate magnitude: no more than 0.5 m/s;
- stationary Actor speed: no more than 0.5 m/s;
- similar speed difference: no more than 1.0 m/s.

Unresolved evidence becomes `uncertain` or receives `unknown` quality with reasons.

## 5. Road Context

Vocabulary:

```text
lane_following
intersection_approach
intersection
unknown
```

Final proximity fields are `intersection_proximity`, `stop_line_proximity`, and `yield_line_proximity`, with values `at`, `near`, `approaching`, `far`, `none`, or `unknown`.

These are conservative map-based facts. Wait-line type is not fully propagated, and a visible STOP sign is not automatically a confirmed Stop-line fact.

## 6. Final record structure

Top level:

```text
scene_fact_format_version
generator_version
rule_version
anchor_id
clip_id
anchor_ns
road_context
actor_context
quality
```

Current embedded versions:

```text
generator_version: 0.1.0
rule_version:      scene_fact_rules_v0.1-draft
```

Each selected Actor includes rank, Track ID, class, relative geometry, distance, motion categories, Actor/Ego speeds, lane-direction relation, observability, visible cameras, quality, and reasons.

## 7. Final delivered statistics

Final Sample Manifest Scene-Fact coverage: **1864/1864**.

Road Context:
- `intersection`: 133
- `intersection_approach`: 582
- `lane_following`: 1142
- `unknown`: 7

Scene-Fact quality:
- `unknown`: 313
- `usable`: 1551

Selected Actor occurrences in final samples:
- `lead_actors`: 1770
- `left_nearby_actors`: 2493
- `right_nearby_actors`: 2674

These counts describe the final selected Sample Manifest, not historical larger intermediate Keyframe builds. Historical references to 3,500 rows and their old hashes are obsolete for the current delivery.

## 8. Downstream Step 8 interface

The current Structured CoC embedded in the final Sample Manifest uses:

```text
generator_version: 0.2.0
rule_version:      structured_causality_rules_v0.3
source SHA-256:    0339cb78de77248533d68e50ebb7bb0cf13790dc870bc684e3d048a3d682c2e5
```

Step 8 joins Navigation, Meta-action, and Scene Facts by exact Anchor identity. It keeps evidence references explicit, uses conservative relations, and does not fabricate missing observations. The current rule set includes stage-consistent handling for an upcoming turn whose execution has not begun.

Structured CoC quality in final samples:
- `partial`: 558
- `unknown`: 166
- `usable`: 1140

## 9. Step 9 and Step 10 interface

Step 9 consumes Structured CoC and produces a summary-only, non-authoritative description. It does not alter Step 7 semantics.

Step 10 embeds the complete Scene-Fact object under:

```text
supervision.scene_facts
```

and records its quality under:

```text
quality.scene_facts
```

The source row's canonical SHA-256 is preserved under:

```text
provenance.scene_fact_record_sha256
```

Training uses the embedded Step 10 copy rather than joining `scene_facts.jsonl`.

## 10. Human review

Step 7 review remains available for detailed Actor-overlay diagnostics. Final delivery review is generated through:

```bash
cd /home/lab/alpamayo_like_dataset/dataset_tools || return
python3 -m step12.review_sample --split test --seed 12 --force
```

The final reviewed sample used the current Step 10 builder, current Structured CoC, and current Step 9 summary. All six review dimensions passed. The review Bundle, Decision, overview, and synchronized video hashes are included in the final Step 12 Contract.

## 11. Known limitations

- static-scene occlusion is not evaluated;
- no rendered depth or pixel-accurate instance masks;
- some camera-visible objects lack usable Actor identity/projection at the exact Anchor;
- wait-line type is not fully propagated;
- STOP-sign presence is not a dedicated visual fact;
- lane matching may remain unknown;
- review alignment offsets affect visualization only;
- Scene Facts are structured labels, not causality or language reasoning.

## 12. Freeze rule

Step 7 is frozen for this delivery. Do not alter its schema, thresholds, list semantics, observability policy, or embedded Sample Manifest representation unless a concrete downstream defect is demonstrated and the change is explicitly approved. Any approved change requires rebuilding and re-closing Steps 8 through 12, including Sample Manifest hashes, split membership validation, human-review freshness, and the final Contract.

## 13. Source-of-truth note

This document freezes Step 7 semantics. Final per-sample training content is the embedded `supervision.scene_facts` object in the Step 10 Sample Manifest. The Step 10 provenance hash, final Contract, and Step 12 audit take precedence over historical review or backup artifacts.
