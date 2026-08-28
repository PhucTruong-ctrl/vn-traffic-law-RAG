from datetime import date

import pytest

from app.query.date_policy import MISSING_QUERY_DATE, parse_query_date, resolve_query_date


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("áp dụng ngày 26/12/2024", date(2024, 12, 26)),
        ("hiệu lực 2024-02-29", date(2024, 2, 29)),
        ("năm 2023", date(2023, 1, 1)),
        ("hôm nay", date(2026, 8, 26)),
        ("năm ngoái", date(2025, 1, 1)),
        ("ngày 26 tháng 12 năm 2024", date(2024, 12, 26)),
    ],
)
def test_parse_date_matrix(text: str, expected: date) -> None:
    parsed = parse_query_date(text, current_date=date(2026, 8, 26))
    assert parsed is not None
    assert parsed.value == expected


def test_absolute_date_is_surfaced_without_canonicalization() -> None:
    result = resolve_query_date("ngày 03/04/2024", current_date=date(2026, 8, 26))
    assert result.parsed_date == date(2024, 4, 3)
    assert result.canonical_date is None
    assert result.date_source == "absolute"


def test_year_gets_canonical_date_when_no_effect_change() -> None:
    result = resolve_query_date("năm 2023", current_date=date(2026, 8, 26))
    assert result.parsed_date == date(2023, 7, 1)
    assert result.canonical_date == date(2023, 7, 1)
    assert result.date_source == "canonical_date"
    assert not result.should_abstain


def test_year_intersecting_effect_change_requires_specific_date() -> None:
    result = resolve_query_date(
        "năm ngoái",
        current_date=date(2026, 8, 26),
        effect_change_dates=[date(2025, 3, 1)],
    )
    assert result.parsed_date == date(2025, 1, 1)
    assert result.reason_code == MISSING_QUERY_DATE
    assert result.should_abstain


@pytest.mark.parametrize(
    "document_number",
    [
        "Nghị định 168/2024/NĐ-CP",
        "Luật 36/2024/QH15",
        "Số: 36/2024/QH15",
    ],
)
def test_document_number_year_is_not_treated_as_query_date(document_number: str) -> None:
    assert parse_query_date(document_number, current_date=date(2026, 8, 26)) is None


def test_explicit_year_query_still_uses_year_fallback() -> None:
    parsed = parse_query_date("năm 2024", current_date=date(2026, 8, 26))
    assert parsed is not None
    assert parsed.value == date(2024, 1, 1)


def test_invalid_date_is_not_guessed() -> None:
    assert parse_query_date("31/02/2024", current_date=date(2026, 8, 26)) is None
