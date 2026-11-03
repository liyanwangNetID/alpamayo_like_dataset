# AlpaSim-Like Multicamera Driving Dataset Pipeline

This repository converts recorded AlpaSim multicamera Clips into a self-contained driving-decision dataset. A single entry point runs the complete production workflow:

```bash
cd dataset_tools || return
python3 -u run_pipeline.py \
  --dataset-root /path/to/raw_clips \
  --outcome-root /path/to/dataset_outcome \
  --force
```

The raw-data root and product root are supplied explicitly when the pipeline starts. The repository can therefore be cloned to any filesystem location. Dataset scale is discovered dynamically: Clip counts, Candidate Anchor counts, Keyframe counts, sample membership, split membership, and SHA-256 provenance come from generated artifacts and contracts rather than machine-specific constants.

## Repository layout after `git clone`

```text
alpamayo_like_dataset/
|-- .gitignore       Generated-product and local-file exclusions
|-- dataset_tools/   Step 1-12 implementation, tests, and run_pipeline.py
|-- docs/            Design, data-format, and handoff documentation
|-- requirements.txt Pinned Python dependencies
`-- README.md
```

`outcome/` and `outcome_full/` are examples of local generated-product directories and are ignored by Git. They are not part of a fresh clone. The pipeline creates whichever directory is supplied through `--outcome-root`; the directory name can be different.

There is no required `config/` directory and no dependency on an AlpaSim source-code workspace. The only required AlpaSim input is the recorded raw Clip directory supplied through `--dataset-root`.

## Pipeline stages

```text
Step 0   Repository and path preflight
Step 1   Clip Manifest and Clip Schema
Step 2   Shared reader API import preflight
Step 3   Candidate Anchors
Step 4   Meta-actions
Step 5   Keyframes
Step 6   Navigation
Step 7   Scene Facts
Step 8   Structured CoC
Step 9   Natural-language Reasoning and production audit
Step 10  Self-contained Sample Manifest
Step 11  Clip-grouped train/validation/test split
Step 12  Final automated dataset audit
```

Step 0 and Step 2 are preflight stages rather than data generators. Step 4 through Step 7 retain their ordered internal sub-stages.

## 1. Clone the repository

```bash
git clone <REPOSITORY_URL> alpamayo_like_dataset
cd alpamayo_like_dataset
```

Replace `<REPOSITORY_URL>` with the actual Git remote URL.

## 2. Create the Python environment

Python 3.12 is required; Python 3.12.13 is the version used for the clean-environment validation. This project uses `uv` for environment and package installation. Install `uv` if it is not already available:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Create and activate a repository-local Python 3.12 environment:

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
```

Install the pinned Python dependencies:

```bash
uv pip install -r requirements.txt
```

`uv` environments do not need the `pip` module. Use `uv pip`, not `python3 -m pip`. The committed `requirements.txt` includes the test dependency `pytest`.

The committed dependency set was validated in a fresh `uv` environment with the complete test suite: `994 passed, 4 skipped, 8 subtests passed`.

## 3. Install and configure Ollama

Step 9 uses Ollama through its local HTTP API. The current production settings are:

```text
Endpoint: http://127.0.0.1:11434
Model: qwen3:14b
Expected family: qwen3
Expected parameter size: 14.8B
Expected quantization: Q4_K_M
```

### Install Ollama on Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

If the installer created a system service, enable and start it:

```bash
sudo systemctl enable --now ollama
sudo systemctl status ollama
```

If no system service is available, start Ollama in a separate terminal:

```bash
ollama serve
```

### Download the Step 9 model

```bash
ollama pull qwen3:14b
```

### Verify Ollama before running the pipeline

```bash
ollama -v
ollama ls
curl -s http://127.0.0.1:11434/api/tags
```

`ollama ls` must include `qwen3:14b`. Step 9 validates the model metadata, so an incompatible family, parameter size, or quantization may be rejected.

If Ollama runs at a different endpoint or an explicitly compatible model is required, set the Step 9 overrides before launching the pipeline:

```bash
export STEP9_OLLAMA_BASE_URL=http://127.0.0.1:11434
export STEP9_OLLAMA_MODEL=qwen3:14b
```

Keep the model, endpoint, and prompt configuration unchanged during one production run. If Ollama is unavailable, Step 9 fails and the pipeline stops rather than silently producing an incomplete dataset.

## 4. Prepare the raw Clips

The directory passed to `--dataset-root` must directly contain the Clip directories:

```text
/path/to/raw_clips/
|-- test_clip_001/
|-- test_clip_002/
|-- test_clip_003/
`-- ...
```

Raw data and generated products must remain separate. The product root must not be the raw root or a child of it.

Check the input directory:

```bash
find /path/to/raw_clips \
  -maxdepth 1 \
  -type d \
  -name 'test_clip_*' \
  | sort \
  | head
```

## 5. Run the complete test suite

From the repository root:

```bash
cd dataset_tools || return
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
cd ..
```


The `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` prefix prevents unrelated globally installed pytest plugins from being loaded. This is important on machines whose shell has sourced ROS 2, because ROS packages such as `launch_testing` may otherwise be discovered outside the project virtual environment. Pytest 9 provides the subtests support used by this repository as a built-in plugin, so disabling third-party plugin autoload does not remove the project's subtest coverage.

Do not start a formal production run until the complete suite passes.

## 6. Inspect the execution plan

```bash
cd dataset_tools || return

python3 -u run_pipeline.py \
  --dataset-root /path/to/raw_clips \
  --outcome-root /path/to/dataset_outcome \
  --dry-run
```

The dry run prints the selected stages, effective paths, Python executable, and child commands without generating products.

List the registered stages:

```bash
python3 -u run_pipeline.py --list-stages
```

## 7. Run the complete production pipeline

```bash
cd dataset_tools || return

python3 -u run_pipeline.py \
  --dataset-root /path/to/raw_clips \
  --outcome-root /path/to/dataset_outcome \
  --force
```

The two path parameters are the public configuration interface:

- `--dataset-root` selects the raw Clip directory.
- `--outcome-root` selects the formal product directory.

No machine-local path configuration file is required. Internally, the runner transports the selected roots to Step subprocesses, including the nested Step 4-7 subprocesses.

`--force` is propagated only to stages that support it. Step 9 additionally resets its checkpoint so that reasoning from different Step 8 inputs cannot be mixed.

The pipeline stops immediately if a stage returns a nonzero exit code or if an expected formal product is absent or malformed.

## 8. Run a selected range

Rebuild from Step 7 through Step 12:

```bash
cd /path/to/alpamayo_like_dataset/dataset_tools || return
python3 -u run_pipeline.py \
  --dataset-root /path/to/raw_clips \
  --outcome-root /path/to/dataset_outcome \
  --from-step 7 \
  --force
```

Run only Step 8 through Step 10:

```bash
cd /path/to/alpamayo_like_dataset/dataset_tools || return
python3 -u run_pipeline.py \
  --dataset-root /path/to/raw_clips \
  --outcome-root /path/to/dataset_outcome \
  --from-step 8 \
  --to-step 10 \
  --force
```

A partial run requires valid upstream artifacts and contracts in the selected product root. If the raw Clip set changes, run the full pipeline from Step 0 with `--force`.

## 9. Automated audit and human review

By default, Step 12 performs the automated audit and does not require human review. A small dataset may finish with `PASS_WITH_WARNINGS` when rare classes are absent from one split. Such warnings do not block the automated pipeline.

For formal delivery that requires completed and fresh human reviews:

```bash
cd /path/to/alpamayo_like_dataset/dataset_tools || return
python3 -u run_pipeline.py \
  --dataset-root /path/to/raw_clips \
  --outcome-root /path/to/dataset_outcome \
  --from-step 12 \
  --force \
  --require-human-review
```

In strict mode, missing, pending, stale, invalid, or failed human review blocks delivery.

## 10. Main products

The selected product root is created at runtime and contains:

```text
/path/to/dataset_outcome/
|-- annotations/
|   `-- v0.1-draft/
|-- manifests/
|-- reports/
|-- schemas/
`-- backups/
```

Important final products include:

```text
manifests/sample_manifest_v0.1.jsonl
manifests/sample_manifest_contract_v0.1.json
manifests/dataset_split_v0.1.jsonl
manifests/dataset_split_contract_v0.1.json
manifests/final_dataset_contract_v0.1.json
reports/final_dataset_audit_v0.1.json
reports/final_dataset_statistics_v0.1.json
reports/final_dataset_delivery_summary_v0.1.md
```

Training should read the self-contained Sample Manifest and the Step 11 split. Apart from loading the referenced raw images, training should not runtime-join the Step 4-9 JSONL files.

## 11. Portability

- The repository can live at any filesystem location.
- `run_pipeline.py` derives the repository tools directory from its own file path.
- Raw data and products are selected explicitly through CLI parameters.
- A fresh clone does not require `config/`, `outcome/`, or `outcome_full/`.
- Sample Manifest image references are relative to the raw Clip root.
- Contracts and reports may contain absolute paths as run provenance. On another machine, regenerate products using the new roots instead of reusing old path-bearing contracts.
- Generated products remain outside source control.

## 12. Common failures


### Pytest tries to import ROS 2 `launch_testing`

Run tests with third-party plugin autoload disabled:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
```

Do not add `PyYAML` merely to satisfy a ROS pytest plugin. The dataset repository does not require that plugin; it was discovered from the surrounding shell environment rather than from `requirements.txt`.

### The raw Clip root does not exist

Check that `--dataset-root` is correct and directly contains `test_clip_*` directories.

### Step 8 reports an upstream SHA-256 mismatch

Do not manually edit a contract hash. Rebuild from the earliest changed upstream stage. If the raw Clip set changed, run the complete pipeline with `--force`.

### Step 9 cannot connect to Ollama

Check the service and API:

```bash
sudo systemctl status ollama
curl -s http://127.0.0.1:11434/api/tags
ollama ls
```

Start the service or `ollama serve`, verify `qwen3:14b`, and rerun from Step 9:

```bash
cd /path/to/alpamayo_like_dataset/dataset_tools || return
python3 -u run_pipeline.py \
  --dataset-root /path/to/raw_clips \
  --outcome-root /path/to/dataset_outcome \
  --from-step 9 \
  --force
```

### Step 12 reports rare-class warnings

These warnings can be non-blocking when Clip exclusivity prevents a better split, especially for a small validation dataset. Inspect:

```text
reports/final_dataset_audit_v0.1.json
reports/final_dataset_statistics_v0.1.json
```

### Strict Step 12 reports missing or stale human review

This is expected when `--require-human-review` is used before the current Sample Manifest has been reviewed. Complete fresh review artifacts and rerun Step 12 in strict mode.

## 13. Development rules

- Keep raw data, source code, and formal products separate.
- Do not hard-code Clip counts, Anchor counts, Keyframe counts, split sizes, or dataset-instance hashes.
- Treat upstream JSONL artifacts and contracts as the source of truth.
- Preserve exact Anchor identity across joined stages.
- Run the complete test suite after code changes.
- Do not bypass provenance, schema, hash, leakage, or Clip-exclusivity checks.
- Fix the earliest responsible stage, then rebuild every dependent stage.

## Additional documentation

See `docs/` for the project handoff, Clip format, Scene-Fact design, and deeper semantic and evidence-boundary documentation. This README is the operational guide for setting up and running the project on a new machine.
