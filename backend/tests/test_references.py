from app.rag.references import extract_references, metadata_matches, parse_reference


def test_abbreviated_reference_matches_full_document_number() -> None:
    reference = parse_reference("Điểm h khoản 5 Điều 6 Nghị định 168/2024")

    assert reference is not None
    assert metadata_matches(
        {
            "document_number": "168/2024/NĐ-CP",
            "article": "6",
            "clause": "5",
            "point": "h",
        },
        reference,
    )


def test_canonical_provision_id_parses_all_coordinates() -> None:
    reference = parse_reference("nd-119-2024__dieu-10__khoan-2__diem-a")

    assert reference is not None
    assert reference.as_dict() == {
        "document_id": "nd-119-2024",
        "article": "10",
        "clause": "2",
        "point": "a",
    }


def test_extracts_mixed_references_in_source_order() -> None:
    references = extract_references(
        "So sánh nd-119-2024__dieu-10__khoan-2 với Điều 11 Nghị định 119/2024"
    )

    assert [reference.as_dict() for reference in references] == [
        {"document_id": "nd-119-2024", "article": "10", "clause": "2"},
        {"article": "11", "kind": "Nghị định", "number": "119/2024"},
    ]


def test_malformed_canonical_id_does_not_parse() -> None:
    assert parse_reference("nd-119-2024__dieu-x") is None
