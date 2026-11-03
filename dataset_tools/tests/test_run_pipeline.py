from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_pipeline as target


def test_stage_order_covers_full_project_flow():
    assert tuple(stage.step for stage in target.STAGES) == (0, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 10, 11, 12)
    assert target.STAGES[-1].name == "final_audit"


def test_select_stages_keeps_multiple_stages_within_same_step():
    selected = target.select_stages(9, 9)
    assert tuple(stage.name for stage in selected) == ("reasoning", "reasoning_audit")


def test_select_stages_rejects_reverse_range():
    with pytest.raises(ValueError, match="from-step"):
        target.select_stages(8, 7)


def test_force_is_only_propagated_where_supported():
    step8 = next(stage for stage in target.STAGES if stage.name == "structured_coc")
    step7 = next(stage for stage in target.STAGES if stage.name == "scene_facts")
    step9 = next(stage for stage in target.STAGES if stage.name == "reasoning")
    assert target.command_for(step8, True)[-1] == "--force"
    assert "--force" not in target.command_for(step7, True)
    assert target.command_for(step9, True)[-2:] == ("--force", "--reset-checkpoint")


def test_dry_run_never_starts_subprocess(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(target, "resolve_roots", lambda dataset_root, outcome_root: (tmp_path, tmp_path / "outcome"))
    monkeypatch.setattr(target.subprocess, "run", lambda *a, **k: pytest.fail("subprocess must not run"))
    assert target.main(("--from-step", "8", "--to-step", "9", "--dry-run")) == 0
    output = capsys.readouterr().out
    assert "structured_coc" in output
    assert "reasoning_audit" in output


def test_failure_stops_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(target, "resolve_roots", lambda dataset_root, outcome_root: (tmp_path, tmp_path / "outcome"))
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=7)
    monkeypatch.setattr(target.subprocess, "run", fake_run)
    assert target.main(("--from-step", "8", "--to-step", "10", "--force")) == 7
    assert len(calls) == 1


def test_validate_outputs_parses_json_and_jsonl(tmp_path):
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests" / "a.json").write_text('{"ok": true}\n', encoding="utf-8")
    (tmp_path / "manifests" / "b.jsonl").write_text('{"id": 1}\n', encoding="utf-8")
    stage = target.PipelineStage(1, "x", "x", outputs=("manifests/a.json", "manifests/b.jsonl"))
    target.validate_outputs(stage, tmp_path)


def test_cli_roots_are_exported_to_child_process(monkeypatch, tmp_path):
    raw = tmp_path / "raw"
    outcome = tmp_path / "products"
    raw.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(target.subprocess, "run", fake_run)
    assert target.main((
        "--from-step", "8", "--to-step", "8",
        "--dataset-root", str(raw),
        "--outcome-root", str(outcome),
    )) == 7
    assert calls[0][1]["env"]["DATASET_RAW_ROOT"] == str(raw.resolve())
    assert calls[0][1]["env"]["DATASET_OUTCOME_ROOT"] == str(outcome.resolve())


def test_resolve_roots_rejects_outcome_inside_raw_data(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    with pytest.raises(RuntimeError, match="outside the raw dataset root"):
        target.resolve_roots(raw, raw / "outcome")


def test_human_review_flag_only_reaches_final_audit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        target,
        "resolve_roots",
        lambda dataset_root, outcome_root: (tmp_path, tmp_path / "outcome"),
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(target.subprocess, "run", fake_run)
    assert target.main((
        "--from-step", "12", "--to-step", "12",
        "--require-human-review",
    )) == 7
    final = next(stage for stage in target.STAGES if stage.name == "final_audit")
    assert calls == [final.command + ("--require-human-review",)]

