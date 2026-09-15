from app.rag.references import extract_references, metadata_matches, parse_reference


def test_parse_canonical_reference_fields():
    reference = parse_reference("nd-119-2024__dieu-10__khoan-2__diem-a")
    assert reference is not None
    assert reference.document_id == "nd-119-2024"
    assert reference.article == "10"
    assert reference.clause == "2"
    assert reference.point == "a"


def test_parse_rejects_malformed_canonical_ids():
    assert parse_reference("nd-119-2024__dieu-10__khoan-x") is None
    assert parse_reference("nd-119-2024__dieu-10__unknown-2") is None


def test_extracts_mixed_references_in_source_order_and_deduplicates():
    text = "nd-119-2024__dieu-10; Điều 12 của Nghị định số 168/2024/NĐ-CP; nd-119-2024__dieu-10."
    references = extract_references(text)
    assert [(item.document_id, item.article, item.number) for item in references] == [
        ("nd-119-2024", "10", None),
        (None, "12", "168/2024/NĐ-CP"),
    ]


def test_abbreviated_number_matches_full_metadata_suffix_but_full_is_exact():
    abbreviated = parse_reference("168/2024")
    full = parse_reference("Nghị định số 168/2024/NĐ-CP")
    assert abbreviated is not None
    assert full is not None
    metadata = {"document_number": "168/2024/NĐ-CP"}
    assert metadata_matches(metadata, abbreviated)
    assert metadata_matches(metadata, full)
    assert not metadata_matches({"document_number": "168/2024/TT-BCA"}, full)


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


def test_extracts_trailing_clause_and_point_orders() -> None:
    cases = {
        "Điều 7 Khoản 3 Nghị định 168/2024": {
            "article": "7",
            "clause": "3",
            "kind": "Nghị định",
            "number": "168/2024",
        },
        "Điều 7, khoản 3 nghị định 168/2024": {
            "article": "7",
            "clause": "3",
            "kind": "nghị định",
            "number": "168/2024",
        },
        "Điều 7 khoản 3 điểm b nghị định 168/2024": {
            "article": "7",
            "clause": "3",
            "point": "b",
            "kind": "nghị định",
            "number": "168/2024",
        },
        "Điều 7 điểm b nghị định 168/2024": {
            "article": "7",
            "point": "b",
            "kind": "nghị định",
            "number": "168/2024",
        },
    }
    for text, expected in cases.items():
        assert extract_references(text)[0].as_dict() == expected


def test_trailing_clause_does_not_merge_two_references() -> None:
    references = extract_references("Điều 10 Nghị định 119/2024; Điều 6 Nghị định 168/2024")
    assert len(references) == 2
    assert [reference.article for reference in references] == ["10", "6"]


STRUCTURAL_GOLD = [
    ("00", "nd-119-2024__dieu-10", 1, ["nd-119-2024"]),
    ("01", "Điều 6 Nghị định 168/2024", 1, ["168/2024"]),
    ("02", "Khoản 2 Điều 10 Nghị định 119/2024", 1, ["119/2024"]),
    ("03", "Điểm a khoản 2 Điều 10 Nghị định 119/2024", 1, ["119/2024"]),
    ("04", "Điều 12 của Nghị định số 168/2024/NĐ-CP", 1, ["168/2024/NĐ-CP"]),
    ("15", "nd-119-2024__dieu-10 và Điều 6 Nghị định 168/2024", 2, ["nd-119-2024", "168/2024"]),
    ("16", "Điều 10 Nghị định 119/2024; Điều 6 Nghị định 168/2024", 2, ["119/2024", "168/2024"]),
    (
        "17",
        "Khoản 2 Điều 10 Nghị định 119/2024 và Điều 12 Nghị định 168/2024",
        2,
        ["119/2024", "168/2024"],
    ),
    (
        "18",
        "Điểm a khoản 2 Điều 10 Nghị định 119/2024 và Điều 12 Nghị định 168/2024",
        2,
        ["119/2024", "168/2024"],
    ),
    (
        "19",
        "nd-119-2024__dieu-10__khoan-2__diem-a; nd-168-2024__dieu-6",
        2,
        ["nd-119-2024", "nd-168-2024"],
    ),
    (
        "20",
        "Điều 10 Nghị định 119/2024, theo Điều 6 Nghị định 168/2024",
        2,
        ["119/2024", "168/2024"],
    ),
    (
        "21",
        "Khoản 2 Điều 10 Nghị định 119/2024 và quy định liên quan Điều 6 Nghị định 168/2024",
        2,
        ["119/2024", "168/2024"],
    ),
    (
        "22",
        "Điểm a khoản 2 Điều 10 Nghị định 119/2024, đối chiếu Điều 12 Nghị định 168/2024",
        2,
        ["119/2024", "168/2024"],
    ),
    (
        "23",
        "nd-119-2024__dieu-10 và tham chiếu Điều 6 Nghị định 168/2024",
        2,
        ["nd-119-2024", "168/2024"],
    ),
    (
        "24",
        "Điều 10 Nghị định 119/2024; xem thêm Điều 12 Nghị định 168/2024",
        2,
        ["119/2024", "168/2024"],
    ),
]


def test_structural_gold_references_are_bounded_and_source_ordered() -> None:
    for _, question, expected_count, expected_numbers in STRUCTURAL_GOLD:
        references = extract_references(question)
        assert len(references) == expected_count
        assert [
            reference.number or reference.document_id for reference in references
        ] == expected_numbers
