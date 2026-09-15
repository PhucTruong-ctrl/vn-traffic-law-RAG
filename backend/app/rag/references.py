"""Deterministic Vietnamese legal-reference parsing and matching."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_CANONICAL_RE = re.compile(
    r"(?<![a-z0-9-])(?P<document>nd-\d+-\d{4})__"
    r"(?P<article>(?:đieu|dieu)-\d+)"
    r"(?:__khoan-\d+)?(?:__diem-[a-zđ])?(?![a-z0-9_-])",
    re.IGNORECASE,
)
_REFERENCE_RE = re.compile(
    r"(?:(?:điểm\s+(?P<point>[a-zđ])\s+)?(?:khoản\s+(?P<clause>\d+)\s+)?"
    r"điều\s+(?P<article>\d+)"
    r"(?:\s*,?\s*(?:khoản\s+(?P<trailing_clause>\d+)"
    r"(?:\s*,?\s*điểm\s+(?P<trailing_point>[a-zđ]))?|"
    r"điểm\s+(?P<trailing_point_only>[a-zđ])))?"
    r"(?:\s+(?:của\s+)?(?P<kind>nghị\s+định|thông\s+tư|luật|bộ\s+luật)\s*"
    r"(?:số\s+)?(?P<number>\d+(?:/\d{4})?(?:/[a-zđ0-9-]+)?))?)",
    re.IGNORECASE,
)
# Bare tokens must not fire inside a canonical id (`nd-119-2024__dieu-10`), so the
# underscore that joins canonical parts counts as a forbidden neighbour too.
_BARE_COORDINATE_RE = re.compile(
    r"(?<![a-z0-9_-])(?:(?P<article>dieu|đieu)-(?P<article_value>\d+)"
    r"|(?P<clause>khoan|khoản)-(?P<clause_value>\d+)"
    r"|(?P<point>diem|điểm)-(?P<point_value>[a-zđ]))(?![a-z0-9_-])",
    re.IGNORECASE,
)
_BARE_NATURAL_RE = re.compile(
    r"(?<!\w)(?:(?P<article_word>điều)\s+(?P<article_value>\d+)"
    r"|(?P<clause_word>khoản)\s+(?P<clause_value>\d+)"
    r"|(?P<point_word>điểm)\s+(?P<point_value>[a-zđ]))(?!\w)",
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
# Patterns at this index and above are document-less fallbacks, applied only where no
# explicit reference already covers the same span.
_BARE_PRIORITY = 4


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
    """Parse the first natural-language, canonical, or bare coordinate reference."""
    canonical = _CANONICAL_RE.search(text)
    natural = _REFERENCE_RE.search(text)
    bare = _BARE_COORDINATE_RE.search(text) or _BARE_NATURAL_RE.search(text)
    candidates = [(match.start(), "canonical", match) for match in (canonical,) if match]
    candidates.extend((match.start(), "natural", match) for match in (natural,) if match)
    if not candidates and bare and not re.search(r"nd-\d+-\d{4}__", text):
        candidates.append((bare.start(), "bare", bare))
    if candidates:
        _, kind, match = min(candidates, key=lambda item: item[0])
        if kind == "canonical":
            return _parse_canonical(match.group(0))
        if kind == "natural":
            return _reference_from_match(match)
        return _bare_reference_from_match(match)
    number = _NUMBER_RE.search(text)
    if number:
        return LegalReference(number=number.group("number"))
    abbreviated = _ABBREVIATED_NUMBER_RE.search(text)
    return LegalReference(number=abbreviated.group("number")) if abbreviated else None


def _bare_reference_from_match(match: re.Match[str]) -> LegalReference:
    values = match.groupdict()
    return LegalReference(
        article=values.get("article_value"),
        clause=values.get("clause_value"),
        point=values.get("point_value"),
    )


def _reference_from_match(match: re.Match[str]) -> LegalReference:
    values = match.groupdict()
    if values.get("trailing_clause"):
        values["clause"] = values["trailing_clause"]
    if values.get("trailing_point") or values.get("trailing_point_only"):
        values["point"] = values.get("trailing_point") or values["trailing_point_only"]
    return LegalReference(
        **{key: value for key, value in values.items() if value and not key.startswith("trailing_")}
    )


def extract_references(text: str, *, limit: int = 4) -> list[LegalReference]:
    """Extract at most ``limit`` unique references in source order."""
    if limit < 1:
        return []
    matches: list[tuple[int, int, int, LegalReference]] = []
    for priority, (pattern, parser) in enumerate(
        (
            (_CANONICAL_RE, lambda m: _parse_canonical(m.group(0))),
            (_REFERENCE_RE, _reference_from_match),
            (_NUMBER_RE, lambda m: LegalReference(number=m.group("number"))),
            (_ABBREVIATED_NUMBER_RE, lambda m: LegalReference(number=m.group("number"))),
            (_BARE_COORDINATE_RE, _bare_reference_from_match),
            (_BARE_NATURAL_RE, _bare_reference_from_match),
        )
    ):
        for match in pattern.finditer(text):
            reference = parser(match)
            if reference is not None:
                matches.append((match.start(), match.end(), priority, reference))
    # Bare tokens are fallbacks: they only count where no explicit reference already
    # covers that span, otherwise every `Điều 10 Nghị định 119/2024` would also emit a
    # document-less `Điều 10` and inflate the reference list.
    explicit_spans = [
        (start, end) for start, end, priority, _ in matches if priority < _BARE_PRIORITY
    ]
    found: list[LegalReference] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    covered_numbers: set[str] = set()
    for start, end, priority, reference in sorted(
        matches, key=lambda item: (item[0], item[1], item[2])
    ):
        key = tuple(sorted(reference.as_dict().items()))
        if key in seen:
            continue
        if priority >= _BARE_PRIORITY and any(
            span_start <= start and end <= span_end for span_start, span_end in explicit_spans
        ):
            continue
        if reference.number:
            number_key = _document_number(reference.number)
            if number_key in covered_numbers:
                continue
        seen.add(key)
        found.append(reference)
        if reference.article and reference.number:
            covered_numbers.add(_document_number(reference.number))
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
    if reference.article:
        actual_article = (
            normalize_reference_value(normalized.get("article", ""))
            .removeprefix("điều")
            .removeprefix("dieu")
        )
        expected_article = (
            normalize_reference_value(reference.article).removeprefix("điều").removeprefix("dieu")
        )
        if actual_article != expected_article:
            return False
    for key in ("clause", "point"):
        expected = getattr(reference, key)
        if expected and normalized.get(key) != normalize_reference_value(expected).removeprefix(
            "khoản" if key == "clause" else "điểm"
        ).removeprefix("khoan" if key == "clause" else "diem"):
            return False
    if reference.number:
        document = (
            normalized.get("document_number")
            or normalized.get("document_name")
            or normalized.get("document_id")
        )
        actual = _document_number(document)
        expected = _document_number(reference.number)
        # Only a bare number/year reference may match a fuller stored number: the
        # abbreviation test must look at the raw text, because normalization strips
        # the `nđ-cp` suffix and would make every decree look abbreviated.
        raw_number = re.sub(r"\s+", "", str(reference.number or "")).casefold()
        abbreviated = bool(re.fullmatch(r"\d+/\d{4}", raw_number))
        if actual != expected and not (abbreviated and actual.startswith(expected + "/")):
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
        key, _, point_value = part.partition("-")
        if (
            key not in {"khoan", "diem"}
            or not point_value
            or (key == "khoan" and not point_value.isdigit())
        ):
            return None
        fields["clause" if key == "khoan" else "point"] = point_value
    return LegalReference(**fields)


def _document_number(value: Any) -> str:
    normalized = normalize_reference_value(value).replace("đ", "d")
    canonical_id = re.fullmatch(r"(?:nd|tt)-(?P<number>\d+)-(?P<year>\d{4})", normalized)
    if canonical_id:
        return f"{canonical_id.group('number')}/{canonical_id.group('year')}"
    match = re.search(r"\d+(?:/\d{4})?(?:/[a-z0-9-]+)?", normalized)
    return match.group(0) if match else normalized


def normalize_reference_value(value: Any) -> str:
    normalized = re.sub(r"\s+", "", str(value or "")).casefold()
    if normalized.startswith(("điều", "dieu", "khoản", "khoan", "điểm", "diem")):
        normalized = re.sub(r"^(?:điều|dieu|khoản|khoan|điểm|diem)", "", normalized)
    if "/nđ-cp" in normalized:
        normalized = normalized.removesuffix("/nđ-cp")
    return normalized


__all__ = [
    "LegalReference",
    "extract_references",
    "metadata_matches",
    "normalize_reference_value",
    "parse_reference",
]
