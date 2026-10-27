#!/usr/bin/env python3
"""Shared paths for the standalone AlpaSim dataset repository."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Mapping

DATASET_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_TOOLS_ROOT = DATASET_REPOSITORY_ROOT / "dataset_tools"
REPOSITORY_ROOT = DATASET_REPOSITORY_ROOT
LOCAL_CONFIG_PATH = DATASET_REPOSITORY_ROOT / "config" / "local_paths.env"

def read_local_path_config(path: Path = LOCAL_CONFIG_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(f"Invalid path configuration at {path}:{line_number}")
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key or not value:
                raise ValueError(f"Empty key or value at {path}:{line_number}")
            values[key] = value
    return values

def configured_path(name: str, *, config: Mapping[str, str], default: Path | None = None) -> Path:
    raw_value = os.environ.get(name) or config.get(name)
    if raw_value:
        return Path(raw_value).expanduser().resolve()
    if default is not None:
        return default.expanduser().resolve()
    raise RuntimeError(f"{name} is not configured. Create {LOCAL_CONFIG_PATH} from config/local_paths.env.example.")

_LOCAL_CONFIG = read_local_path_config()
ALPASIM_DATA_ROOT = configured_path("ALPASIM_DATA_ROOT", config=_LOCAL_CONFIG)
ALPASIM_ROOT = configured_path("ALPASIM_ROOT", config=_LOCAL_CONFIG)
DATASET_OUTCOME_ROOT = configured_path("DATASET_OUTCOME_ROOT", config=_LOCAL_CONFIG, default=DATASET_REPOSITORY_ROOT / "outcome")
ANNOTATION_ROOT = DATASET_OUTCOME_ROOT / "annotations" / "v0.1-draft"
INTERMEDIATE_ROOT = ANNOTATION_ROOT / "intermediate"
REPORT_ROOT = DATASET_OUTCOME_ROOT / "reports"
SCHEMA_ROOT = DATASET_OUTCOME_ROOT / "schemas"
MANIFEST_ROOT = DATASET_OUTCOME_ROOT / "manifests"
BACKUP_ROOT = DATASET_OUTCOME_ROOT / "backups"
