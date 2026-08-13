"""Tests for the Legal Context Enricher (VNLRAG-132, FR-04).

The gold contract is ``tests/fixtures/parser_benchmark/gold/parent_context_annotation.json``:
for a POINT, ``retrieval_text`` = clause lead-in + point ``source_text``; for a
CLAUSE, article heading + clause ``source_text``; ARTICLE and other kinds keep
their own ``source_text`` (identity).  ``source_text``/``content_hash`` must
stay byte-identical after enrichment.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.ingestion.context_enricher import (
    build_parent_context,
    enrich_provision,
    enrich_retrieval_text,
    parent_context_completeness,
)
from app.ingestion.structure_extractor import ExtractedLegalProvision

GOLD = json.loads(
    (
        Path(__file__).parent
        / "fixtures"
        / "parser_benchmark"
        / "gold"
        / "parent_context_annotation.json"
    ).read_text(encoding="utf-8")
)
ANNOTATIONS = {ann["provision_id"]: ann for ann in GOLD["annotations"]}

DOCUMENT_ID = "nd-168-2024"
ARTICLE_HEADING = (
    "Điều 7. Xử phạt người điều khiển xe mô tô, xe gắn máy vi phạm quy tắc giao thông đường bộ"
)

#: POINT annotations the acceptance criteria require to match exactly.
REQUIRED_GOLD_POINTS = {
    "nd-168-2024__dieu-7__khoan-4__diem-a",
    "nd-168-2024__dieu-5__khoan-1__diem-đ",
}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _provision(
    provision_id: str,
    *,
    node_kind: str,
    source_text: str,
    article: str | None = None,
    clause: str | None = None,
    point: str | None = None,
    heading: str | None = None,
    parent_context: str | None = None,
    short_point: bool = False,
    document_version_id: str = DOCUMENT_ID,
) -> ExtractedLegalProvision:
    return ExtractedLegalProvision(
        provision_id=provision_id,
        document_version_id=document_version_id,
        chapter=None,
        section=None,
        article=article,
        clause=clause,
        point=point,
        heading=heading,
        source_text=source_text,
        retrieval_text=source_text,
        parent_context=parent_context,
        page_number=1,
        bbox=None,
        source_element_ids=["e1"],
        content_hash=_hash(source_text),
        node_kind=node_kind,
        point_label=point,
        short_point=short_point,
    )


def _labels_from_provision_id(provision_id: str) -> dict[str, str]:
    """Derive ``Điều 7`` / ``Khoản 4`` / ``Điểm a)`` labels from a stable ID."""

    labels: dict[str, str] = {}
    for part in provision_id.split("__")[1:]:
        if part.startswith("dieu-"):
            labels["article"] = "Điều " + part.removeprefix("dieu-")
        elif part.startswith("khoan-"):
            labels["clause"] = "Khoản " + part.removeprefix("khoan-")
        elif part.startswith("diem-"):
            labels["point"] = "Điểm " + part.removeprefix("diem-") + ")"
    return labels


def _clause_lead_in(annotation: dict[str, object]) -> str:
    """Gold clause lead-in = expected retrieval text minus the point text."""

    expected = annotation["retrieval_text_expected"]
    source_text = annotation["source_text"]
    assert isinstance(expected, str) and isinstance(source_text, str)
    assert expected.endswith(source_text)
    return expected.removesuffix(source_text).strip()


def test_gold_annotation_covers_required_points() -> None:
    assert REQUIRED_GOLD_POINTS.issubset(ANNOTATIONS)


def test_real_extractor_output_matches_gold_parent_context() -> None:
    """Regression (oracle): enrichment on REAL extractor output equals the gold.

    The extractor records ``parent_context`` of a POINT as the article+clause
    concatenation (e.g. ``"Điều 7. Xử phạt ... 4. Phạt tiền ... sau đây:"``);
    the enricher must produce only the canonical clause lead-in + point text,
    never the article heading, and never pass the raw concatenation through.

    The gold annotation normalizes away trailing sentence punctuation that the
    source fixture keeps (``"...đường bộ."`` vs ``"...đường bộ"``,
    ``"...phương tiện;"`` vs ``"...phương tiện"``), while the enricher must
    keep ``source_text`` verbatim per the immutability contract — so the
    comparison strips trailing sentence punctuation from the produced
    retrieval text only (the lead-in and the point label are still compared
    exactly, and any missing/wrong parent context still fails this test).
    """

    from app.ingestion.structure_extractor import LegalStructureExtractor
    from tests.test_structure_extractor import FIXTURE, _document

    lines = [
        (line, "paragraph")
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    provisions = LegalStructureExtractor().extract(
        _document(lines), document_version_id="version-1"
    )
    by_id = {provision.provision_id: provision for provision in provisions}
    for annotation in GOLD["annotations"]:
        provision_id = annotation["provision_id"]
        if not provision_id.startswith("nd-168-2024"):
            continue
        assert provision_id in by_id, f"extractor did not emit {provision_id}"
        actual = enrich_retrieval_text(by_id[provision_id])
        expected = annotation["retrieval_text_expected"]
        assert actual.rstrip(".;,!?") == expected


@pytest.mark.parametrize("provision_id", sorted(ANNOTATIONS))
def test_point_retrieval_text_exactly_matches_gold_annotation(provision_id: str) -> None:
    """POINT retrieval_text = clause lead-in + point source_text (gold format)."""

    annotation = ANNOTATIONS[provision_id]
    labels = _labels_from_provision_id(provision_id)
    point = _provision(
        provision_id,
        node_kind="POINT",
        source_text=annotation["source_text"],
        article=labels["article"],
        clause=labels["clause"],
        point=labels["point"],
        parent_context=_clause_lead_in(annotation),
    )
    assert enrich_retrieval_text(point) == annotation["retrieval_text_expected"]


def test_point_with_unresolvable_clause_uses_derived_clause_lead_in_only() -> None:
    """Regression (oracle): a POINT whose clause cannot be located structurally
    (missing clause label -> ``_extract_clause_lead_in`` bails) must never
    inherit the chapter/section/article prefix of ``parent_context``; the
    fallback derives the trailing clause segment after the last article
    boundary and canonicalizes it to ``Khoản {n}. ...``.
    """

    point = _provision(
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        node_kind="POINT",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        article="Điều 7",
        clause=None,
        point="Điểm a)",
        parent_context=(
            "Chương I. Quy định chung Mục 1. Quy định về xử phạt "
            "Điều 7. Xử phạt người điều khiển xe mô tô, xe gắn máy vi phạm quy tắc giao thông đường bộ "
            "4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người điều khiển xe "
            "thực hiện hành vi vi phạm sau đây:"
        ),
    )
    retrieval_text = enrich_retrieval_text(point)
    assert retrieval_text == (
        "Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người điều khiển xe "
        "thực hiện hành vi vi phạm sau đây: a) Điều khiển xe lạng lách, đánh võng trên đường bộ"
    )
    assert "Chương" not in retrieval_text
    assert "Mục" not in retrieval_text
    assert "Điều 7" not in retrieval_text


def test_point_with_mismatched_clause_number_uses_derived_clause_lead_in_only() -> None:
    """Regression (oracle): the structural clause label may not match the
    marker-stripped/reconstructed clause text in ``parent_context``; the
    derived fallback must still pick the trailing clause segment (by its own
    marker) instead of leaking the article heading.
    """

    point = _provision(
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        node_kind="POINT",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        article="Điều 7",
        clause="Khoản 3",
        point="Điểm a)",
        parent_context=(
            "Chương I. Quy định chung Mục 1. Quy định về xử phạt "
            "Điều 7. Xử phạt người điều khiển xe mô tô, xe gắn máy vi phạm quy tắc giao thông đường bộ "
            "4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người điều khiển xe "
            "thực hiện hành vi vi phạm sau đây:"
        ),
    )
    retrieval_text = enrich_retrieval_text(point)
    assert retrieval_text == (
        "Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người điều khiển xe "
        "thực hiện hành vi vi phạm sau đây: a) Điều khiển xe lạng lách, đánh võng trên đường bộ"
    )
    assert "Điều 7" not in retrieval_text


def test_point_with_underivable_parent_context_falls_back_to_source_text() -> None:
    """A POINT whose clause cannot be located AND whose parent_context has no
    derivable clause segment (chapter+section+article only) falls back to the
    unmodified ``source_text`` — the full ``parent_context`` is never leaked.
    """

    point = _provision(
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        node_kind="POINT",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        article="Điều 7",
        clause=None,
        point="Điểm a)",
        parent_context=(
            "Chương I. Quy định chung Mục 1. Quy định về xử phạt "
            "Điều 7. Xử phạt người điều khiển xe mô tô, xe gắn máy vi phạm quy tắc giao thông đường bộ"
        ),
    )
    assert enrich_retrieval_text(point) == point.source_text
    assert build_parent_context(point) == ""


def test_clause_with_chapter_section_parent_derives_article_heading_only() -> None:
    """Regression (oracle): a CLAUSE enriched without sibling documents
    (``build_retrieval_units`` path) must never inherit chapter/section text:
    the article heading is derived from ``parent_context`` and any clause-level
    text after it is cut off.
    """

    clause_text = (
        "4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người điều khiển xe "
        "thực hiện hành vi vi phạm sau đây:"
    )
    clause = _provision(
        "nd-168-2024__dieu-7__khoan-4",
        node_kind="CLAUSE",
        source_text=clause_text,
        article="Điều 7",
        clause="Khoản 4",
        parent_context=(
            "Chương I. Quy định chung Mục 1. Quy định về xử phạt "
            "Điều 7. Xử phạt người điều khiển xe mô tô, xe gắn máy vi phạm quy tắc giao thông đường bộ "
            "4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người điều khiển xe "
            "thực hiện hành vi vi phạm sau đây:"
        ),
    )
    retrieval_text = enrich_retrieval_text(clause)
    assert retrieval_text.startswith(ARTICLE_HEADING)
    assert "Chương" not in retrieval_text
    assert "Mục" not in retrieval_text
    assert retrieval_text == f"{ARTICLE_HEADING} {clause_text}"


def test_clause_without_derivable_article_heading_falls_back_to_source_text() -> None:
    """A CLAUSE whose ``parent_context`` has no article heading falls back to
    the unmodified ``source_text`` — chapter/section text is never prepended.
    """

    clause = _provision(
        "nd-168-2024__dieu-7__khoan-4",
        node_kind="CLAUSE",
        source_text="4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng",
        article="Điều 7",
        clause="Khoản 4",
        parent_context="Chương I. Quy định chung Mục 1. Quy định về xử phạt",
    )
    assert enrich_retrieval_text(clause) == clause.source_text
    assert build_parent_context(clause) == ""


def test_build_parent_context_resolves_clause_lead_in_from_siblings() -> None:
    """Without parent_context on the record, the clause lead-in comes from siblings."""

    provision_id = "nd-168-2024__dieu-7__khoan-4__diem-a"
    annotation = ANNOTATIONS[provision_id]
    lead_in = _clause_lead_in(annotation)
    labels = _labels_from_provision_id(provision_id)
    point = _provision(
        provision_id,
        node_kind="POINT",
        source_text=annotation["source_text"],
        article=labels["article"],
        clause=labels["clause"],
        point=labels["point"],
    )
    clause = _provision(
        "nd-168-2024__dieu-7__khoan-4",
        node_kind="CLAUSE",
        source_text=lead_in,
        article=labels["article"],
        clause=labels["clause"],
    )
    article = _provision(
        "nd-168-2024__dieu-7",
        node_kind="ARTICLE",
        source_text=ARTICLE_HEADING,
        article=labels["article"],
    )
    documents = {DOCUMENT_ID: [article, clause, point]}
    assert build_parent_context(point, documents=documents) == lead_in


def test_build_parent_context_matches_parent_by_labels_when_id_differs() -> None:
    """Label fields resolve the parent when the sibling provision_id deviates."""

    point = _provision(
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        node_kind="POINT",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        article="Điều 7",
        clause="Khoản 4",
        point="Điểm a)",
    )
    clause = _provision(
        "nd-168-2024__dieu-7__khoan-4-reconstructed",
        node_kind="CLAUSE",
        source_text="Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người "
        "điều khiển xe thực hiện hành vi vi phạm sau đây:",
        article="Điều 7",
        clause="Khoản 4",
    )
    documents = {DOCUMENT_ID: [clause, point]}
    assert build_parent_context(point, documents=documents) == clause.source_text


def test_clause_inherits_article_heading() -> None:
    clause_text = (
        "4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người điều khiển xe "
        "thực hiện hành vi vi phạm sau đây:"
    )
    clause = _provision(
        "nd-168-2024__dieu-7__khoan-4",
        node_kind="CLAUSE",
        source_text=clause_text,
        article="Điều 7",
        clause="Khoản 4",
        parent_context=ARTICLE_HEADING,
    )
    assert enrich_retrieval_text(clause) == f"{ARTICLE_HEADING} {clause_text}"


def test_clause_parent_context_resolved_from_article_sibling() -> None:
    clause = _provision(
        "nd-168-2024__dieu-7__khoan-4",
        node_kind="CLAUSE",
        source_text="4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người điều "
        "khiển xe thực hiện hành vi vi phạm sau đây:",
        article="Điều 7",
        clause="Khoản 4",
    )
    article = _provision(
        "nd-168-2024__dieu-7",
        node_kind="ARTICLE",
        source_text=ARTICLE_HEADING,
        article="Điều 7",
    )
    documents = {DOCUMENT_ID: [article, clause]}
    assert build_parent_context(clause, documents=documents) == ARTICLE_HEADING


def test_article_and_other_node_kinds_are_identity() -> None:
    article = _provision(
        "nd-168-2024__dieu-7",
        node_kind="ARTICLE",
        source_text=ARTICLE_HEADING,
        article="Điều 7",
        parent_context="Chương I. Quy định chung",
    )
    assert enrich_retrieval_text(article) == ARTICLE_HEADING
    table = _provision(
        "nd-168-2024__dieu-7__bang-1",
        node_kind="TABLE",
        source_text="Bảng 1. Mức phạt tiền",
        article="Điều 7",
        parent_context=ARTICLE_HEADING,
    )
    assert enrich_retrieval_text(table) == table.source_text


def test_short_point_retains_parent_context() -> None:
    """Short Points are valid provisions: context is kept, never dropped.

    Aligned with ``short_point_annotation.json``: no length threshold drops a
    short Point, and enrichment still attaches its parent context.
    """

    short_point = _provision(
        "luat-36-2024__dieu-8__khoan-1__diem-a",
        node_kind="POINT",
        source_text="a) Đường cao tốc",
        article="Điều 8",
        clause="Khoản 1",
        point="Điểm a)",
        parent_context="Khoản 1. Trong Luật này, các từ ngữ dưới đây được hiểu như sau:",
        short_point=True,
    )
    assert short_point.short_point is True
    expected = "Khoản 1. Trong Luật này, các từ ngữ dưới đây được hiểu như sau: a) Đường cao tốc"
    assert enrich_retrieval_text(short_point) == expected


def test_enrich_provision_keeps_source_text_and_content_hash_byte_identical() -> None:
    point = _provision(
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        node_kind="POINT",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        article="Điều 7",
        clause="Khoản 4",
        point="Điểm a)",
        parent_context="Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với "
        "người điều khiển xe thực hiện hành vi vi phạm sau đây:",
    )
    original_source_text = point.source_text
    original_hash = point.content_hash
    enriched = enrich_provision(point)
    assert enriched is not point
    assert enriched.source_text == original_source_text
    assert enriched.source_text.encode("utf-8") == original_source_text.encode("utf-8")
    assert enriched.content_hash == original_hash
    assert enriched.retrieval_text == enrich_retrieval_text(point)
    assert enriched.retrieval_text != original_source_text
    assert enriched.parent_context == point.parent_context
    # The input record itself must stay untouched.
    assert point.source_text == original_source_text
    assert point.content_hash == original_hash


def test_enrich_provision_populates_parent_context() -> None:
    lead_in = (
        "Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người điều khiển "
        "xe thực hiện hành vi vi phạm sau đây:"
    )
    point = _provision(
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        node_kind="POINT",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        article="Điều 7",
        clause="Khoản 4",
        point="Điểm a)",
        parent_context=lead_in,
    )
    enriched = enrich_provision(point)
    assert enriched.retrieval_text == f"{lead_in} {point.source_text}"
    assert enriched.parent_context == lead_in


def test_enrich_provision_without_context_is_identity() -> None:
    point = _provision(
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        node_kind="POINT",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        article="Điều 7",
        clause="Khoản 4",
        point="Điểm a)",
    )
    enriched = enrich_provision(point)
    assert enriched.retrieval_text == point.source_text
    assert enriched.parent_context is None


def test_unresolved_parent_falls_back_to_source_text_identity() -> None:
    point = _provision(
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        node_kind="POINT",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        article="Điều 7",
        clause="Khoản 4",
        point="Điểm a)",
    )
    assert build_parent_context(point) == ""
    assert enrich_retrieval_text(point) == point.source_text


def test_parent_context_field_fallback_is_prepended() -> None:
    lead_in = (
        "Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng đối với người điều khiển "
        "xe thực hiện hành vi vi phạm sau đây:"
    )
    point = _provision(
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        node_kind="POINT",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        article="Điều 7",
        clause="Khoản 4",
        point="Điểm a)",
        parent_context=lead_in,
    )
    assert build_parent_context(point) == lead_in
    assert enrich_retrieval_text(point) == f"{lead_in} {point.source_text}"


def test_build_parent_context_falls_back_to_field_when_parent_missing() -> None:
    """Documents provided but parent absent -> provision.parent_context is used."""

    lead_in = "Khoản 1. Trong Luật này, các từ ngữ dưới đây được hiểu như sau:"
    point = _provision(
        "luat-36-2024__dieu-3__khoan-1__diem-đ",
        node_kind="POINT",
        source_text="đ) Người đi bộ là người đi bộ trên đường bộ, bao gồm cả người đi bộ qua đường",
        article="Điều 3",
        clause="Khoản 1",
        point="Điểm đ)",
        parent_context=lead_in,
    )
    unrelated = _provision(
        "nd-168-2024__dieu-7",
        node_kind="ARTICLE",
        source_text=ARTICLE_HEADING,
        article="Điều 7",
    )
    documents = {DOCUMENT_ID: [unrelated]}
    assert build_parent_context(point, documents=documents) == lead_in


def test_parent_context_completeness_all_context_is_one() -> None:
    provisions = [
        _provision(
            "nd-168-2024__dieu-7__khoan-4__diem-a",
            node_kind="POINT",
            source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
            parent_context="Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng",
        ),
        _provision(
            "nd-168-2024__dieu-7__khoan-4",
            node_kind="CLAUSE",
            source_text="4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng",
            parent_context=ARTICLE_HEADING,
        ),
    ]
    assert parent_context_completeness(provisions) == 1.0


def test_parent_context_completeness_none_is_zero() -> None:
    provisions = [
        _provision(
            "nd-168-2024__dieu-7__khoan-4__diem-a",
            node_kind="POINT",
            source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        ),
        _provision(
            "nd-168-2024__dieu-7__khoan-4",
            node_kind="CLAUSE",
            source_text="4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng",
        ),
    ]
    assert parent_context_completeness(provisions) == 0.0


def test_parent_context_completeness_mixed_is_fraction() -> None:
    with_context = _provision(
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        node_kind="POINT",
        source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        parent_context="Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng",
    )
    without_context = _provision(
        "nd-168-2024__dieu-7__khoan-1__diem-a",
        node_kind="POINT",
        source_text="a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
    )
    clause_with = _provision(
        "nd-168-2024__dieu-7__khoan-4",
        node_kind="CLAUSE",
        source_text="4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng",
        parent_context=ARTICLE_HEADING,
    )
    clause_without = _provision(
        "nd-168-2024__dieu-7__khoan-1",
        node_kind="CLAUSE",
        source_text="1. Phạt tiền từ 400.000 đồng đến 600.000 đồng",
    )
    article = _provision(
        "nd-168-2024__dieu-7",
        node_kind="ARTICLE",
        source_text=ARTICLE_HEADING,
    )
    provisions = [with_context, without_context, clause_with, clause_without, article]
    # 4 POINT/CLAUSE provisions, 2 with context; ARTICLE excluded from the metric.
    assert parent_context_completeness(provisions) == 0.5


def test_parent_context_completeness_empty_list_is_zero() -> None:
    assert parent_context_completeness([]) == 0.0


def test_parent_context_completeness_articles_only_is_zero() -> None:
    articles = [
        _provision("nd-168-2024__dieu-7", node_kind="ARTICLE", source_text=ARTICLE_HEADING),
        _provision("nd-168-2024__dieu-5", node_kind="ARTICLE", source_text="Điều 5. Xử phạt"),
    ]
    assert parent_context_completeness(articles) == 0.0
