from datetime import date
from types import SimpleNamespace

import pytest

from app.generation.context_builder import build_context


def item(pid, version, rank, text="text"):
    return SimpleNamespace(
        provision_id=pid,
        provision_version=version,
        rank=rank,
        text=text,
        document_number="12/2024/NĐ-CP",
        article="7",
        clause="2",
        point="a",
        effective_from=date(2024, 1, 1),
        effective_to=None,
        page_number=3,
        source_id="scan-1",
    )


def test_order_dedup_and_provenance_annotation():
    value = build_context([item("b", 1, 2), item("a", 1, 1), item("a", 1, 3)])
    assert value.index("a@v1") < value.index("b@v1")
    assert value.count("a@v1") == 1
    assert "source=scan-1; page=3; interval=2024-01-01–present" in value


def test_applied_date_and_budgets():
    value = build_context(
        [item("a", 1, 1, "one two"), item("b", 1, 2, "three four")],
        applied_date=date(2025, 1, 2),
        max_tokens=20,
    )
    assert "applied 2025-01-02" in value
    assert "b@v1" not in value
    assert len(value) <= 12_000


def test_invalid_budget():
    with pytest.raises(ValueError):
        build_context([], max_chars=-1)


def test_oversized_block_is_skipped_and_later_block_fits():
    value = build_context(
        [item("a", 1, 1, "one two"), item("b", 1, 2, "three")],
        applied_date=date(2025, 1, 2),
        max_tokens=15,
    )
    assert "a@v1" in value
    assert "b@v1" not in value
    assert "applied 2025-01-02" in value
