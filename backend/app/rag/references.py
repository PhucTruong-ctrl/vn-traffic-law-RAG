"""Deterministic Vietnamese legal-reference parsing and matching."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_CANONICAL_RE = re.compile(
    r"(?<![a-z0-9-])(?P<document_id>nd-\d+-\d{4}__dieu-\d+"
    r"(?:__khoan-\d+)?(?:__diem-[a-z])?)(?![a-z0-9-])",
    re.IGNORECASE,
)
_REFERENCE_RE = re.compile(
    r"(?:(?:điểm\s+(?P<point>[a-zđ])\s+)?(?:khoản\s+(?P<clause>\d+)\s+)?"
    r"điều\s+(?P<article>\d+)"
    r"(?:\s+(?:của\s+)?(?P<kind>nghị\s+định|thông\s+tư|luật|bộ\s+luật)\s*"
    r"(?:số\s+)?(?P<number>\d+(?:/\d{4})?(?:/[a-zđ0-9-]+)?))?)",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(
    r"\b(?:nghị\s+định|thông\s+tư|luật|bộ\s+luật)\s+(?:số\s+)?"
    r"(?P<number>\d+(?:/\d{4})?(?:/[a-zđ0-9-]+)?)\b",
    re.IGNORECASE,
)
_ABBREVIATED_NUMBER_RE = re.compile(
    r"(?<![\d/])(?P<number>\d+/\d{4})(?!/[a-zđ0-9-])", re.IGNORECASE
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
            }.items()
            if value is not None
        }


def parse_reference(text: str) -> LegalReference | None:
    """Parse the first natural-language or canonical legal reference."""
    canonical = _CANONICAL_RE.search(text)
    natural = _REFERENCE_RE.search(text)
    if canonical and (not natural or canonical.start() < natural.start()):
        return _parse_canonical(canonical.group("document_id"))
    if natural:
        values = natural.groupdict()
        return LegalReference(**{key: value for key, value in values.items() if value})
    number = _NUMBER_RE.search(text)
    if number:
        return LegalReference(number=number.group("number"))
    abbreviated = _ABBREVIATED_NUMBER_RE.search(text)
    return LegalReference(number=abbreviated.group("number")) if abbreviated else None


def extract_references(text: str, *, limit: int = 4) -> list[LegalReference]:
    """Extract at most ``limit`` unique references in source order."""
    if limit < 1:
        return []
    matches: list[tuple[int, LegalReference]] = []
    for pattern, parser in (
        (_CANONICAL_RE, lambda m: _parse_canonical(m.group("document_id"))),
        (
            _REFERENCE_RE,
            lambda m: LegalReference(
                **{key: value for key, value in m.groupdict().items() if value}
            ),
        ),
        (_NUMBER_RE, lambda m: LegalReference(number=m.group("number"))),
        (_ABBREVIATED_NUMBER_RE, lambda m: LegalReference(number=m.group("number"))),
    ):
        matches.extend((match.start(), parser(match)) for match in pattern.finditer(text))
    found: list[LegalReference] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for _, reference in sorted(matches, key=lambda item: item[0]):
        key = tuple(sorted(reference.as_dict().items()))
        if key in seen:
            continue
        seen.add(key)
        found.append(reference)
        if len(found) >= limit:
            break
    return found


def metadata_matches(metadata: Mapping[str, Any], reference: LegalReference) -> bool:
    """Require exact normalized matches for every specified reference field."""
    normalized = {str(key): normalize_reference_value(value) for key, value in metadata.items()}
    if reference.document_id:
        actual_id = normalized.get("document_id")
        if actual_id != normalize_reference_value(reference.document_id):
            return False
    for key in ("article", "clause", "point"):
        expected = getattr(reference, key)
        if expected and normalized.get(key) != normalize_reference_value(expected):
            return False
    if reference.number:
        document = normalized.get("document_number") or normalized.get("document_name")
        actual = _document_number(document)
        expected = _document_number(reference.number)
        if actual != expected and not (
            "/" not in reference.number and actual.startswith(expected + "/")
        ):
            return False
    return True


def _parse_canonical(value: str) -> LegalReference | None:
    parts = value.casefold().split("__")
    if len(parts) < 2:
        return None
    document_id, article_part, *rest = parts
    if not re.fullmatch(r"nd-\d+-\d{4}", document_id) or not re.fullmatch(
        r"(?:đieu|dieu)-\d+", article_part
    ):
        return None
    fields = {"document_id": document_id, "article": article_part.split("-", 1)[1]}
    for part in rest:
        key, _, value = part.partition("-")
        if key not in {"khoan", "diem"} or not value or (key == "khoan" and not value.isdigit()):
            return None
        fields["clause" if key == "khoan" else "point"] = value
    return LegalReference(**fields)


def _document_number(value: Any) -> str:
    normalized = normalize_reference_value(value).replace("đ", "d")
    match = re.search(r"\d+(?:/\d{4})?(?:/[a-z0-9-]+)?", normalized)
    return match.group(0) if match else normalized


def normalize_reference_value(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


__all__ = ["LegalReference", "extract_references", "metadata_matches", "parse_reference"]
