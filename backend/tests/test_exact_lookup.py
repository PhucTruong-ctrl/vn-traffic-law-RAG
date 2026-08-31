from datetime import date
from types import SimpleNamespace

from app.retrieval.exact_lookup import ExactLookup


def _row(
    provision_id: str = "p-đ", *, vehicle_types: list[str] | None = None
) -> SimpleNamespace:
    document = SimpleNamespace(
        document_id="doc-168",
        document_number="168/2024/NĐ-CP",
        source_id=None,
    )
    version = SimpleNamespace(
        manifest_json={"vehicle_types": vehicle_types} if vehicle_types is not None else {},
        document=document,
    )
    return SimpleNamespace(
        id="row-id",
        provision_id=provision_id,
        version=1,
        document_version_id="version-id",
        document_version=version,
        retrieval_text="Nội dung điểm đ",
        source_text="Điểm đ) ...",
        parent_context=None,
        article="7",
        clause="4",
        point="đ",
        effective_from=date(2024, 1, 1),
        effective_to=None,
        page_number=3,
    )


class FakeRepository:
    def __init__(self, rows):
        self.rows = rows
        self.arguments = None

    def lookup_exact(self, **kwargs):
        self.arguments = kwargs
        return self.rows


def test_exact_lookup_preserves_literal_point_and_canonical_row():
    repository = FakeRepository([_row()])
    result = ExactLookup(repository).lookup(
        document_number="168/2024/NĐ-CP",
        article="7",
        clause="4",
        point="đ",
        query_date=date(2025, 1, 1),
        derived_provision_ids=("stale-qdrant-id",),
    )

    assert result.results[0].point == "đ"
    assert result.results[0].provision_id == "p-đ"
    assert repository.arguments["point"] == "đ"


def test_exact_lookup_normalizes_vietnamese_vehicle_type():
    repository = FakeRepository([_row(vehicle_types=["MOTORCYCLE"])])
    result = ExactLookup(repository).lookup(
        document_number="168/2024/NĐ-CP",
        article="7",
        clause="4",
        point="đ",
        query_date=date(2025, 1, 1),
        vehicle_type="xe máy",
    )

    assert [item.provision_id for item in result.results] == ["p-đ"]


def test_exact_lookup_does_not_broaden_when_no_canonical_match():
    repository = FakeRepository([])
    result = ExactLookup(repository).lookup(
        document_number="168/2024/NĐ-CP",
        article="7",
        clause="4",
        point="d",
        query_date=date(2025, 1, 1),
    )

    assert result.results == []
    assert result.query.endswith("Điểm d")


def test_exact_lookup_returns_all_canonical_rows_even_when_hint_matches_one():
    rows = [_row("canonical-a"), _row("canonical-b")]
    result = ExactLookup(FakeRepository(rows)).lookup(
        document_number="168/2024/NĐ-CP",
        article="7",
        clause="4",
        point="đ",
        query_date=date(2025, 1, 1),
        derived_provision_ids=("canonical-a",),
    )

    assert [item.provision_id for item in result.results] == [
        "canonical-a",
        "canonical-b",
    ]
