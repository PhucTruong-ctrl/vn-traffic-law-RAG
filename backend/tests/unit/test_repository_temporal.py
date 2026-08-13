"""Unit tests: temporal validity predicate (VNLRAG-39).

The predicate is the pure half of the temporal query; the SQL half is
covered by the integration suite against PostgreSQL. Boundaries follow the
half-open ``[effective_from, effective_to)`` interval (doc 00 §8.6).
"""

from datetime import date
from uuid import uuid4

from app.persistence.models import LegalProvision
from app.persistence.repositories import TemporalRepository

D = date(2025, 6, 1)


def _provision(**overrides: object) -> LegalProvision:
    fields: dict[str, object] = {
        "provision_id": "nd-168-2024__dieu-7",
        "document_version_id": uuid4(),
        "source_text": "Điều 7. Nội dung.",
        "retrieval_text": "Nội dung.",
        "status": "EFFECTIVE",
        "page_number": 1,
        "content_hash": "sha256:test",
        "version": 1,
        "review_status": "ACCEPTED",
    }
    fields.update(overrides)
    return LegalProvision(**fields)  # type: ignore[arg-type]


def test_valid_inside_interval() -> None:
    provision = _provision(effective_from=date(2025, 1, 1), effective_to=date(2025, 12, 31))
    assert TemporalRepository.is_valid_at(provision, D)


def test_valid_at_effective_from_boundary() -> None:
    provision = _provision(effective_from=D, effective_to=None)
    assert TemporalRepository.is_valid_at(provision, D)


def test_invalid_before_effective_from() -> None:
    provision = _provision(effective_from=date(2025, 7, 1), effective_to=None)
    assert not TemporalRepository.is_valid_at(provision, D)


def test_invalid_at_effective_to_boundary() -> None:
    """Exclusive upper bound: d == effective_to is not valid."""
    provision = _provision(effective_from=date(2025, 1, 1), effective_to=date(2025, 6, 1))
    assert not TemporalRepository.is_valid_at(provision, D)


def test_valid_when_effective_to_is_null() -> None:
    provision = _provision(effective_from=date(2025, 1, 1), effective_to=None)
    assert TemporalRepository.is_valid_at(provision, D)


def test_invalid_when_not_accepted() -> None:
    provision = _provision(
        review_status="PENDING",
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )
    assert not TemporalRepository.is_valid_at(provision, D)


def test_invalid_when_effective_from_missing() -> None:
    provision = _provision(review_status="PENDING", effective_from=None, effective_to=None)
    assert not TemporalRepository.is_valid_at(provision, D)
