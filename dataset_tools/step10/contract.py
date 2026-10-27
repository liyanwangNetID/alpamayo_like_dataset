from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

IDENTITY_KEYS = frozenset({"anchor_id", "clip_id", "anchor_ns"})


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: row must be an object")
            rows.append(value)
    return rows


def index_by_anchor(rows: Iterable[Mapping[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        anchor_id = str(row.get("anchor_id", ""))
        if not anchor_id:
            raise ValueError(f"{name}: missing anchor_id")
        if anchor_id in result:
            raise ValueError(f"{name}: duplicate anchor_id {anchor_id}")
        result[anchor_id] = dict(row)
    return result


def require_identity(reference: Mapping[str, Any], value: Mapping[str, Any], name: str) -> None:
    expected = (
        str(reference["anchor_id"]),
        str(reference["clip_id"]),
        int(reference["anchor_ns"]),
    )
    actual = (
        str(value["anchor_id"]),
        str(value["clip_id"]),
        int(value["anchor_ns"]),
    )
    if actual != expected:
        raise ValueError(f"{name}: identity mismatch expected={expected} actual={actual}")


def without_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in IDENTITY_KEYS}
