from app.ingestion.reference_resolver import ReferenceCandidate, resolve_candidate


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
