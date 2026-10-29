from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .checkpoint import load_checkpoint
from .config import Step9Config
from .contract import (
    GENERATOR_VERSION,
    PROMPT_VERSION,
    REASONING_FORMAT_VERSION,
    output_schema,
    read_input_records,
    sha256_file,
    source_record_sha256,
)
from .format_check import check_response_format


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: row must be an object")
            rows.append(value)
    return rows


def sentence_count(text: str) -> int:
    import re
    return len([item for item in re.split(r"(?<=[.!?])\\s+", text.strip()) if item])


def select_review_rows(rows: list[dict[str, Any]], per_stratum: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["quality_status"], sentence_count(row["reasoning_summary"]))].append(row)
    selected = []
    for key in sorted(groups, key=str):
        for row in groups[key][:per_stratum]:
            selected.append({
                "anchor_id": row["anchor_id"],
                "clip_id": row["clip_id"],
                "quality_status": row["quality_status"],
                "reasoning_summary": row["reasoning_summary"],
                "review_stratum": {"quality_status": key[0], "sentence_count": key[1]},
            })
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Step 9 summary-only production artifacts.")
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--review-per-stratum", type=int, default=4)
    args = parser.parse_args()
    if args.review_per_stratum < 1:
        raise SystemExit("--review-per-stratum must be positive")

    config = Step9Config.from_environment(args.data_root)
    sources, input_contract = read_input_records(config.input_path, config.input_contract_path)
    source_by_anchor = {row["anchor_id"]: row for row in sources}
    output_rows = read_jsonl(config.output_path)
    checkpoint = load_checkpoint(config.checkpoint_path)
    schema_file = json.loads(config.schema_path.read_text(encoding="utf-8"))
    summary_file = json.loads(config.summary_path.read_text(encoding="utf-8"))
    contract_file = json.loads(config.contract_path.read_text(encoding="utf-8"))

    errors: list[str] = []
    output_ids = [row.get("anchor_id") for row in output_rows]
    source_ids = [row["anchor_id"] for row in sources]
    if len(output_rows) != len(sources):
        errors.append(f"record count mismatch: output={len(output_rows)} input={len(sources)}")
    if len(set(output_ids)) != len(output_ids):
        errors.append("duplicate anchor_id in reasoning output")
    if output_ids != source_ids:
        errors.append("reasoning output anchor order differs from Step 8 input")
    if len(checkpoint) != len(sources):
        errors.append(f"checkpoint unique count mismatch: {len(checkpoint)} != {len(sources)}")

    schema_validator = Draft202012Validator(output_schema())
    schema_errors = 0
    format_errors = 0
    checkpoint_mismatches = 0
    source_hash_mismatches = 0
    quality_counts = Counter()
    sentence_counts = Counter()
    length_max = 0
    for row in output_rows:
        schema_errors += len(list(schema_validator.iter_errors(row)))
        anchor_id = row.get("anchor_id")
        source = source_by_anchor.get(anchor_id)
        if checkpoint.get(anchor_id) != row:
            checkpoint_mismatches += 1
        if source is None or row.get("source_record_sha256") != source_record_sha256(source):
            source_hash_mismatches += 1
        try:
            check_response_format({"reasoning_summary": row.get("reasoning_summary", "")})
        except Exception:
            format_errors += 1
        quality_counts[row.get("quality_status")] += 1
        count = sentence_count(str(row.get("reasoning_summary", "")))
        sentence_counts[count] += 1
        length_max = max(length_max, len(str(row.get("reasoning_summary", ""))))

    if schema_errors:
        errors.append(f"output schema validation errors: {schema_errors}")
    if format_errors:
        errors.append(f"response format errors: {format_errors}")
    if checkpoint_mismatches:
        errors.append(f"checkpoint/output mismatches: {checkpoint_mismatches}")
    if source_hash_mismatches:
        errors.append(f"source hash mismatches: {source_hash_mismatches}")

    output_sha = sha256_file(config.output_path)
    schema_sha = sha256_file(config.schema_path)
    expected_summary = {
        "record_count": len(output_rows),
        "output_sha256": output_sha,
        "schema_sha256": schema_sha,
        "quality_status_counts": dict(sorted(quality_counts.items())),
    }
    for key, expected in expected_summary.items():
        if summary_file.get(key) != expected:
            errors.append(f"summary {key} mismatch")
    for key, expected in {
        "record_count": len(output_rows),
        "input_sha256": input_contract["output_sha256"],
        "output_sha256": output_sha,
        "schema_sha256": schema_sha,
        "reasoning_format_version": REASONING_FORMAT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "prompt_version": PROMPT_VERSION,
    }.items():
        if contract_file.get(key) != expected:
            errors.append(f"contract {key} mismatch")
    if schema_file != output_schema():
        errors.append("schema file differs from current output_schema()")

    review_rows = select_review_rows(output_rows, args.review_per_stratum)
    review_path = config.work_root / "production_review_sample_v02.jsonl"
    report_path = config.work_root / "production_audit_v02.json"
    review_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in review_rows),
        encoding="utf-8",
    )
    report = {
        "audit_version": "step9_production_audit_v0.2",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "record_count": len(output_rows),
        "unique_anchor_count": len(set(output_ids)),
        "checkpoint_unique_count": len(checkpoint),
        "schema_error_count": schema_errors,
        "format_error_count": format_errors,
        "checkpoint_mismatch_count": checkpoint_mismatches,
        "source_hash_mismatch_count": source_hash_mismatches,
        "quality_status_counts": dict(sorted(quality_counts.items())),
        "sentence_count_distribution": dict(sorted(sentence_counts.items())),
        "maximum_summary_length": length_max,
        "output_path": str(config.output_path),
        "output_sha256": output_sha,
        "schema_path": str(config.schema_path),
        "schema_sha256": schema_sha,
        "summary_path": str(config.summary_path),
        "contract_path": str(config.contract_path),
        "review_sample_path": str(review_path),
        "review_sample_count": len(review_rows),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("audit report:", report_path)
    print("review sample:", review_path)
    print("status:", report["status"])
    print("records:", report["record_count"])
    print("checkpoint:", report["checkpoint_unique_count"])
    print("review samples:", report["review_sample_count"])
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 2
    print("PASS: Step 9 summary-only artifacts, hashes, schema, checkpoint, and format are consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
