#!/usr/bin/env python3
"""Run the AlpaSim dataset production pipeline from Step 1 through Step 12.

Step 0 is represented by repository/path preflight. Step 2 is a shared reader
library and is represented by import preflight. All record counts and identities
continue to flow through formal upstream artifacts and contracts.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

PROJECT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class PipelineStage:
    step: int
    name: str
    description: str
    command: tuple[str, ...] | None = None
    outputs: tuple[str, ...] = ()
    force_supported: bool = False
    force_extra: tuple[str, ...] = ("--force",)


STAGES: tuple[PipelineStage, ...] = (
    PipelineStage(0, "preflight", "Validate repository paths and configured roots."),
    PipelineStage(
        1, "clip_manifest", "Build the Clip Manifest and aggregate summary.",
        (sys.executable, "-u", "-m", "step1.clip_manifest"),
        ("manifests/clips_v0.1.jsonl", "reports/clip_manifest_summary_v0.1.json"), True,
    ),
    PipelineStage(
        1, "clip_schema", "Generate the frozen Clip Manifest schema document.",
        (sys.executable, "-u", "-m", "step1.clip_schema"),
        ("schemas/clip_schema.md",), False,
    ),
    PipelineStage(2, "reader_preflight", "Import the shared Step 2 reader modules."),
    PipelineStage(
        3, "candidate_anchors", "Build Candidate Anchors and their contract.",
        (sys.executable, "-u", "-m", "step3.candidate_anchors"),
        ("annotations/v0.1-draft/candidate_anchors.jsonl", "manifests/candidate_anchor_contract_v0.1.json"), True,
    ),
    PipelineStage(
        4, "meta_actions", "Regenerate Step 4 features and build frozen Meta-actions.",
        (sys.executable, "-u", "-m", "step4.build_meta_actions_v02"),
        ("annotations/v0.1-draft/meta_actions_v0.2.jsonl", "manifests/meta_action_contract_v0.2.json"), True,
    ),
    PipelineStage(
        5, "keyframes", "Detect events, deduplicate them, and select Keyframes.",
        (sys.executable, "-u", "-m", "step5.build_keyframes_v01"),
        ("annotations/v0.1-draft/keyframes.jsonl", "manifests/keyframe_contract_v0.1.json"), True,
    ),
    PipelineStage(
        6, "navigation", "Build all frozen Navigation stages.",
        (sys.executable, "-u", "-m", "step6.build_navigation_v01"),
        ("annotations/v0.1-draft/navigation.jsonl",), True,
    ),
    PipelineStage(
        7, "scene_facts", "Build all eight Step 7 Scene-Fact stages.",
        (sys.executable, "-u", "-m", "step7.build_step7"),
        ("annotations/v0.1-draft/scene_facts.jsonl",), False,
    ),
    PipelineStage(
        8, "structured_coc", "Build Structured CoC and its contract.",
        (sys.executable, "-u", "-m", "step8.build_step8"),
        ("annotations/v0.1-draft/structured_causality.jsonl", "manifests/structured_causality_contract_v0.1.json"), True,
    ),
    PipelineStage(
        9, "reasoning", "Generate local LLM reasoning with checkpoint support.",
        (sys.executable, "-u", "-m", "step9.run"),
        ("annotations/v0.1-draft/reasoning.jsonl", "manifests/reasoning_contract_v0.1.json"), True,
        ("--force", "--reset-checkpoint"),
    ),
    PipelineStage(
        9, "reasoning_audit", "Audit Step 9 output, hashes, checkpoint, and format.",
        (sys.executable, "-u", "-m", "step9.audit_production"),
        ("reports/step9_local_llm/production_audit_v02.json",), False,
    ),
    PipelineStage(
        10, "sample_manifest", "Build the self-contained Sample Manifest.",
        (sys.executable, "-u", "-m", "step10.build_sample_manifest"),
        ("manifests/sample_manifest_v0.1.jsonl", "manifests/sample_manifest_contract_v0.1.json"), True,
    ),
    PipelineStage(
        11, "dataset_split", "Build the deterministic Clip-grouped split.",
        (sys.executable, "-u", "-m", "step11.build_dataset_split"),
        ("manifests/dataset_split_v0.1.jsonl", "manifests/dataset_split_contract_v0.1.json"), True,
    ),
    PipelineStage(
        12, "final_audit", "Run final machine and human-review freshness audit.",
        (sys.executable, "-u", "-m", "step12.audit_dataset"),
        ("reports/final_dataset_audit_v0.1.json", "manifests/final_dataset_contract_v0.1.json"), True,
    ),
)


def duration_text(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def select_stages(from_step: int, to_step: int) -> tuple[PipelineStage, ...]:
    if from_step > to_step:
        raise ValueError("--from-step must not be greater than --to-step")
    return tuple(stage for stage in STAGES if from_step <= stage.step <= to_step)


def resolve_roots(
    dataset_root: Path | None,
    outcome_root: Path | None,
) -> tuple[Path, Path]:
    """Resolve CLI overrides without importing project_paths too early."""
    if dataset_root is None or outcome_root is None:
        paths = importlib.import_module("project_paths")
        if dataset_root is None:
            dataset_root = Path(paths.DATASET_RAW_ROOT)
        if outcome_root is None:
            outcome_root = Path(paths.DATASET_OUTCOME_ROOT)
    data_root = Path(dataset_root).expanduser().resolve()
    product_root = Path(outcome_root).expanduser().resolve()
    if not data_root.is_dir():
        raise RuntimeError(f"raw dataset root is not a directory: {data_root}")
    if product_root == data_root or product_root.is_relative_to(data_root):
        raise RuntimeError(
            "outcome root must be separate from and outside the raw dataset root: "
            f"dataset={data_root}, outcome={product_root}"
        )
    product_root.mkdir(parents=True, exist_ok=True)
    return data_root, product_root


def pipeline_environment(data_root: Path, outcome_root: Path) -> dict[str, str]:
    """Build the environment inherited by every Step and nested subprocess."""
    environment = os.environ.copy()
    environment["DATASET_RAW_ROOT"] = str(data_root)
    environment["DATASET_OUTCOME_ROOT"] = str(outcome_root)
    return environment


def run_internal(stage: PipelineStage, data_root: Path, outcome_root: Path) -> None:
    if stage.name == "preflight":
        if Path.cwd().resolve() != PROJECT_DIR:
            raise RuntimeError(f"run from dataset_tools root: {PROJECT_DIR}")
        if not (PROJECT_DIR / "project_paths.py").is_file():
            raise RuntimeError("project_paths.py is missing")
        print(f"data root: {data_root}")
        print(f"outcome root: {outcome_root}")
        return
    if stage.name == "reader_preflight":
        for module in ("step2.clip_reader", "step2.temporal_index", "step2.coordinate_utils", "step2.vector_map_reader"):
            importlib.import_module(module)
            print(f"imported: {module}")
        return
    raise RuntimeError(f"unknown internal stage: {stage.name}")


def command_for(stage: PipelineStage, force: bool) -> tuple[str, ...] | None:
    if stage.command is None:
        return None
    if force and stage.force_supported:
        return stage.command + stage.force_extra
    return stage.command


def validate_outputs(stage: PipelineStage, outcome_root: Path) -> None:
    missing = [str(outcome_root / rel) for rel in stage.outputs if not (outcome_root / rel).is_file()]
    if missing:
        raise RuntimeError(f"{stage.name} completed but expected outputs are missing: {missing}")
    for rel in stage.outputs:
        path = outcome_root / rel
        if path.suffix == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise RuntimeError(f"JSON output root is not an object: {path}")
        elif path.suffix == ".jsonl":
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if line.strip():
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise RuntimeError(f"JSONL row is not an object: {path}:{line_number}")
    if stage.outputs:
        print(f"validated outputs: {len(stage.outputs)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Rebuild and overwrite all selected production outputs. Step 9 also resets its checkpoint.")
    parser.add_argument("--dry-run", action="store_true", help="Print the selected execution plan without running it.")
    parser.add_argument(
        "--dataset-root", type=Path, default=None, metavar="PATH",
        help="Raw test_clip_* root. Overrides DATASET_RAW_ROOT for the full process tree.",
    )
    parser.add_argument(
        "--outcome-root", type=Path, default=None, metavar="PATH",
        help="Formal product root. Overrides DATASET_OUTCOME_ROOT for the full process tree.",
    )
    parser.add_argument("--from-step", type=int, choices=range(0, 13), default=0, metavar="N")
    parser.add_argument("--to-step", type=int, choices=range(0, 13), default=12, metavar="N")
    parser.add_argument(
        "--require-human-review", action="store_true",
        help="Make Step 12 require completed, fresh human reviews for formal delivery.",
    )
    parser.add_argument("--list-stages", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_stages:
        for index, stage in enumerate(STAGES, 1):
            kind = "internal" if stage.command is None else "command"
            print(f"{index:02d}. Step {stage.step}: {stage.name} [{kind}] - {stage.description}")
        return 0
    try:
        selected = select_stages(args.from_step, args.to_step)
    except ValueError as error:
        build_parser().error(str(error))
    if not selected:
        build_parser().error("no stages selected")

    data_root, outcome_root = resolve_roots(args.dataset_root, args.outcome_root)
    child_environment = pipeline_environment(data_root, outcome_root)
    os.environ.update({
        "DATASET_RAW_ROOT": str(data_root),
        "DATASET_OUTCOME_ROOT": str(outcome_root),
    })
    print(f"Pipeline stages selected: {len(selected)}")
    print(f"Step range: {args.from_step} through {args.to_step}")
    print(f"Raw dataset root: {data_root}")
    print(f"Outcome root: {outcome_root}")
    print(f"Force: {args.force}")
    print(f"Dry run: {args.dry_run}")
    print(f"Require human review: {args.require_human_review}")
    started = time.monotonic()
    timings: list[tuple[str, float]] = []

    for position, stage in enumerate(selected, 1):
        command = command_for(stage, args.force)
        if command is not None and stage.name == "final_audit" and args.require_human_review:
            command = command + ("--require-human-review",)
        print("\n" + "=" * 88)
        print(f"PIPELINE {position}/{len(selected)} | Step {stage.step} | {stage.name}")
        print(stage.description)
        print("command:", "<internal preflight>" if command is None else " ".join(command))
        print("=" * 88, flush=True)
        if args.dry_run:
            timings.append((stage.name, 0.0))
            continue
        stage_started = time.monotonic()
        if command is None:
            run_internal(stage, data_root, outcome_root)
        else:
            completed = subprocess.run(
                command,
                cwd=PROJECT_DIR,
                env=child_environment,
                check=False,
            )
            if completed.returncode != 0:
                print(f"ERROR: Step {stage.step} {stage.name} failed with exit code {completed.returncode}", file=sys.stderr)
                return completed.returncode or 1
            validate_outputs(stage, outcome_root)
        elapsed = time.monotonic() - stage_started
        timings.append((stage.name, elapsed))
        print(f"completed: {stage.name} in {duration_text(elapsed)}", flush=True)

    total = time.monotonic() - started
    print("\nPIPELINE SUMMARY")
    for name, elapsed in timings:
        print(f"- {name}: {duration_text(elapsed)}")
    print(f"total: {duration_text(total)}")
    if args.to_step < 12:
        print("PASS: selected pipeline range completed; final delivery audit was not requested.")
    else:
        print("PASS: full dataset pipeline completed through Step 12.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
