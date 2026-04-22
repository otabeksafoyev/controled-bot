"""Pattern matching helpers for channel rules and auto-replies."""

from __future__ import annotations

import logging
import re

from db.models import PATTERN_REGEX, PATTERN_SUBSTRING

log = logging.getLogger(__name__)


def match_pattern(text: str, pattern: str, pattern_type: str) -> bool:
    """Return True if `text` matches `pattern` per `pattern_type`.

    - substring: case-insensitive 'in' check (or True if pattern is empty = match all)
    - regex: Python re.search, case-insensitive; invalid regex returns False
    - empty pattern always matches (catch-all)
    """
    if not pattern:
        return True
    if pattern_type == PATTERN_REGEX:
        try:
            return re.search(pattern, text or "", re.IGNORECASE) is not None
        except re.error as exc:
            log.warning("Yaroqsiz regex %r: %s", pattern, exc)
            return False
    # default: substring
    if pattern_type != PATTERN_SUBSTRING:
        log.warning("Noma'lum pattern_type=%r, substring sifatida qarayapmiz", pattern_type)
    return pattern.lower() in (text or "").lower()


def validate_regex(pattern: str) -> str | None:
    """Return error message if pattern invalid, None if ok."""
    try:
        re.compile(pattern)
    except re.error as exc:
        return str(exc)
    return None
