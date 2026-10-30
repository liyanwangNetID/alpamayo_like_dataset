# AlpaSim VLM Dataset Development Handoff

**Document status:** Final Step 0-12 delivery handoff, updated 2026-10-30  
**Audience:** A new AI assistant or developer continuing the standalone dataset repository  
**Purpose:** These three documents are the complete minimum context for a new conversation. Read this file first, then `CLIP_DATA_FORMAT.md` and `SCENE_FACT_DESIGN.md`. Do not ask the user to repeat the project history.

## 1. Final project state

The Step 0 through Step 12 development route is complete and frozen:

- Step 0: Freeze schemas and versions
- Step 1: Clip Manifest
- Step 2: Unified reading API
- Step 3: Candidate Anchors
- Step 4: Meta-actions
- Step 5: Keyframes
- Step 6: Navigation
- Step 7: Scene Facts
- Step 8: Structured chain of causality (Structured CoC)
- Step 9: Human-readable reasoning
- Step 10: Self-contained Sample Manifest
- Step 11: Clip-grouped dataset split
- Step 12: Final machine audit, statistics, and human review

The authoritative delivery directory is:

```text
/home/lab/alpamayo_like_dataset/outcome
```

Final status: **PASS_WITH_WARNINGS**, with **0 blocking errors** and **1 non-blocking warning**. The dataset is deliverable. Do not reopen frozen upstream steps unless a concrete downstream defect is demonstrated.

## 2. Source-of-truth precedence

When documents and generated artifacts disagree, use this order:

1. `outcome/manifests/final_dataset_contract_v0.1.json` for final delivery closure and artifact hashes.
2. `outcome/reports/final_dataset_audit_v0.1.json` for machine and human audit status.
3. `outcome/manifests/sample_manifest_contract_v0.1.json` and `dataset_split_contract_v0.1.json` for Step 10 and Step 11 contracts.
4. The generated JSONL/JSON artifacts themselves.
5. These Markdown documents as the explanatory handoff.

Historical files under `outcome/reports/backups/` are not current sources of truth. A copied review Bundle is valid only when Step 12 reports it as current, completed, and non-stale.

## 3. Repository and path policy

```text
Dataset repository: /home/lab/alpamayo_like_dataset
Dataset code:       /home/lab/alpamayo_like_dataset/dataset_tools
Raw Clip root:      /home/lab/data_from_alpasim
Formal outcome:     /home/lab/alpamayo_like_dataset/outcome
```

Rules:

- Raw Clips and generated artifacts are separate.
- All formal generated artifacts go under `outcome/`.
- `outcome/` is excluded from Git.
- The user manages Git. Do not inspect, stage, commit, or alter Git state unless explicitly requested.
- Dataset code is independent of the ROS workspace. Do not return to `ALPASIM_ROS2_WS` for dataset processing.
- Machine-specific data roots are resolved through `project_paths.py` and environment configuration.
- Do not ask the user to create scripts with heredocs or manual copy-paste. Supply downloadable scripts.
- When supplying multiple files, include batch move/install commands.
- Run the complete test suite directly unless a failure requires focused diagnosis.

## 4. Frozen training sample contract

The final Sample Manifest is self-contained. Training reads the Sample Manifest plus raw images; it does not join Step 4-9 JSONL files at training time.

```text
Path:    /home/lab/alpamayo_like_dataset/outcome/manifests/sample_manifest_v0.1.jsonl
Records: 1864
SHA-256: de7b046e70b74929137c457d584ee2e42bf68d8933ba091b66c00feac790bcb8
Format:  0.1-draft
Builder: 0.2.0
```

Each record uses `anchor_id` as the unique sample identity. There is no duplicate `sample_id`.

Each sample contains:

- four cameras: `front_wide`, `front_tele`, `cross_left`, `cross_right`;
- three exact frames per camera at `-0.4 s`, `-0.2 s`, and `0 s`;
- 12 relative image references total;
- 16 Ego-history points at 10 Hz over 1.5 seconds, in the Anchor Ego frame;
- coarse Navigation input;
- driving-decision supervision;
- complete Scene Facts;
- Structured CoC;
- optional non-authoritative Step 9 reasoning;
- quality and provenance hashes.

Totals:

- Image references: 22368
- Ego-history points: 29824
- Reasoning available: 1864/1864
- Static occupancy used by the Sample Manifest: **false**
- Future Actor, future Ego, planner output used as model input: **false**

Two training views share identical sample membership, primary model input, supervision, and split assignment:

- Default: `structured_only`, Step 9 reasoning excluded.
- Experimental: `reasoning_assisted`, reasoning auxiliary only.

Step 9 reasoning is non-authoritative. It must not affect sample membership, action targets, acceptance, or split assignment.

## 5. Final Step 9 reasoning interface

The old evidence-key/limitations format and strict Validator workflow are obsolete for the final delivery. The final record is summary-only:

```text
reasoning_format_version: 0.2-draft
generator_version:         0.3.0
prompt_version:            step9_minimal_rewrite_prompt_v0.12
fields:                    reasoning_summary, quality_status, source_record_sha256
```

The final prompt renders confirmed Structured CoC information into at most five natural sentences. Unknown facts are removed before the LLM input rather than narrated as repetitive limitations. Reasoning remains for human-readable inspection, debugging, and optional experiments.

## 6. Final dataset split

```text
Path:    /home/lab/alpamayo_like_dataset/outcome/manifests/dataset_split_v0.1.jsonl
Records: 1864
Clips:   728
Seed:    11
Group:   clip_id
SHA-256: 5fec78f2a754161204386cbf264191611d7d58fbe28803b27e8b9843164774a3
```

Sample counts:

- train: 1491
- validation: 187
- test: 186

Clip counts:

- train: 587
- validation: 75
- test: 66

The split is deterministic, stratified over key dataset dimensions, and grouped exclusively by `clip_id`. `clip_cross_split_count = 0`. Reasoning and static occupancy are not split inputs.

## 7. Final audit and delivery closure

Complete test baseline:

```text
975 passed, 8 subtests passed
```

Final machine audit:

```text
Path:    /home/lab/alpamayo_like_dataset/outcome/reports/final_dataset_audit_v0.1.json
SHA-256: f92df2c3211dab887e8478b070013cedd0ad6418c2e9856cd68d05aa0c6f4a18
Status:  PASS_WITH_WARNINGS
Records: 1864
Clips:   728
Errors:  0
Warnings:1
```

Verified checks include:

- Sample and split counts and exact Anchor-set closure;
- Sample Manifest and split Contract hashes;
- JSON Schema validation;
- 22,368 image references, zero missing images;
- relative, non-escaping image paths;
- 29,824 Ego-history points and zero non-finite values;
- no forbidden model-input leakage terms;
- embedded provenance hashes;
- zero Clip cross-split leakage;
- current-version human-review Bundle and Decision;
- hashes for the review Bundle, Decision, overview image, and synchronized video.

Human review:

```text
Bundles:   1
Completed: 1
Pass:      1
Pending:   0
Stale:     0
Fail:      0
```

Non-blocking warning:

- `rare_class_missing_from_split`: dimension `lateral`, class `turn_left`, global 7, split `test` count 0

The rare `turn_left` absence in test is accepted because the global count is only seven and Clip integrity takes precedence over forcing class presence.

Final closure files:

```text
/home/lab/alpamayo_like_dataset/outcome/reports/final_dataset_audit_v0.1.json              f92df2c3211dab887e8478b070013cedd0ad6418c2e9856cd68d05aa0c6f4a18
/home/lab/alpamayo_like_dataset/outcome/reports/final_dataset_statistics_v0.1.json              77c5cb56c12c892c7f2e0e572612434abc69b4409f86e0f1d900be5e61988b6f
/home/lab/alpamayo_like_dataset/outcome/reports/final_dataset_delivery_summary_v0.1.md           d9bc75fcb853216ccc540bf3bcccd79de779dee895062bf3cd45ac8662bdfb23
/home/lab/alpamayo_like_dataset/outcome/manifests/final_dataset_contract_v0.1.json     4f646b1091f62e35ba26b5e98cfca9aac9ced9a31c3d825255480514f0c3e651
```

## 8. Current distributions in the final Sample Manifest

### Driving lateral
- `change_lane_left`: 62
- `change_lane_right`: 56
- `keep_direction`: 1679
- `turn_left`: 7
- `turn_right`: 28
- `unknown`: 32

### Driving longitudinal
- `accelerate`: 356
- `decelerate`: 352
- `maintain_speed`: 856
- `stop`: 165
- `unknown`: 135

### Navigation
- `left`: 42
- `right`: 59
- `straight`: 1549
- `unknown`: 214

### Road Context
- `intersection`: 133
- `intersection_approach`: 582
- `lane_following`: 1142
- `unknown`: 7

### Quality

Meta-action:
- `unknown`: 166
- `usable`: 1698

Navigation:
- `unknown`: 214
- `usable`: 1650

Scene Facts:
- `unknown`: 313
- `usable`: 1551

Structured CoC:
- `partial`: 558
- `unknown`: 166
- `usable`: 1140

Reasoning:
- `partial`: 558
- `unknown`: 166
- `usable`: 1140

## 9. Production entry points

```bash
cd /home/lab/alpamayo_like_dataset/dataset_tools || return

python3 -m pytest -q
python3 -m step10.build_sample_manifest --force
python3 -m step11.build_dataset_split --force
python3 -u -m step12.audit_dataset --force
```

Human review for a sample:

```bash
python3 -m step12.review_sample --split test --seed 12 --force
```

Do not rebuild Steps 10 or 11 casually: rebuilding Step 10 changes its output hash and requires rechecking Step 11 membership, the human-review Bundle, and Step 12 Contract closure.

## 10. Formal output map

```text
outcome/
├── annotations/v0.1-draft/
│   ├── candidate_anchors.jsonl
│   ├── keyframes.jsonl
│   ├── meta_actions_v0.2.jsonl
│   ├── navigation.jsonl
│   ├── scene_facts.jsonl
│   ├── structured_causality.jsonl
│   └── reasoning.jsonl
├── manifests/
│   ├── sample_manifest_v0.1.jsonl
│   ├── sample_manifest_contract_v0.1.json
│   ├── dataset_split_v0.1.jsonl
│   ├── dataset_split_contract_v0.1.json
│   └── final_dataset_contract_v0.1.json
├── reports/
│   ├── sample_manifest_summary_v0.1.json
│   ├── dataset_split_summary_v0.1.json
│   ├── final_dataset_audit_v0.1.json
│   ├── final_dataset_statistics_v0.1.json
│   ├── final_dataset_delivery_summary_v0.1.md
│   └── step12_review/
├── schemas/
│   ├── sample_manifest_schema_v0.1-draft.json
│   ├── dataset_split_schema_v0.1-draft.json
│   └── final_dataset_audit_schema_v0.1-draft.json
└── backups/
```

## 11. New-conversation quick start

When these three documents are provided in a new conversation:

1. Treat Step 0-12 as complete and frozen.
2. Do not propose restarting Step 10, Step 11, or Step 12.
3. Use the final Contract and audit as the delivery source of truth.
4. If asked to develop training code, read only `sample_manifest_v0.1.jsonl` plus raw image files during training; use `dataset_split_v0.1.jsonl` for partition membership.
5. Keep the default structured-only view and optional reasoning-assisted experiment separate.
6. Preserve Clip-grouped splits and all leakage boundaries.
7. Ask the user only for a genuinely new decision, not for project history already contained here.

## 12. Next development boundary

The dataset-production route is closed. The normal next phase is model-training and evaluation development, not further automatic-label redesign. Training work must preserve the frozen Sample Manifest and split contracts, report which training view is used, and avoid introducing hidden joins to Step 4-9 artifacts. Any future dataset expansion should rerun the established pipeline and Step 12 closure rather than changing frozen semantics merely because the data volume grows.
