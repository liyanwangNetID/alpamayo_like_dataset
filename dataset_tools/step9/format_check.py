from __future__ import annotations

import re
from typing import Any, Mapping

from .contract import Step9ContractError, response_schema, validate_schema


def _sentence_count(text: str) -> int:
    parts = [item for item in re.split(r"(?<=[.!?])\s+", text.strip()) if item]
    return len(parts)


def check_response_format(
    response: Mapping[str, Any],
    package: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Check JSON shape and the five-sentence limit only."""
    validate_schema(response, response_schema())
    summary = str(response["reasoning_summary"]).strip()
    if not summary:
        raise Step9ContractError("reasoning_summary must not be empty")
    if _sentence_count(summary) > 5:
        raise Step9ContractError("reasoning_summary must contain no more than five sentences")
    return {"reasoning_summary": summary}
