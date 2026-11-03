from pathlib import Path

import project_paths


def test_repository_and_outcome_paths_are_portable_and_separated():
    repository = Path(project_paths.__file__).resolve().parents[1]
    assert project_paths.DATASET_REPOSITORY_ROOT == repository
    assert project_paths.DATASET_TOOLS_ROOT == repository / "dataset_tools"
    assert project_paths.DATASET_OUTCOME_ROOT == repository / "outcome"

    # The real raw Clip root is supplied by run_pipeline.py --dataset-root.
    # Importing project_paths without that CLI context must remain safe and
    # must not assume one machine-specific absolute path.
    assert project_paths.DATASET_RAW_ROOT == (
        repository / ".dataset_raw_root_unconfigured"
    )
    assert project_paths.DATASET_RAW_ROOT != project_paths.DATASET_OUTCOME_ROOT


def test_output_subdirectories_are_derived_from_outcome_root():
    root = project_paths.DATASET_OUTCOME_ROOT
    assert project_paths.ANNOTATION_ROOT == root / "annotations" / "v0.1-draft"
    assert project_paths.MANIFEST_ROOT == root / "manifests"
    assert project_paths.REPORT_ROOT == root / "reports"
    assert project_paths.SCHEMA_ROOT == root / "schemas"
