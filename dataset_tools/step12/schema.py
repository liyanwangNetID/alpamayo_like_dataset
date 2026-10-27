from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator


def final_audit_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "final_dataset_audit_schema_v0.1-draft.json",
        "title": "AlpaSim final dataset audit v0.1-draft",
        "type": "object",
        "additionalProperties": False,
        "required": ["audit_version", "status", "record_count", "clip_count", "checks", "warnings", "errors", "artifacts"],
        "properties": {
            "audit_version": {"const": "0.1"},
            "status": {"enum": ["PASS", "PASS_WITH_WARNINGS", "FAIL"]},
            "record_count": {"type": "integer", "minimum": 0},
            "clip_count": {"type": "integer", "minimum": 0},
            "checks": {"type": "object"},
            "warnings": {"type": "array", "items": {"type": "object"}},
            "errors": {"type": "array", "items": {"type": "object"}},
            "artifacts": {"type": "object"},
        },
    }


def write_schema(path: Path) -> None:
    schema = final_audit_schema()
    Draft202012Validator.check_schema(schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
