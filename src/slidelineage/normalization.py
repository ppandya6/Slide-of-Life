"""Pure conservative normalization helpers for manifest ingestion."""

import re
import unicodedata

_MISSING_TOKENS = {"", "na", "n/a", "null", "none"}
_SEPARATOR_RUN_RE = re.compile(r"[\s\-/\\]+")
_UNDERSCORE_RUN_RE = re.compile(r"_+")
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def normalize_header(value: str) -> str:
    """Normalize a CSV header without semantic alias mapping."""

    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    normalized = _SEPARATOR_RUN_RE.sub("_", normalized)
    normalized = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in normalized
    )
    normalized = _UNDERSCORE_RUN_RE.sub("_", normalized).strip("_")
    if not normalized:
        raise ValueError("normalized header cannot be empty")
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    """Apply minimal text cleanup without case folding or semantic interpretation."""

    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).strip()
    return normalized or None


def normalize_missing_value(value: str | None) -> str | None:
    """Map approved missing-value tokens to None after minimal cleanup."""

    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    if normalized.casefold() in _MISSING_TOKENS:
        return None
    return normalized


def normalize_identifier_candidate(value: str | None) -> str | None:
    """Return conservative comparison text for explicit identifier-like fields."""

    normalized = normalize_missing_value(value)
    if normalized is None:
        return None
    casefolded = normalized.casefold()
    return _WHITESPACE_RUN_RE.sub(" ", casefolded)
