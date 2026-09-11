from langchain_core.documents import Document

from app.rag.cross_refs import (
    expand_cross_references,
    expand_sibling_completions,
    extract_cross_references,
)


def test_extracts_bounded_references():
    refs = extract_cross_references("Điều 1, Điều 2, Điều 3, Điều 4, Điều 5")
    assert [ref.article for ref in refs] == ["1", "2", "3", "4"]


def test_expands_one_hop_and_deduplicates_without_recursion():
    original = Document(page_content="Căn cứ Điều 2.", metadata={"chunk_id": "a"})
    referenced = Document(page_content="Căn cứ Điều 3.", metadata={"article": "2", "chunk_id": "b"})
    recursive = Document(page_content="Điều 3", metadata={"article": "3", "chunk_id": "c"})

    result = expand_cross_references([original], lambda ref: [referenced, referenced, recursive])
    assert result[0] is original
    assert [doc.metadata["chunk_id"] for doc in result] == ["a", "b", "c"]
    assert all(doc.metadata["added_by"] == "CROSS_REFERENCE" for doc in result[1:])
    assert all(
        doc.metadata["depth"] == 1 and doc.metadata["source_id"] == "a" for doc in result[1:]
    )
    assert referenced.metadata == {"article": "2", "chunk_id": "b"}
    assert recursive.metadata == {"article": "3", "chunk_id": "c"}


def test_duplicate_reference_from_distinct_originals_keeps_first_source():
    first = Document(page_content="Điều 2", metadata={"chunk_id": "first"})
    second = Document(page_content="Điều 2", metadata={"chunk_id": "second"})
    target = Document(page_content="target", metadata={"provision_id": "p", "source": "law"})

    result = expand_cross_references([first, second], lambda _: [target])
    assert len(result) == 3
    assert result[-1].metadata["source_id"] == "first"
    assert result[-1].metadata["provision_id"] == "p"
    assert target.metadata == {"provision_id": "p", "source": "law"}


def test_expansion_respects_total_document_cap_and_original_precedence():
    originals = [
        Document(page_content="Điều 1, Điều 2, Điều 3, Điều 4", metadata={"chunk_id": "a"}),
        Document(page_content="Nội dung gốc", metadata={"chunk_id": "b"}),
    ]
    referenced = [
        Document(page_content=f"ref-{index}", metadata={"chunk_id": str(index)})
        for index in range(8)
    ]
    calls: list[object] = []

    def resolve(reference, *, limit):
        calls.append((reference, limit))
        return referenced

    result = expand_cross_references(
        originals,
        resolve,
        max_references=4,
        max_documents=4,
    )

    assert result[:2] == originals
    assert len(result) == 4
    assert len(calls) == 1
    assert calls[0][1] == 2


def test_unresolved_reference_preserves_originals():
    original = Document(page_content="Điều 99", metadata={"chunk_id": "a"})
    assert expand_cross_references([original], lambda _: []) == [original]


def test_sibling_completion_is_bounded_provenanced_and_capped():
    original = Document(
        page_content="Vi phạm bị phạt tiền.",
        metadata={"chunk_id": "a", "document_id": "law", "article": "7"},
    )
    sibling = Document(
        page_content="Ngoài ra bị trừ điểm giấy phép.",
        metadata={"chunk_id": "b", "document_id": "law", "article": "7"},
    )
    unrelated = Document(
        page_content="Bị tước quyền sử dụng.",
        metadata={"chunk_id": "c", "document_id": "other", "article": "7"},
    )

    result = expand_sibling_completions(
        [original],
        lambda _document, *, limit: [sibling, sibling, unrelated][:limit],
        max_documents=2,
        max_siblings=2,
    )

    assert [doc.metadata["chunk_id"] for doc in result] == ["a", "b"]
    assert result[1].metadata["added_by"] == "SIBLING"
    assert result[1].metadata["depth"] == 0
    assert result[1].metadata["source_id"] == "a"
    assert sibling.metadata == {
        "chunk_id": "b",
        "document_id": "law",
        "article": "7",
    }
