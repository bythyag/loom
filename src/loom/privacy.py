"""Privacy policy applied before traces and run artifacts are persisted."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REDACTED = "[REDACTED]"
OMITTED = "[OMITTED BY PRIVACY POLICY]"
_SECRET_KEYS = re.compile(r"(?:api[_-]?key|authorization|token|secret|password|cookie)", re.IGNORECASE)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+={0,2}")
_KNOWN_KEYS = re.compile(r"\b(?:sk-or-v1-|sk-)[A-Za-z0-9_-]{12,}\b")
_ABSOLUTE_PATH = re.compile(r"(?<![\w.-])/(?:Users|home)/[^\s/:]+")


def include_content(*, official_frozen_fixture: bool, explicit_opt_in: bool = False) -> bool:
    """Official frozen prompts are evidence; arbitrary repository content is opt-in."""
    return official_frozen_fixture or explicit_opt_in


def sanitize(
    value: Any,
    *,
    official_frozen_fixture: bool = False,
    explicit_content_opt_in: bool = False,
    home: str | Path | None = None,
) -> Any:
    """Return a JSON-compatible copy with secrets, content, and user paths protected."""
    allow_content = include_content(
        official_frozen_fixture=official_frozen_fixture, explicit_opt_in=explicit_content_opt_in
    )
    user_home = str(Path(home).resolve()) if home is not None else str(Path.home())

    def clean(item: Any, key: str | None = None) -> Any:
        if key and _SECRET_KEYS.search(key):
            return REDACTED
        if key in {"prompt", "content", "file_content", "diff"} and not allow_content:
            return OMITTED
        if isinstance(item, str):
            text = item.replace(user_home, "$HOME") if user_home else item
            text = _ABSOLUTE_PATH.sub(
                lambda match: "$HOME" if match.group(0) != "/home" else match.group(0), text
            )
            text = _BEARER.sub("Bearer " + REDACTED, text)
            return _KNOWN_KEYS.sub(REDACTED, text)
        if isinstance(item, Mapping):
            return {
                str(child_key): clean(child, str(child_key)) for child_key, child in item.items()
            }
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            return [clean(child) for child in item]
        if item is None or isinstance(item, (bool, int, float)):
            return item
        raise TypeError(f"unsupported artifact value: {type(item).__name__}")

    return clean(value)
