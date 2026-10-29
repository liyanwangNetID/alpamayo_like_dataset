from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .checkpoint import append_jsonl, load_checkpoint
from .config import Step9Config
from .contract import (
    GENERATOR_VERSION,
    PROMPT_VERSION,
    REASONING_FORMAT_VERSION,
    canonical_json,
    output_schema,
    read_input_records,
    sha256_file,
    source_record_sha256,
    usage_policy,
    validate_schema,
)
from .format_check import check_response_format
from .ollama_client import OllamaClient
from .prompt import build_evidence_package


def output_record(source: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reasoning_format_version": REASONING_FORMAT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "prompt_version": PROMPT_VERSION,
        "anchor_id": source["anchor_id"],
        "clip_id": source["clip_id"],
        "anchor_ns": source["anchor_ns"],
        "reasoning_summary": response["reasoning_summary"],
        "quality_status": source["quality"]["status"],
        "source_record_sha256": source_record_sha256(source),
    }


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Generate Step 9 reasoning locally with Ollama.")
    value.add_argument("--data-root", type=Path, default=None)
    value.add_argument("--limit", type=int, default=None)
    value.add_argument("--dry-run", action="store_true")
    value.add_argument("--force", action="store_true")
    value.add_argument("--reset-checkpoint", action="store_true")
    return value


def main() -> int:
    args = parser().parse_args()
    config = Step9Config.from_environment(args.data_root)
    rows, input_contract = read_input_records(config.input_path, config.input_contract_path)
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be positive")
        rows = rows[: args.limit]
    packages = [build_evidence_package(row) for row in rows]
    if args.dry_run:
        print("[Step 9] Dry run")
        print("input:", config.input_path)
        print("records:", len(rows))
        print("quality:", dict(sorted(Counter(x["quality_status"] for x in packages).items())))
        print("model:", config.model)
        return 0

    if args.reset_checkpoint:
        config.checkpoint_path.unlink(missing_ok=True)
        config.rejection_path.unlink(missing_ok=True)
    existing = load_checkpoint(config.checkpoint_path)
    client = OllamaClient(config)
    metadata = client.validate_model()
    details = metadata.get("details") or {}
    manifest = {
        "model": config.model,
        "model_details": details,
        "model_modified_at": metadata.get("modified_at"),
        "prompt_version": PROMPT_VERSION,
        "num_ctx": config.num_ctx,
        "num_predict": config.num_predict,
        "temperature": config.temperature,
        "seed": config.seed,
        "think": False,
        "input_path": str(config.input_path),
        "input_sha256": input_contract["output_sha256"],
    }
    atomic_write(config.run_manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    started = time.monotonic()
    generated = 0
    generation_errors = 0
    for index, (source, package) in enumerate(zip(rows, packages), 1):
        anchor_id = source["anchor_id"]
        cached = existing.get(anchor_id)
        if cached and cached.get("source_record_sha256") == source_record_sha256(source):
            generated += 1
            continue
        last_error = None
        for attempt in range(1, config.max_attempts + 1):
            try:
                response, _ = client.generate(package, attempt=attempt, validation_feedback=last_error)
                check_response_format(response, package)
                record = output_record(source, response)
                validate_schema(record, output_schema())
                append_jsonl(config.checkpoint_path, record)
                generated += 1
                last_error = None
                break
            except Exception as error:
                last_error = str(error)
        if last_error is not None:
            generation_errors += 1
            append_jsonl(config.rejection_path, {"anchor_id": anchor_id, "error": last_error})
        if index == len(rows) or index % 25 == 0:
            elapsed = time.monotonic() - started
            rate = index / elapsed if elapsed else 0.0
            print(
                f"[Step 9] {index}/{len(rows)} | generated {generated} | "
                f"generation_errors {generation_errors} | rate {rate:.2f}/s",
                flush=True,
            )

    complete = load_checkpoint(config.checkpoint_path)
    ordered = [
        complete[source["anchor_id"]]
        for source in rows
        if source["anchor_id"] in complete
        and complete[source["anchor_id"]].get("source_record_sha256") == source_record_sha256(source)
    ]
    if generation_errors or len(ordered) != len(rows):
        print(
            f"ERROR: incomplete Step 9 run: generated={len(ordered)} "
            f"expected={len(rows)} generation_errors={generation_errors}",
            file=sys.stderr,
        )
        return 2
    if config.output_path.exists() and not args.force:
        print(f"ERROR: output exists; use --force: {config.output_path}", file=sys.stderr)
        return 2

    schema = output_schema()
    Draft202012Validator.check_schema(schema)
    atomic_write(config.output_path, "".join(canonical_json(row) + "\n" for row in ordered))
    atomic_write(config.schema_path, json.dumps(schema, indent=2, sort_keys=True) + "\n")
    output_sha = sha256_file(config.output_path)
    schema_sha = sha256_file(config.schema_path)
    quality = Counter(row["quality_status"] for row in ordered)
    summary = {
        "summary_format_version": "0.1",
        "record_count": len(ordered),
        "quality_status_counts": dict(sorted(quality.items())),
        "output_path": str(config.output_path),
        "output_sha256": output_sha,
        "schema_path": str(config.schema_path),
        "schema_sha256": schema_sha,
        "model": config.model,
        "model_details": details,
        "prompt_version": PROMPT_VERSION,
        "usage_policy": usage_policy(),
        "elapsed_seconds": time.monotonic() - started,
    }
    atomic_write(config.summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    contract = {
        "contract_version": "0.1",
        "producer_step": 9,
        "record_count": len(ordered),
        "reasoning_format_version": REASONING_FORMAT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": config.model,
        "model_details": details,
        "model_modified_at": metadata.get("modified_at"),
        "input_path": str(config.input_path),
        "input_sha256": input_contract["output_sha256"],
        "output_path": str(config.output_path),
        "output_sha256": output_sha,
        "schema_path": str(config.schema_path),
        "schema_sha256": schema_sha,
        "summary_path": str(config.summary_path),
        "reasoning_is_control_input": False,
        "usage_policy": usage_policy(),
    }
    atomic_write(config.contract_path, json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print("PASS: Step 9 local reasoning generated, format-checked, summarized, and contracted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
