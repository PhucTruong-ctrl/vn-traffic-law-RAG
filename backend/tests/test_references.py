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
