from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

FORMAT_VERSION = "0.1-draft"
BUILDER_VERSION = "0.1.0"
SPLIT_NAMES = ("train", "validation", "test")


def dataset_split_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "dataset_split_schema_v0.1-draft.json",
        "title": "AlpaSim clip-grouped dataset split v0.1-draft",
        "type": "object",
        "additionalProperties": False,
        "required": ["split_format_version", "anchor_id", "clip_id", "split"],
        "properties": {
            "split_format_version": {"const": FORMAT_VERSION},
            "anchor_id": {"type": "string", "minLength": 1},
            "clip_id": {"type": "string", "pattern": "^test_clip_[0-9]+$"},
            "split": {"type": "string", "enum": list(SPLIT_NAMES)},
        },
    }


def write_schema(path: Path) -> None:
    schema = dataset_split_schema()
    Draft202012Validator.check_schema(schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
