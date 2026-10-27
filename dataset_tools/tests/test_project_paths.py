from pathlib import Path
import project_paths

def test_standalone_repository_and_outcome_paths_are_separated():
    repository = Path("/home/lab/alpamayo_like_dataset")
    assert project_paths.DATASET_REPOSITORY_ROOT == repository
    assert project_paths.DATASET_TOOLS_ROOT == repository / "dataset_tools"
    assert project_paths.DATASET_OUTCOME_ROOT == repository / "outcome"
    assert project_paths.ALPASIM_DATA_ROOT == Path("/home/lab/data_from_alpasim")
    assert project_paths.ALPASIM_DATA_ROOT != project_paths.DATASET_OUTCOME_ROOT
    for path in (project_paths.ANNOTATION_ROOT, project_paths.INTERMEDIATE_ROOT, project_paths.REPORT_ROOT, project_paths.SCHEMA_ROOT, project_paths.MANIFEST_ROOT, project_paths.BACKUP_ROOT):
        assert path.is_relative_to(project_paths.DATASET_OUTCOME_ROOT)
    assert not hasattr(project_paths, "ALPASIM_ROS2_WS")

def test_outcome_is_ignored_by_repository_gitignore():
    text = (project_paths.DATASET_REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/outcome/" in text.splitlines()
