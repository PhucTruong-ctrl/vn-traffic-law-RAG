"""Deterministic query-date parsing and canonical-date policy.

This module deliberately does not compute temporal intervals.  It converts the
small, explicit date vocabulary understood by query analysis into a date and
applies the historical year disambiguation rule.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

_DOCUMENT_NUMBER_YEAR_RE = re.compile(r"(?<![\d/])\d{1,4}/\d{4}/(?=[a-z0-9])")


def _is_document_number_year(text: str, year_match: re.Match[str]) -> bool:
    """Return whether a year is the middle component of a document number."""
    return any(
        candidate.start() < year_match.start() < candidate.end()
        for candidate in _DOCUMENT_NUMBER_YEAR_RE.finditer(text)
    )


MISSING_QUERY_DATE = "MISSING_QUERY_DATE"


@dataclass(frozen=True)
class ParsedQueryDate:
    """A parsed date signal, retaining whether the user supplied only a year."""

    value: date
    source: str
    year_only: bool = False


@dataclass(frozen=True)
class DatePolicyResult:
    """Resolved date exposed to query-planner callers."""

    parsed_date: date | None
    canonical_date: date | None = None
    reason_code: str | None = None
    date_source: str | None = None
    note: str | None = None

    @property
    def should_abstain(self) -> bool:
        return self.reason_code == MISSING_QUERY_DATE


def parse_query_date(text: str, *, current_date: date) -> ParsedQueryDate | None:
    """Parse supported absolute, year-only, and Vietnamese relative references.

    ``current_date`` is mandatory so tests and replayed requests are
    deterministic. Invalid or ambiguous input returns ``None``.
    """
    value = text.strip().lower()
    match = re.search(r"\bngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})\b", value)
    if match:
        try:
            return ParsedQueryDate(date(int(match[3]), int(match[2]), int(match[1])), "absolute")
        except ValueError:
            return None
    if re.search(r"\bhôm nay\b|\bhom nay\b", value):
        return ParsedQueryDate(current_date, "relative")
    if re.search(r"\bnăm ngoái\b|\bnam ngoai\b", value):
        return ParsedQueryDate(date(current_date.year - 1, 1, 1), "relative", True)

    match = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", value)
    if match:
        try:
            return ParsedQueryDate(date(int(match[3]), int(match[2]), int(match[1])), "absolute")
        except ValueError:
            return None
    match = re.search(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", value)
    if match:
        try:
            return ParsedQueryDate(date(int(match[1]), int(match[2]), int(match[3])), "absolute")
        except ValueError:
            return None
    years = [
        int(match[1])
        for match in re.finditer(r"(?<!\d)(\d{4})(?!\d)", value)
        if not _is_document_number_year(value, match)
    ]
    if len(years) == 1:
        return ParsedQueryDate(date(years[0], 1, 1), "year", True)
    return None


def resolve_query_date(
    query: str,
    *,
    current_date: date,
    effect_change_dates: Iterable[date] = (),
    canonical_month: int = 7,
    canonical_day: int = 1,
) -> DatePolicyResult:
    """Parse ``query`` and apply canonical policy for year-only references.

    Effect changes are only relevant when they fall in the referenced year.
    """
    parsed = parse_query_date(query, current_date=current_date)
    if parsed is None:
        return DatePolicyResult(None)
    if not parsed.year_only:
        return DatePolicyResult(parsed.value, date_source=parsed.source)
    changes = tuple(effect_change_dates)
    if any(event.year == parsed.value.year for event in changes):
        return DatePolicyResult(
            parsed.value,
            reason_code=MISSING_QUERY_DATE,
            date_source=parsed.source,
            note=f"query year {parsed.value.year} intersects an effect change",
        )
    try:
        canonical = date(parsed.value.year, canonical_month, canonical_day)
    except ValueError as exc:
        raise ValueError("canonical month/day must form a valid date") from exc
    return DatePolicyResult(
        canonical,
        canonical_date=canonical,
        date_source="canonical_date",
        note=(
            f"no effect change in {parsed.value.year}; "
            f"applied canonical date {canonical.isoformat()}"
        ),
    )


__all__ = [
    "MISSING_QUERY_DATE",
    "ParsedQueryDate",
    "DatePolicyResult",
    "parse_query_date",
    "resolve_query_date",
]
