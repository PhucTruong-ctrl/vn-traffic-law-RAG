from pathlib import Path

from app.ingestion.markdown import load_markdown


def _sample(tmp_path: Path) -> Path:
    path = tmp_path / "sample.md"
    path.write_text(
        "# Điều 7. Xử phạt người điều khiển xe mô tô trên đường bộ\n"
        "1. Phạt tiền từ 100.000 đồng đến 200.000 đồng.\n"
        "a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông.\n",
        encoding="utf-8",
    )
    return path


def test_inherits_structural_metadata_without_changing_content(tmp_path: Path) -> None:
    documents = load_markdown(_sample(tmp_path), document_id="sample")

    assert [document.metadata["chunk_id"] for document in documents] == [
        "sample:0001",
        "sample:0002",
        "sample:0003",
    ]
    assert documents[2].page_content == ("Không chấp hành hiệu lệnh của đèn tín hiệu giao thông.")
    assert documents[2].metadata["normalized_action"] == documents[2].page_content
    assert documents[2].metadata["provision_family"] == "sample:article:7:clause:1"
    assert documents[2].metadata["vehicle_categories"] == ["motorcycle"]
    assert documents[2].metadata["context_scope"] == ["road_traffic"]
    assert len({document.metadata["content_sha256"] for document in documents}) == 1


def test_propagates_only_uniform_effective_interval(tmp_path: Path) -> None:
    path = _sample(tmp_path)
    effective = load_markdown(
        path,
        document_id="effective",
        status="EFFECTIVE",
        effective_from="2025-01-01",
        effective_to="2026-01-01",
    )
    partial = load_markdown(
        path,
        document_id="partial",
        status="PARTIALLY_EFFECTIVE",
        effective_from="2020-01-01",
        effective_to="2025-01-01",
    )

    assert effective[0].metadata["effective_from"] == "2025-01-01"
    assert effective[0].metadata["effective_to"] == "2026-01-01"
    assert "effective_from" not in partial[0].metadata
    assert "effective_to" not in partial[0].metadata
