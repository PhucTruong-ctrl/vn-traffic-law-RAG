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
_CANONICAL_RE = re.compile(
    r"\b(?P<document_id>(?:nd|tt)-\d+-\d{4})"
    r"__dieu-(?P<article>\d+)"
    r"(?:__khoan-(?P<clause>\d+))?"
    r"(?:__diem-(?P<point>[a-zđ]))?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class LegalReference:
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    kind: str | None = None
    number: str | None = None
    document_id: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "article": self.article,
                "clause": self.clause,
                "point": self.point,
                "kind": self.kind,
                "number": self.number,
                "document_id": self.document_id,
            }.items()
            if value is not None
        }


def parse_reference(text: str) -> LegalReference | None:
    """Parse first canonical or natural legal reference."""
    canonical = _CANONICAL_RE.search(text)
    natural = _REFERENCE_RE.search(text)
    candidates = [
        (match.start(), kind, match)
        for kind, match in (("canonical", canonical), ("natural", natural))
        if match is not None
    ]
    if candidates:
        _, kind, match = min(candidates, key=lambda item: item[0])
        values = {key: value for key, value in match.groupdict().items() if value}
        if kind == "canonical":
            values["document_id"] = values["document_id"].casefold()
        return LegalReference(**values)
    number = _NUMBER_RE.search(text)
    return LegalReference(number=number.group("number")) if number else None


def extract_references(text: str, *, limit: int = 4) -> list[LegalReference]:
    """Extract at most ``limit`` unique references in source order."""
    if limit < 1:
        return []
    matches: list[tuple[int, int, re.Match[str]]] = [
        (match.start(), 0, match) for match in _CANONICAL_RE.finditer(text)
    ]
    matches.extend((match.start(), 1, match) for match in _REFERENCE_RE.finditer(text))
    matches.extend((match.start(), 2, match) for match in _NUMBER_RE.finditer(text))
    found: list[LegalReference] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    occupied: list[tuple[int, int]] = []
    for _, kind, match in sorted(matches, key=lambda item: (item[0], item[1])):
        span = match.span()
        if any(start <= span[0] and span[1] <= end for start, end in occupied):
            continue
        values = {key: value for key, value in match.groupdict().items() if value}
        if kind == 0:
            values["document_id"] = values["document_id"].casefold()
        reference = LegalReference(**values)
        key = tuple(sorted(reference.as_dict().items()))
        if key not in seen:
            seen.add(key)
            found.append(reference)
            occupied.append(span)
        if len(found) >= limit:
            break
    return found


def metadata_matches(metadata: Mapping[str, Any], reference: LegalReference) -> bool:
    """Require exact normalized matches for every specified reference field."""
    normalized = {str(key): normalize_reference_value(value) for key, value in metadata.items()}
    if reference.article:
        actual_article = normalize_reference_value(normalized.get("article")).removeprefix("điều")
        if actual_article != normalize_reference_value(reference.article).removeprefix("điều"):
            return False
    if reference.clause and normalized.get("clause") != normalize_reference_value(reference.clause):
        return False
    if reference.point and normalized.get("point") != normalize_reference_value(reference.point):
        return False
    if reference.document_id and normalize_reference_value(
        metadata.get("document_id")
    ) != normalize_reference_value(reference.document_id):
        return False
    if reference.number:
        document = (
            normalized.get("document_number")
            or normalized.get("document_name")
            or normalized.get("document_id")
        )
        actual_number = _document_number(document)
        expected_number = _document_number(reference.number)
        if actual_number != expected_number and not (
            "/" not in expected_number.removeprefix(expected_number.split("/", 1)[0] + "/")
            and actual_number.startswith(f"{expected_number}/")
        ):
            return False
    return True


def _document_number(value: Any) -> str:
    normalized = normalize_reference_value(value).replace("đ", "d")
    canonical_id = re.fullmatch(r"(?:nd|tt)-(?P<number>\d+)-(?P<year>\d{4})", normalized)
    if canonical_id:
        return f"{canonical_id.group('number')}/{canonical_id.group('year')}"
    match = re.search(r"\d+(?:/\d{4})?(?:/[a-z0-9-]+)?", normalized)
    return match.group(0) if match else normalized


def normalize_reference_value(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


__all__ = ["LegalReference", "extract_references", "metadata_matches", "parse_reference"]
