from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .config import Step9Config
from .contract import PROMPT_VERSION, canonical_json, read_input_records, source_record_sha256
from .format_check import check_response_format
from .ollama_client import OllamaClient
from .prompt import build_evidence_package

TRIAL_VERSION = "step9_local_trial_v0.2"
DEFAULT_TRIAL_SIZE = 24


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def trial_tags(package: Mapping[str, Any]) -> set[str]:
    tags = {f"quality:{package['quality_status']}"}
    links = package.get("links", ())
    rules = {str(link["rule_id"]) for link in links}
    relations = {str(link["relation"]) for link in links}
    tags.update(f"rule:{rule}" for rule in rules)
    tags.update(f"relation:{relation}" for relation in relations)
    actor_count = sum(link.get("source_type") == "actor_state" for link in links)
    tags.add(
        "actors:multiple" if actor_count >= 2 else "actors:single" if actor_count == 1 else "actors:none"
    )
    return tags


def select_trial_rows(rows: list[dict[str, Any]], *, limit: int = DEFAULT_TRIAL_SIZE) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("trial limit must be positive")
    packages = [build_evidence_package(row) for row in rows]
    required = {
        "quality:usable",
        "quality:partial",
        "quality:unknown",
        "relation:aligns_with",
        "relation:stage_consistent",
        "relation:insufficient_evidence",
        "relation:supports",
        "actors:none",
        "actors:single",
        "actors:multiple",
    }
    selected: list[int] = []
    selected_set: set[int] = set()
    uncovered = set(required)
    while uncovered and len(selected) < limit:
        best_index = None
        best_gain: set[str] = set()
        for index, package in enumerate(packages):
            if index in selected_set:
                continue
            gain = trial_tags(package) & uncovered
            if len(gain) > len(best_gain):
                best_index = index
                best_gain = gain
        if best_index is None or not best_gain:
            break
        selected.append(best_index)
        selected_set.add(best_index)
        uncovered -= best_gain
    for index in range(len(rows)):
        if len(selected) >= limit:
            break
        if index not in selected_set:
            selected.append(index)
            selected_set.add(index)
    return [rows[index] for index in selected]


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Run an isolated, stratified Step 9 local-model trial.")
    value.add_argument("--data-root", type=Path, default=None)
    value.add_argument("--limit", type=int, default=DEFAULT_TRIAL_SIZE)
    value.add_argument("--force", action="store_true")
    return value


def main() -> int:
    args = parser().parse_args()
    config = Step9Config.from_environment(args.data_root)
    rows, input_contract = read_input_records(config.input_path, config.input_contract_path)
    selected = select_trial_rows(rows, limit=args.limit)
    packages = [build_evidence_package(row) for row in selected]
    trial_root = config.work_root / "trial"
    output_path = trial_root / "trial_results.jsonl"
    report_path = trial_root / "trial_report.json"
    selection_path = trial_root / "trial_selection.json"
    if any(path.exists() for path in (output_path, report_path, selection_path)) and not args.force:
        raise SystemExit("Trial outputs already exist; use --force")

    client = OllamaClient(config)
    metadata = client.validate_model()
    started = time.monotonic()
    results = []
    failures = []
    total_prompt_tokens = 0
    total_output_tokens = 0
    for index, (source, package) in enumerate(zip(selected, packages), 1):
        last_error = None
        for attempt in range(1, config.max_attempts + 1):
            try:
                response, envelope = client.generate(package, attempt=attempt, validation_feedback=last_error)
                check_response_format(response, package)
                results.append({
                    "anchor_id": source["anchor_id"],
                    "clip_id": source["clip_id"],
                    "anchor_ns": source["anchor_ns"],
                    "quality_status": package["quality_status"],
                    "trial_tags": sorted(trial_tags(package)),
                    "response": response,
                    "source_record_sha256": source_record_sha256(source),
                    "attempt": attempt,
                    "prompt_eval_count": envelope.get("prompt_eval_count", 0),
                    "eval_count": envelope.get("eval_count", 0),
                    "total_duration_ns": envelope.get("total_duration", 0),
                })
                total_prompt_tokens += int(envelope.get("prompt_eval_count", 0) or 0)
                total_output_tokens += int(envelope.get("eval_count", 0) or 0)
                last_error = None
                break
            except Exception as error:
                last_error = str(error)
        if last_error is not None:
            failures.append({"anchor_id": source["anchor_id"], "error": last_error})
        print(
            f"[Step 9 Trial] {index}/{len(selected)} | generated {len(results)} | "
            f"generation_errors {len(failures)}",
            flush=True,
        )

    elapsed = time.monotonic() - started
    selected_tags = Counter(tag for package in packages for tag in trial_tags(package))
    selection = {
        "trial_version": TRIAL_VERSION,
        "record_count": len(selected),
        "anchor_ids": [row["anchor_id"] for row in selected],
        "tag_counts": dict(sorted(selected_tags.items())),
        "quality_counts": dict(sorted(Counter(p["quality_status"] for p in packages).items())),
    }
    report = {
        "trial_version": TRIAL_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": config.model,
        "model_details": metadata.get("details", {}),
        "model_modified_at": metadata.get("modified_at"),
        "input_path": str(config.input_path),
        "input_sha256": input_contract["output_sha256"],
        "selected_count": len(selected),
        "generated_count": len(results),
        "generation_error_count": len(failures),
        "first_attempt_generated_count": sum(row["attempt"] == 1 for row in results),
        "failures": failures,
        "elapsed_seconds": elapsed,
        "records_per_second": len(selected) / elapsed if elapsed else 0.0,
        "prompt_tokens": total_prompt_tokens,
        "output_tokens": total_output_tokens,
        "production_outputs_written": False,
        "output_path": str(output_path),
        "selection_path": str(selection_path),
    }
    atomic_write(output_path, "".join(canonical_json(row) + "\n" for row in results))
    atomic_write(selection_path, json.dumps(selection, indent=2, sort_keys=True) + "\n")
    atomic_write(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("trial output:", output_path)
    print("trial report:", report_path)
    print("generated:", len(results))
    print("generation_errors:", len(failures))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
