"""Unit tests: index LegalProvisions as retrieval units (VNLRAG-48).

Verifies the exact retrieval-unit contract: one unit per provision (short
points included, no token-length filtering), ``retrieval_text`` flowing
through the Legal Context Enricher (VNLRAG-132 — monkeypatched here with a
contract-matching fake; the orchestrator verifies the real integration after
merge), ``source_text`` preserved verbatim, legal-boundary chunking only (no
arbitrary token cuts), and the ``unit_id`` format. Golden expectations come
from ``fixtures/parser_benchmark/gold/parent_context_annotation.json`` and
``short_point_annotation.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.ingestion import retrieval_units as retrieval_units_module
from app.ingestion.retrieval_units import (
    RetrievalUnit,
    build_retrieval_units,
    retrieval_unit_stats,
)
from app.ingestion.structure_extractor import ExtractedLegalProvision

GOLD_DIR = Path(__file__).resolve().parent / "fixtures" / "parser_benchmark" / "gold"

PARENT_CONTEXT_ANNOTATION = json.loads(
    (GOLD_DIR / "parent_context_annotation.json").read_text(encoding="utf-8")
)
SHORT_POINT_ANNOTATION = json.loads(
    (GOLD_DIR / "short_point_annotation.json").read_text(encoding="utf-8")
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ────────────────────────────────────────────────────────────────────────────


def _provision(
    *,
    provision_id: str,
    source_text: str,
    node_kind: str = "POINT",
    parent_context: str | None = None,
    short_point: bool = False,
    version: int = 1,
    **overrides: object,
) -> ExtractedLegalProvision:
    """Build an ``ExtractedLegalProvision`` with minimal required fields."""
    values: dict[str, object] = {
        "provision_id": provision_id,
        "document_version_id": "gold:" + provision_id.split("__", 1)[0],
        "chapter": None,
        "section": None,
        "article": "Điều 7",
        "clause": "Khoản 4",
        "point": "Điểm a",
        "heading": None,
        "source_text": source_text,
        "retrieval_text": source_text,
        "parent_context": parent_context,
        "page_number": 1,
        "bbox": None,
        "source_element_ids": ["test"],
        "content_hash": "test-hash",
        "node_kind": node_kind,
        "point_label": None,
        "short_point": short_point,
        "version": version,
    }
    values.update(overrides)
    return ExtractedLegalProvision(**values)


def _sentinel_enricher(provision: ExtractedLegalProvision) -> str:
    """Fake VNLRAG-132 enricher: deterministic sentinel per provision."""
    return f"ENRICHED::{provision.provision_id}::v{provision.version}"


def _gold_parent_context_enricher() -> Any:
    """Fake enricher implementing the gold annotation's retrieval_text rule.

    For a POINT the annotated ``retrieval_text_expected`` is
    ``clause lead-in + point source_text``; the fake rebuilds it from the
    *actual* provision ``source_text`` so the test proves the enricher is
    called with the full provision and its output is used uncut.
    """
    entries = {entry["provision_id"]: entry for entry in PARENT_CONTEXT_ANNOTATION["annotations"]}

    def _enrich(provision: ExtractedLegalProvision) -> str:
        entry = entries[provision.provision_id]
        expected = entry["retrieval_text_expected"]
        assert expected.endswith(provision.source_text), (
            "gold source_text must end the retrieval_text"
        )
        lead_in = expected[: -len(provision.source_text)].rstrip()
        return f"{lead_in} {provision.source_text}"

    return _enrich


# ────────────────────────────────────────────────────────────────────────────
# One unit per provision — short points included, no length filtering
# ────────────────────────────────────────────────────────────────────────────


def test_one_unit_per_provision_including_short_points(monkeypatch: pytest.MonkeyPatch) -> None:
    provisions = [
        _provision(
            provision_id="luat-36-2024__dieu-3",
            source_text="Điều 3. Giải thích từ ngữ",
            node_kind="ARTICLE",
        ),
        _provision(
            provision_id="luat-36-2024__dieu-3__khoan-1",
            source_text="Khoản 1. Trong Luật này, các từ ngữ dưới đây được hiểu như sau:",
            node_kind="CLAUSE",
        ),
        _provision(
            provision_id="luat-36-2024__dieu-3__khoan-1__diem-a",
            source_text="a) Tổ chức tín dụng là tổ chức ...",
            node_kind="POINT",
        ),
        # 3-word short point — must NOT be filtered out by token length.
        _provision(
            provision_id="luat-36-2024__dieu-8__khoan-1__diem-a",
            source_text="a) Đường cao tốc",
            node_kind="POINT",
            short_point=True,
        ),
    ]
    monkeypatch.setattr(retrieval_units_module, "_enrich_retrieval_text", _sentinel_enricher)

    units = build_retrieval_units(provisions)

    assert len(units) == len(provisions)  # exactly one unit per provision
    assert [unit.unit_id for unit in units] == [
        f"{provision.provision_id}__v{provision.version}" for provision in provisions
    ]
    short_units = [unit for unit in units if unit.short_point]
    assert len(short_units) == 1
    assert short_units[0].retrieval_text  # short point still indexed with retrieval_text


def test_short_points_retained_per_gold_annotation(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = SHORT_POINT_ANNOTATION["short_points"]
    provisions = [
        _provision(
            provision_id=entry["provision_id"],
            source_text=entry["source_text"],
            short_point=True,
        )
        for entry in entries
    ]
    monkeypatch.setattr(retrieval_units_module, "_enrich_retrieval_text", _sentinel_enricher)

    units = build_retrieval_units(provisions)

    # Every annotated short point is a valid provision — retained (no threshold).
    assert all(entry["expected_retained"] for entry in entries)
    assert len(units) == len(entries)
    assert all(unit.short_point for unit in units)
    for unit, entry in zip(units, entries, strict=True):
        assert unit.provision_id == entry["provision_id"]
        assert unit.source_text == entry["source_text"]
        assert unit.retrieval_text == f"ENRICHED::{entry['provision_id']}::v1"


# ────────────────────────────────────────────────────────────────────────────
# retrieval_text flows through the enricher
# ────────────────────────────────────────────────────────────────────────────


def test_retrieval_text_flows_through_enricher(monkeypatch: pytest.MonkeyPatch) -> None:
    provisions = [
        _provision(
            provision_id="nd-168-2024__dieu-7",
            source_text="Điều 7. ...",
            node_kind="ARTICLE",
        ),
        _provision(
            provision_id="nd-168-2024__dieu-7__khoan-4",
            source_text="Khoản 4. ...",
            node_kind="CLAUSE",
        ),
        _provision(
            provision_id="nd-168-2024__dieu-7__khoan-4__diem-a",
            source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        ),
    ]
    seen: list[str] = []
    expected_source = {provision.provision_id: provision.source_text for provision in provisions}

    def _fake_enricher(provision: ExtractedLegalProvision) -> str:
        assert provision.source_text == expected_source[provision.provision_id]
        seen.append(provision.provision_id)
        return "SENTINEL-RETRIEVAL-TEXT"

    monkeypatch.setattr(retrieval_units_module, "_enrich_retrieval_text", _fake_enricher)

    units = build_retrieval_units(provisions)

    assert all(unit.retrieval_text == "SENTINEL-RETRIEVAL-TEXT" for unit in units)
    # Called exactly once per provision, in order — one unit per provision.
    assert seen == [provision.provision_id for provision in provisions]


# ────────────────────────────────────────────────────────────────────────────
# source_text preserved verbatim (immutability contract)
# ────────────────────────────────────────────────────────────────────────────


def test_source_text_byte_identical_to_provision(monkeypatch: pytest.MonkeyPatch) -> None:
    provisions = [
        _provision(
            provision_id="nd-168-2024__dieu-7__khoan-4__diem-a",
            source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
            parent_context="Khoản 4. Xử phạt người điều khiển xe mô tô, xe gắn máy ...",
        ),
        _provision(
            provision_id="luat-36-2024__dieu-8__khoan-1__diem-đ",
            source_text="đ) Đường xã",
            short_point=True,
        ),
        _provision(
            provision_id="nd-168-2024__dieu-9",
            source_text="Điều 9. ...",
            node_kind="ARTICLE",
        ),
    ]
    monkeypatch.setattr(retrieval_units_module, "_enrich_retrieval_text", _sentinel_enricher)

    units = build_retrieval_units(provisions)

    for unit, provision in zip(units, provisions, strict=True):
        assert unit.source_text.encode("utf-8") == provision.source_text.encode("utf-8")
        assert unit.source_text == provision.source_text


# ────────────────────────────────────────────────────────────────────────────
# Unit boundaries == provision boundaries (no token cuts) vs gold fixtures
# ────────────────────────────────────────────────────────────────────────────


def test_boundaries_match_gold_parent_context_annotation(monkeypatch: pytest.MonkeyPatch) -> None:
    annotations = PARENT_CONTEXT_ANNOTATION["annotations"]
    provisions = [
        _provision(
            provision_id=entry["provision_id"],
            source_text=entry["source_text"],
            parent_context=entry["parent_context"],
        )
        for entry in annotations
    ]
    monkeypatch.setattr(
        retrieval_units_module, "_enrich_retrieval_text", _gold_parent_context_enricher()
    )

    units = build_retrieval_units(provisions)

    assert len(units) == len(annotations)
    for unit, entry in zip(units, annotations, strict=True):
        # Whole enricher output for the whole provision — no token-boundary cuts.
        assert unit.retrieval_text == entry["retrieval_text_expected"]
        # The enricher output embeds the full source_text as its tail.
        assert unit.retrieval_text.endswith(unit.source_text)
        assert unit.source_text == entry["source_text"]
        assert unit.provision_id == entry["provision_id"]


def test_boundaries_match_gold_for_dieu7_khoan4_diem_a(monkeypatch: pytest.MonkeyPatch) -> None:
    """Focused check for the canonical nd-168-2024__dieu-7__khoan-4__diem-a case."""
    entry = next(
        e
        for e in PARENT_CONTEXT_ANNOTATION["annotations"]
        if e["provision_id"] == "nd-168-2024__dieu-7__khoan-4__diem-a"
    )
    provision = _provision(
        provision_id=entry["provision_id"],
        source_text=entry["source_text"],
        parent_context=entry["parent_context"],
    )
    monkeypatch.setattr(
        retrieval_units_module, "_enrich_retrieval_text", _gold_parent_context_enricher()
    )

    (unit,) = build_retrieval_units([provision])

    assert unit.retrieval_text == (
        "Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với "
        "người điều khiển xe thực hiện hành vi vi phạm sau đây: a) Điều khiển xe "
        "lạng lách, đánh võng trên đường bộ"
    )
    assert unit.retrieval_text == entry["retrieval_text_expected"]
    assert unit.source_text == "a) Điều khiển xe lạng lách, đánh võng trên đường bộ"


# ────────────────────────────────────────────────────────────────────────────
# unit_id format
# ────────────────────────────────────────────────────────────────────────────


def test_unit_id_format_and_version_distinctness(monkeypatch: pytest.MonkeyPatch) -> None:
    v1 = _provision(
        provision_id="nd-168-2024__dieu-7__khoan-4__diem-a",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        version=1,
    )
    v2 = _provision(
        provision_id="nd-168-2024__dieu-7__khoan-4__diem-a",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ (amended)",
        version=2,
    )
    monkeypatch.setattr(retrieval_units_module, "_enrich_retrieval_text", _sentinel_enricher)

    units = build_retrieval_units([v1, v2])

    assert [unit.unit_id for unit in units] == [
        "nd-168-2024__dieu-7__khoan-4__diem-a__v1",
        "nd-168-2024__dieu-7__khoan-4__diem-a__v2",
    ]
    assert units[0].unit_id != units[1].unit_id
    assert units[1].version == 2


def test_retrieval_unit_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RetrievalUnit(
            unit_id="nd-168-2024__dieu-7__v1",
            provision_id="nd-168-2024__dieu-7",
            version=1,
            node_kind="ARTICLE",
            retrieval_text="Điều 7. ...",
            source_text="Điều 7. ...",
            parent_context=None,
            page_number=1,
            document_id="nd-168-2024",
            short_point=False,
            unexpected_field=True,
        )


# ────────────────────────────────────────────────────────────────────────────
# retrieval_unit_stats
# ────────────────────────────────────────────────────────────────────────────


def test_retrieval_unit_stats_counts_by_node_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    provisions = [
        _provision(
            provision_id="nd-168-2024__dieu-7",
            source_text="Điều 7. ...",
            node_kind="ARTICLE",
        ),
        _provision(
            provision_id="nd-168-2024__dieu-7__khoan-4",
            source_text="Khoản 4. ...",
            node_kind="CLAUSE",
        ),
        _provision(
            provision_id="nd-168-2024__dieu-7__khoan-5",
            source_text="Khoản 5. ...",
            node_kind="CLAUSE",
        ),
        _provision(
            provision_id="nd-168-2024__dieu-7__khoan-4__diem-a",
            source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        ),
    ]
    monkeypatch.setattr(retrieval_units_module, "_enrich_retrieval_text", _sentinel_enricher)

    stats = retrieval_unit_stats(build_retrieval_units(provisions))

    assert stats == {"total": 4, "by_node_kind": {"ARTICLE": 1, "CLAUSE": 2, "POINT": 1}}


def test_retrieval_unit_stats_empty() -> None:
    assert build_retrieval_units([]) == []
    assert retrieval_unit_stats([]) == {"total": 0, "by_node_kind": {}}
