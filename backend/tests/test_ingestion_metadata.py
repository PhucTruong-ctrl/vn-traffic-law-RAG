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


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "markers.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_marker_variants_and_inheritance(tmp_path: Path) -> None:
    docs = load_markdown(
        _write(
            tmp_path,
            "# Điều 1. Tựa đề\n"
            "1. Khoản một\n"
            "a) Điểm a\n"
            "b)\tĐiểm b\n"
            "đ)\u00a0Điểm đ\n"
            "2) Khoản hai\n"
            "Nội dung khoản hai.\n"
            "3. Khoản ba\n"
            "a\n)\nĐiểm tách dòng\n"
            "b) Điểm kế tiếp\n"
            "Dòng tiếp tục.\n"
            "Không phải marker 1.5 nội dung.\n",
        ),
        document_id="markers",
    )
    # docs[0] is the article heading chunk: it inherits `article` but carries no
    # clause/point, exactly as before this fix.
    assert docs[0].metadata.get("article") == "1"
    assert docs[0].metadata.get("clause") is None
    assert docs[0].metadata.get("point") is None
    assert [d.metadata.get("clause") for d in docs] == [
        None,
        "1",
        "1",
        "1",
        "1",
        "2",
        "3",
        "3",
        "3",
    ]
    # `2)` opens a new clause while `b)`/`đ)` must not leak into the next clause; the
    # split marker `a` + `)` is a point of clause 3, which the parser used to swallow
    # into the clause-3 chunk.
    assert [d.metadata.get("point") for d in docs] == [
        None,
        None,
        "a",
        "b",
        "đ",
        None,
        None,
        "a",
        "b",
    ]
    assert "Điểm tách dòng" in docs[7].page_content
    assert docs[7].metadata.get("clause") == "3"
    assert docs[7].metadata.get("point") == "a"
    assert "Dòng tiếp tục." in docs[8].page_content
    assert "Không phải marker 1.5 nội dung." in docs[8].page_content


def test_article_without_clause_and_bare_article(tmp_path: Path) -> None:
    docs = load_markdown(
        _write(tmp_path, "Điều 12.\nNội dung điều.\nĐiều 13. Có tiêu đề.\n"),
        document_id="articles",
    )
    assert docs[0].metadata["article"] == "12"
    assert docs[0].page_content == "Nội dung điều."
    assert docs[1].metadata["article"] == "13"
    assert docs[1].page_content == "Có tiêu đề."
