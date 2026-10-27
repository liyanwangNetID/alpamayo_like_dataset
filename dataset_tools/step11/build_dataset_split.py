#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from project_paths import MANIFEST_ROOT, REPORT_ROOT, SCHEMA_ROOT
from step11.schema import BUILDER_VERSION, FORMAT_VERSION, write_schema, dataset_split_schema
from step11.splitter import SPLIT_NAMES, SPLIT_RATIOS, SPLIT_SEED, deterministic_grouped_split, sample_features

SAMPLE_MANIFEST = MANIFEST_ROOT / "sample_manifest_v0.1.jsonl"
SAMPLE_CONTRACT = MANIFEST_ROOT / "sample_manifest_contract_v0.1.json"
OUTPUT = MANIFEST_ROOT / "dataset_split_v0.1.jsonl"
CONTRACT = MANIFEST_ROOT / "dataset_split_contract_v0.1.json"
SUMMARY = REPORT_ROOT / "dataset_split_summary_v0.1.json"
SCHEMA = SCHEMA_ROOT / "dataset_split_schema_v0.1-draft.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def atomic_write(path: Path, text: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing output: {path}; use --force")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-manifest", type=Path, default=SAMPLE_MANIFEST)
    parser.add_argument("--sample-contract", type=Path, default=SAMPLE_CONTRACT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--contract-output", type=Path, default=CONTRACT)
    parser.add_argument("--summary-output", type=Path, default=SUMMARY)
    parser.add_argument("--schema-output", type=Path, default=SCHEMA)
    parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_jsonl(args.sample_manifest)
    sample_contract = json.loads(args.sample_contract.read_text(encoding="utf-8"))
    if len(rows) != int(sample_contract["record_count"]):
        raise ValueError("Sample Manifest count does not match its Contract")
    sample_hash = file_sha256(args.sample_manifest)
    if sample_hash != sample_contract["output_sha256"]:
        raise ValueError("Sample Manifest SHA-256 does not match its Contract")

    clip_assignments = deterministic_grouped_split(rows, seed=args.seed)
    schema = dataset_split_schema()
    validator = Draft202012Validator(schema)
    output_rows = []
    anchor_ids = set()
    clip_to_split = {}
    sample_counts = Counter()
    clip_counts = Counter()
    feature_counts = {name: Counter() for name in SPLIT_NAMES}

    for row in rows:
        anchor_id = str(row["anchor_id"])
        clip_id = str(row["clip_id"])
        if anchor_id in anchor_ids:
            raise ValueError(f"duplicate Sample Manifest anchor_id: {anchor_id}")
        anchor_ids.add(anchor_id)
        split = clip_assignments[clip_id]
        previous = clip_to_split.setdefault(clip_id, split)
        if previous != split:
            raise RuntimeError(f"Clip crosses splits: {clip_id}")
        output = {"split_format_version": FORMAT_VERSION, "anchor_id": anchor_id, "clip_id": clip_id, "split": split}
        errors = list(validator.iter_errors(output))
        if errors:
            raise ValueError(f"{anchor_id}: split schema error: {errors[0].message}")
        output_rows.append(output)
        sample_counts[split] += 1
        feature_counts[split].update(sample_features(row))
    clip_counts.update(clip_assignments.values())

    total = len(rows)
    output_text = "".join(canonical_json(row) + "\n" for row in output_rows)
    output_hash = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
    write_schema(args.schema_output)
    schema_hash = file_sha256(args.schema_output)

    global_features = Counter()
    for counter in feature_counts.values():
        global_features.update(counter)
    distributions = {}
    for split in SPLIT_NAMES:
        distributions[split] = {
            feature: feature_counts[split][feature]
            for feature in sorted(global_features)
        }
    summary = {
        "summary_version": "0.1",
        "record_count": total,
        "unique_anchor_count": len(anchor_ids),
        "unique_clip_count": len(clip_assignments),
        "split_sample_counts": dict(sample_counts),
        "split_clip_counts": dict(clip_counts),
        "target_ratios": SPLIT_RATIOS,
        "actual_ratios": {name: sample_counts[name] / total for name in SPLIT_NAMES},
        "absolute_ratio_errors": {name: abs(sample_counts[name] / total - SPLIT_RATIOS[name]) for name in SPLIT_NAMES},
        "maximum_absolute_ratio_error": max(abs(sample_counts[name] / total - SPLIT_RATIOS[name]) for name in SPLIT_NAMES),
        "feature_counts": distributions,
        "clip_cross_split_count": 0,
        "reasoning_used_for_split": False,
        "static_occupancy_used": False,
        "output_path": str(args.output),
        "output_sha256": output_hash,
        "schema_path": str(args.schema_output),
        "schema_sha256": schema_hash,
    }
    contract = {
        "contract_version": "0.1",
        "producer_step": 11,
        "split_format_version": FORMAT_VERSION,
        "builder_version": BUILDER_VERSION,
        "split_seed": args.seed,
        "group_key": "clip_id",
        "target_ratios": SPLIT_RATIOS,
        "record_count": total,
        "clip_count": len(clip_assignments),
        "output_path": str(args.output),
        "output_sha256": output_hash,
        "schema_path": str(args.schema_output),
        "schema_sha256": schema_hash,
        "summary_path": str(args.summary_output),
        "sample_manifest_path": str(args.sample_manifest),
        "sample_manifest_sha256": sample_hash,
        "sample_manifest_contract_path": str(args.sample_contract),
        "sample_manifest_contract_sha256": file_sha256(args.sample_contract),
        "leakage_controls": {
            "clip_group_exclusive": True,
            "reasoning_used_for_split": False,
            "static_occupancy_used": False,
            "future_data_used": False,
        },
        "training_views": {
            "structured_only": "same_split_assignment",
            "reasoning_assisted": "same_split_assignment",
        },
    }
    atomic_write(args.output, output_text, args.force)
    atomic_write(args.summary_output, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.force)
    atomic_write(args.contract_output, json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.force)
    print("Step 11 deterministic clip-grouped split")
    print("records:", total)
    print("clips:", len(clip_assignments))
    print("sample counts:", dict(sample_counts))
    print("clip counts:", dict(clip_counts))
    print("actual ratios:", {name: round(sample_counts[name] / total, 6) for name in SPLIT_NAMES})
    print("maximum ratio error:", summary["maximum_absolute_ratio_error"])
    print("sha256:", output_hash)
    print("output:", args.output)
    print("summary:", args.summary_output)
    print("contract:", args.contract_output)
    print("PASS: Step 11 split built with Clip exclusivity and deterministic stratification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
