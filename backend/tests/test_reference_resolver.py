from app.ingestion.reference_resolver import (
    ReferenceCandidate,
    infer_parent_relations,
    resolve_candidate,
    resolve_references,
)


def test_article_reference_does_not_match_descendant_provisions() -> None:
    candidate = ReferenceCandidate(
        source_provision_id="source",
        relation_type="REFERS_TO",
        source_text="Điều 7",
        target_provision_id="7",
    )
    provisions = [
        {"id": "article", "provision_id": "nd-168-2024__dieu-7", "version": 1},
        {
            "id": "clause",
            "provision_id": "nd-168-2024__dieu-7__khoan-1",
            "version": 1,
        },
    ]

    resolved = resolve_candidate(candidate, provisions, source_version=1)

    assert resolved.resolution_status == "RESOLVED"
    assert resolved.target_provision_id == "article"


def test_clause_reference_matches_only_same_hierarchy_level() -> None:
    candidate = ReferenceCandidate(
        source_provision_id="source",
        relation_type="REFERS_TO",
        source_text="Khoản 1 Điều 7",
        target_provision_id="7/1",
    )
    provisions = [
        {"id": "article", "provision_id": "nd-168-2024__dieu-7", "version": 1},
        {
            "id": "clause",
            "provision_id": "nd-168-2024__dieu-7__khoan-1",
            "version": 1,
        },
        {
            "id": "point",
            "provision_id": "nd-168-2024__dieu-7__khoan-1__diem-a",
            "version": 1,
        },
    ]

    resolved = resolve_candidate(candidate, provisions, source_version=1)

    assert resolved.resolution_status == "RESOLVED"
    assert resolved.target_provision_id == "clause"


def test_hierarchy_relations_include_parent_and_sibling_edges() -> None:
    provisions = [
        {"provision_id": "d__dieu-1", "document_version_id": "v", "node_kind": "ARTICLE", "article": "1"},
        {"provision_id": "d__dieu-1__khoan-1", "document_version_id": "v", "node_kind": "CLAUSE", "article": "1", "clause": "1"},
        {"provision_id": "d__dieu-1__khoan-1__diem-a", "document_version_id": "v", "node_kind": "POINT", "article": "1", "clause": "1", "point": "a"},
        {"provision_id": "d__dieu-1__khoan-1__diem-b", "document_version_id": "v", "node_kind": "POINT", "article": "1", "clause": "1", "point": "b"},
    ]

    relations = infer_parent_relations(provisions)

    assert {(r.relation_type, r.source_provision_id, r.target_provision_id) for r in relations} == {
        ("PARENT_OF", "d__dieu-1", "d__dieu-1__khoan-1"),
        ("PARENT_OF", "d__dieu-1__khoan-1", "d__dieu-1__khoan-1__diem-a"),
        ("PARENT_OF", "d__dieu-1__khoan-1", "d__dieu-1__khoan-1__diem-b"),
        ("SIBLING_OF", "d__dieu-1__khoan-1__diem-a", "d__dieu-1__khoan-1__diem-b"),
    }


def test_penalty_companion_stays_pending_after_unique_resolution() -> None:
    provisions = [{"id": "target", "provision_id": "d__dieu-7", "version": 1}]

    candidates = resolve_references(
        "Mức phạt theo Điều 7.",
        "source",
        provisions,
        source_version=1,
    )
    candidate = next(r for r in candidates if r.relation_type == "PENALTY_COMPANION")

    assert candidate.target_provision_id == "target"
    assert candidate.resolution_status == "PENDING_REVIEW"
