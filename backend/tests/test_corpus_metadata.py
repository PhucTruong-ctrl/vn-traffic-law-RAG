import json

from app.legal.corpus import _read_processed


def test_processed_jsonl_preserves_supported_metadata_and_drops_unknown(tmp_path) -> None:
    row = {
        "page_content": "Point text",
        "metadata": {
            "document_id": "nd-119-2024",
            "article": "10",
            "clause": "2",
            "point": "a",
            "normalized_action": "đỗ xe trái quy định",
            "vehicle_categories": ["ô tô", "xe máy"],
            "context_scope": ["đường đô thị"],
            "provision_family": "nd-119-2024:article:10:clause:2",
            "effective_from": "2025-01-01",
            "effective_to": "2025-12-31",
            "status": "EFFECTIVE",
            "unknown": "discarded",
        },
        "unknown_row_key": True,
    }
    path = tmp_path / "chunks.jsonl"
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    chunks = _read_processed(path)

    assert len(chunks) == 1
    assert chunks[0].metadata == {
        "document_id": "nd-119-2024",
        "article": "10",
        "clause": "2",
        "point": "a",
        "normalized_action": "đỗ xe trái quy định",
        "vehicle_categories": ["ô tô", "xe máy"],
        "context_scope": ["đường đô thị"],
        "provision_family": "nd-119-2024:article:10:clause:2",
        "effective_from": "2025-01-01",
        "effective_to": "2025-12-31",
        "status": "EFFECTIVE",
        "source_kind": "markdown",
    }
