# AlpaSim VLM Dataset Development Handoff

**Document status:** Current reusable Step 0-12 workflow and delivery contract  
**Audience:** A new AI assistant or developer continuing the standalone dataset repository

## 1. Development route

- Step 0: Freeze schemas and versions
- Step 1: Clip Manifest
- Step 2: Unified reading API
- Step 3: Candidate Anchors
- Step 4: Meta-actions
- Step 5: Keyframes
- Step 6: Navigation
- Step 7: Scene Facts
- Step 8: Structured CoC
- Step 9: Human-readable reasoning
- Step 10: Self-contained Sample Manifest
- Step 11: Clip-grouped dataset split
- Step 12: Final audit, statistics, and human review

The workflow is reusable across datasets of different sizes. Do not hard-code sample counts, Clip counts, class counts, split counts, test counts, or artifact hashes in implementation guidance or these handoff documents. Read current values from formal contracts, summaries, and audit artifacts.

## 2. Sources of truth

Use this precedence when information differs:

1. `outcome/manifests/final_dataset_contract_v0.1.json`
2. `outcome/reports/final_dataset_audit_v0.1.json`
3. Step-specific contracts under `outcome/manifests/`
4. Formal JSON and JSONL artifacts
5. These Markdown documents
6. Historical backups, which are not current sources of truth

The authoritative formal-output root is `/home/lab/alpamayo_like_dataset/outcome`.

## 3. Repository policy

```text
Repository:       /home/lab/alpamayo_like_dataset
Dataset code:     /home/lab/alpamayo_like_dataset/dataset_tools
Raw Clip root:    /home/lab/data_from_alpasim
Formal artifacts: /home/lab/alpamayo_like_dataset/outcome
```

- Keep raw Clips and generated artifacts separate.
- Write formal outputs only under `outcome/`.
- Keep `outcome/` outside Git tracking.
- The user manages Git. Do not inspect, stage, commit, or alter Git state unless requested.
- Dataset processing is independent of the ROS workspace.
- Put temporary diagnostics, source bundles, and patch scripts in `~/Downloads`.
- Run downloaded patch scripts directly from `~/Downloads` while the repository is the current working directory. Do not move patch scripts into the repository.
- Supply downloadable modification scripts rather than asking the user to create source files manually.
- Run the complete test suite after a coherent change.
- Continue automatically after validation unless a user decision is required.

## 4. Self-contained training contract

Step 10 produces a self-contained Sample Manifest. Training reads the Sample Manifest plus raw images and uses the Step 11 split artifact. Training must not join Step 4-9 JSONL files at runtime.

Each record contains the configured multi-camera, multi-frame visual input, Ego history in the Anchor Ego frame, Navigation, driving-decision supervision, Scene Facts, Structured CoC, optional non-authoritative reasoning, quality, and provenance.

Two training views share identical membership, primary input, supervision, and split:

- `structured_only`: default; excludes Step 9 reasoning.
- `reasoning_assisted`: experimental; reasoning is auxiliary only.

Step 9 reasoning must not affect sample acceptance, action targets, membership, or split assignment.

## 5. Step 2 Ego-history dynamics

Some recorded Clips contain reported Ego speed, velocity, or acceleration fields that freeze at zero while Pose continues moving. A related visualization symptom is an Ego vehicle that appears stationary in RViz and later jumps forward.

The unified reader therefore derives Ego-history speed from planar Pose displacement and timestamps. Longitudinal acceleration is derived from the resulting speed sequence. Zero reported speed must not be interpreted as a stationary vehicle when Pose shows motion.

Required behavior:

- timestamps strictly increase;
- endpoint speed uses the adjacent interval;
- interior speed uses adjacent intervals with time-aware weighting;
- acceleration derives from the Pose-time speed sequence;
- Pose, yaw, and yaw-rate handling remain unchanged;
- non-finite values remain invalid.

Step 12 blocks a history whose Pose moves materially while its speed sequence remains near zero. Exact thresholds belong to current code and tests, not this scale-agnostic document.

## 6. Step 7 reliable Ego-speed propagation

Step 7 computes one reliable `reference_ego_speed_mps` and propagates it consistently through Step 7H Actor-role selection, Step 7I-K Scene-Fact feature assembly, and Step 7L final Scene Facts.

Every selected Actor must satisfy:

```text
actor.ego_speed_mps == actor_context.reference_ego_speed_mps
```

Actor-relative velocity and relative-speed categories must use the same reliable Ego speed. Step 7L rejects mismatches before formal output is written.

## 7. Step 8 Structured CoC

Exact current generator and rule versions are read from `step8/contract.py` and the generated contract.

Current semantic rules include:

- `road_context` participates as a formal node when linked to a decision.
- Usable wait-line/intersection context may support `decelerate` or `stop`.
- General usable intersection context may weakly support `decelerate` or `stop`.
- Traffic-light color and brake-light state are not invented.
- At most one eligible primary Rank-1 Lead Actor explains a longitudinal response.
- Rank 2 or Rank 3 is not a fallback when Rank 1 is ineligible.
- Far Lead and Side Actor relations remain conservative.
- Straight route intent may be stage-consistent with a lane-level lane change.
- Quality distinguishes usable sources from complete decision-explanation coverage.

Current distributions are read from the generated Step 8 summary and semantic profile.

## 8. Step 9 reasoning

Step 9 is a non-authoritative presentation layer. Exact prompt and generator versions are read from `step9/contract.py` and the reasoning contract.

The interface is summary-only:

```text
reasoning_summary
quality_status
source_record_sha256
```

Unknown facts are removed before LLM input. Intersection context may be described conservatively. Signal-light color, brake-light state, and absolute causality must not be invented. Reasoning remains excluded from default training.

## 9. Step 11 split

The split is deterministic, grouped exclusively by `clip_id`, approximately follows the configured ratio policy, and prevents Clip cross-split leakage. Reasoning and static occupancy are not split inputs.

Read current membership and distributions from the split contract and summary. A rare class may be absent from a split when preserving Clip integrity is preferable to manually moving Clips.

## 10. Step 12 audit and human review

Step 12 audits contracts, schemas, images, safe paths, finite Ego-history values, Pose-motion versus speed consistency, provenance, leakage boundaries, Anchor-set closure, Clip exclusivity, and human-review freshness.

A completed Decision uses `review_status: completed`. The six review dimensions use string values `pass`, `warn`, or `fail`. Boolean values and invented statuses such as `confirmed` are invalid. Pending, stale, invalid, or failed reviews block delivery.

Current audit status, warning counts, review counts, test baseline, dataset scale, and hashes are read from the final audit and contract rather than duplicated here.

## 11. Production entry points

```bash
cd /home/lab/alpamayo_like_dataset/dataset_tools || return
python3 -m pytest -q
python3 -u -m step8.build_step8 --force
python3 -u -m step9.run --force
python3 -u -m step10.build_sample_manifest --force
python3 -u -m step11.build_dataset_split --force
python3 -u -m step12.audit_dataset --force
```

Human review:

```bash
python3 -u -m step12.review_sample --split test --seed <seed> --force
```

Any approved upstream change requires rebuilding all dependent downstream stages and re-closing Step 12.

## 12. New-conversation quick start

1. Read the current formal contracts and audit before quoting scale, counts, versions, hashes, or delivery status.
2. Preserve the self-contained Sample Manifest and Clip-grouped split.
3. Keep structured-only training separate from reasoning-assisted experiments.
4. Do not reopen frozen semantics without a demonstrated defect.
5. Repair the earliest responsible step, then rebuild every dependent stage.
6. Continue automatically after validation unless a user decision is required.

## 13. Next boundary

The normal next phase is model training and evaluation. Future dataset expansion should reuse this pipeline, recompute scale-dependent artifacts, and rerun Step 12. Dataset growth alone is not a reason to change semantics.
