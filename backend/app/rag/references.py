"""Deterministic Vietnamese legal-reference parsing and matching."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_REFERENCE_RE = re.compile(
    r"(?:(?:điểm\s+(?P<point>[a-zđ])\s+)?(?:khoản\s+(?P<clause>\d+)\s+)?"
    r"điều\s+(?P<article>\d+)"
    r"(?:\s+(?:của\s+)?(?P<kind>nghị\s+định|thông\s tư|luật|bộ\s luật)\s*"
    r"(?:số\s+)?(?P<number>\d+(?:/\d{4})?(?:/[a-zđ0-9-]+)?))?)",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(
    r"\b(?:nghị\s+định|thông\s+tư|luật|bộ\s+luật)\s+(?:số\s+)?"
    r"(?P<number>\d+(?:/\d{4})?(?:/[a-zđ0-9-]+)?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class LegalReference:
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    kind: str | None = None
    number: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "article": self.article,
                "clause": self.clause,
                "point": self.point,
                "kind": self.kind,
                "number": self.number,
            }.items()
            if value is not None
        }


def parse_reference(text: str) -> LegalReference | None:
    """Parse the first explicit Điều/Khoản/Điểm/document-number reference."""
    match = _REFERENCE_RE.search(text)
    if match:
        values = match.groupdict()
        return LegalReference(**{key: value for key, value in values.items() if value})
    number = _NUMBER_RE.search(text)
    return LegalReference(number=number.group("number")) if number else None


def extract_references(text: str, *, limit: int = 4) -> list[LegalReference]:
    """Extract at most ``limit`` unique references in source order."""
    if limit < 1:
        return []
    found: list[LegalReference] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for match in _REFERENCE_RE.finditer(text):
        reference = LegalReference(
            **{key: value for key, value in match.groupdict().items() if value}
        )
        key = tuple(sorted(reference.as_dict().items()))
        if key not in seen:
            seen.add(key)
            found.append(reference)
        if len(found) >= limit:
            break
    if len(found) < limit:
        for match in _NUMBER_RE.finditer(text):
            reference = LegalReference(number=match.group("number"))
            key = tuple(sorted(reference.as_dict().items()))
            if key not in seen:
                seen.add(key)
                found.append(reference)
            if len(found) >= limit:
                break
    return found


def metadata_matches(metadata: Mapping[str, Any], reference: LegalReference) -> bool:
    """Require exact normalized matches for every specified reference field."""
    normalized = {str(key): normalize_reference_value(value) for key, value in metadata.items()}
    if reference.article and normalized.get("article") != normalize_reference_value(
        reference.article
    ):
        return False
    if reference.clause and normalized.get("clause") != normalize_reference_value(reference.clause):
        return False
    if reference.point and normalized.get("point") != normalize_reference_value(reference.point):
        return False
    if reference.number:
        document = normalized.get("document_number") or normalized.get("document_name")
        if document != normalize_reference_value(reference.number):
            return False
    return True


def normalize_reference_value(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


__all__ = ["LegalReference", "extract_references", "metadata_matches", "parse_reference"]
