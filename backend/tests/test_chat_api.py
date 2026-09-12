from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType

import pytest

from app.chats.service import add_feedback
from app.legal import api as legal_api
from app.rag.schemas import ChatResponse, Citation
from app.rag.service import RAGService


def test_retriever_uses_remote_qdrant_settings(monkeypatch) -> None:
    from app.rag import retrieval

    class Settings:
        url = "https://qdrant.example"
        timeout = 17
        collection = "legal_hybrid"
        path = "/tmp/unused"

    class EmbeddingSettings:
        model = "embedding-model"
        openrouter_api_key = "key"
        openrouter_base_url = "https://openrouter.example"

    class Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Store:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class RetrievalMode:
        HYBRID = "hybrid"

    class Embeddings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Sparse:
        def __init__(self, name):
            self.name = name

    openai_module = ModuleType("langchain_openai")
    openai_module.OpenAIEmbeddings = Embeddings
    qdrant_module = ModuleType("langchain_qdrant")
    qdrant_module.FastEmbedSparse = Sparse
    qdrant_module.QdrantVectorStore = Store
    qdrant_module.RetrievalMode = RetrievalMode

    monkeypatch.setattr(retrieval, "get_qdrant_settings", lambda: Settings())
    monkeypatch.setattr(retrieval, "get_embedding_settings", lambda: EmbeddingSettings())
    monkeypatch.setattr(retrieval, "QdrantClient", Client)
    monkeypatch.setitem(sys.modules, "langchain_openai", openai_module)
    monkeypatch.setitem(sys.modules, "langchain_qdrant", qdrant_module)

    store = retrieval.Retriever()._store_for_query()

    assert store.kwargs["client"].kwargs == {
        "url": "https://qdrant.example",
        "timeout": 17,
    }
    assert store.kwargs["collection_name"] == "legal_hybrid"
    assert store.kwargs["retrieval_mode"] == "hybrid"


def test_chitchat_does_not_call_retriever() -> None:
    class NeverRetriever:
        def retrieve(self, *args, **kwargs):
            raise AssertionError("chitchat must not retrieve")

    result = RAGService(NeverRetriever()).answer("hi")
    assert result["answer"]
    assert result["status"] == "GREETING"


def test_exact_reference_mismatch_abstains() -> None:
    from langchain_core.documents import Document

    result = RAGService().answer(
        "Điều 6 Nghị định 100/2019 quy định gì?",
        chunks=[
            Document(
                page_content="Nội dung điều 6.",
                metadata={"article": "Điều 7", "document_number": "100/2019"},
            )
        ],
    )

    assert result["status"] == "insufficient_evidence"
    assert result["reason_code"] == "reference_not_found"


def test_exact_reference_match_allows_answer(monkeypatch) -> None:
    from langchain_core.documents import Document

    monkeypatch.setattr("app.rag.service.generate_answer", lambda *_args, **_kwargs: "Đáp án")
    result = RAGService().answer(
        "Điều 6 Nghị định 100/2019 quy định gì?",
        chunks=[
            Document(
                page_content="Nội dung điều 6.",
                metadata={
                    "chunk_id": "chunk-6",
                    "document_id": "100/2019",
                    "article": "Điều 6",
                    "document_number": "100/2019",
                },
            )
        ],
    )

    assert result["status"] == "complete"


def test_release_chat_contract_rejects_wrong_reference_or_citation() -> None:
    from scripts.verify_release_authenticated import require_chat_contract

    valid = {
        "status": "complete",
        "answer": "Theo quy định.",
        "citations": [
            {
                "source_id": "chunk-1",
                "document_id": "nd-168-2024",
                "article": "Điều 6",
                "excerpt": "Nội dung.",
            }
        ],
    }
    require_chat_contract(valid, "valid", required_reference="168")
    with pytest.raises(RuntimeError, match="required reference"):
        require_chat_contract(valid, "wrong-reference", required_reference="100")
    invalid = {**valid, "citations": [{**valid["citations"][0], "excerpt": ""}]}
    with pytest.raises(RuntimeError, match="excerpt"):
        require_chat_contract(invalid, "missing-excerpt")


def test_vehicle_penalty_query_retrieves_all_categories(monkeypatch) -> None:
    from langchain_core.documents import Document

    monkeypatch.setattr(
        "app.rag.service.generate_answer",
        lambda *_args, **_kwargs: "Mức phạt được xác định theo từng loại phương tiện.",
    )

    class RecordingRetriever:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def retrieve(self, query: str, **_: object) -> list[Document]:
            self.queries.append(query)
            return [
                Document(
                    page_content="Theo quy định hiện hành, hành vi này bị xử phạt.",
                    metadata={
                        "chunk_id": "chunk-vehicle",
                        "document_id": "law-168",
                        "source_file": "traffic-law.md",
                        "document_name": "Nghị định về xử phạt giao thông",
                        "article": "Điều 6",
                    },
                )
            ]

    retriever = RecordingRetriever()
    result = RAGService(retriever).answer("Vượt đèn đỏ thì mức phạt bao nhiêu?")

    assert result["status"] == "complete"
    assert result["citations"]
    vehicle_queries = [query for query in retriever.queries if "đối với" in query]
    assert len(vehicle_queries) == 3
    for category in (
        "đối với ô tô",
        "đối với xe mô tô, xe gắn máy",
        "đối với xe thô sơ",
    ):
        matching = [query for query in vehicle_queries if query.endswith(category)]
        assert len(matching) == 1
        assert "vượt đèn đỏ" in matching[0].lower()


@dataclass
class Chunk:
    text: str
    metadata: dict


def test_feedback_checks_message_ownership_before_insert(supabase_client) -> None:
    supabase_client.responses.append([])
    with pytest.raises(Exception) as exc:
        add_feedback(supabase_client, "owner-1", "session-1", "message-1", {"rating": 1})
    assert getattr(exc.value, "status_code", None) == 404
    assert len(supabase_client.calls) == 1
    assert supabase_client.calls[0]["params"] == {
        "id": "eq.message-1",
        "session_id": "eq.session-1",
        "user_id": "eq.owner-1",
        "select": "*",
    }


def test_feedback_duplicate_is_rejected(supabase_client) -> None:
    supabase_client.responses.extend(
        [[{"id": "message-1"}], [{"id": "feedback-1"}], [{"id": "message-1"}], []]
    )
    assert add_feedback(supabase_client, "owner-1", "session-1", "message-1", {"rating": 1}) == {
        "id": "feedback-1"
    }

    with pytest.raises(Exception) as exc:
        add_feedback(supabase_client, "owner-1", "session-1", "message-1", {"rating": 0})

    assert getattr(exc.value, "status_code", None) == 409
    assert supabase_client.calls[2]["params"] == {
        "id": "eq.message-1",
        "session_id": "eq.session-1",
        "user_id": "eq.owner-1",
        "select": "*",
    }


def test_authenticated_chat_creates_session_and_persists_snapshots(
    client, supabase_client, monkeypatch
) -> None:
    supabase_client.auth_response = {"id": "user-1", "email": "person@example.com"}
    citation = {
        "source_id": "chunk-1",
        "document_id": "nd-100-2019",
        "document_title": "Nghị định 100",
        "source_file": "nd100.md",
        "excerpt": "Tốc độ tối đa...",
    }
    rag_result = {
        "answer": "Được đi tối đa 50 km/h.",
        "citations": [citation],
        "status": "complete",
    }
    monkeypatch.setattr("app.chats.api.rag_service.answer", lambda question, **kwargs: rag_result)
    supabase_client.responses.extend(
        [
            [{"id": "user-1", "email": "person@example.com"}],
            [{"id": "session-1", "user_id": "user-1", "title": "New chat"}],
            [{"id": "user-message", "role": "user", "content": "Tốc độ?"}],
            [{"id": "assistant-message", "role": "assistant", "content": rag_result["answer"]}],
            [{"id": "session-1", "user_id": "user-1", "deleted": False}],
        ]
    )
    response = client.post(
        "/api/v1/chat",
        json={"question": "Tốc độ?", "title": "New chat"},
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    body = response.json()
    inserts = [call for call in supabase_client.calls if call["method"] == "POST"]
    assistant_insert = next(
        call["data"] for call in inserts if call["data"].get("role") == "assistant"
    )
    assert assistant_insert["response"]["answer"] == rag_result["answer"]
    assert assistant_insert["citations"] == [citation]
    assert body["session_id"] == "session-1"
    assert body["answer"] == rag_result["answer"]
    assert body["citations"] == [citation]


def test_authenticated_chat_normalizes_legacy_rag_result_for_frontend(
    client, supabase_client, monkeypatch
) -> None:
    supabase_client.auth_response = {"id": "user-1"}
    citation = {
        "source_id": "chunk-1",
        "document_id": "nd-168-2024",
        "document_title": "Nghị định 168/2024/NĐ-CP",
        "source_file": "nd168.md",
        "excerpt": "Dùng tay cầm và sử dụng điện thoại...",
    }
    rag_result = {
        "answer": "Không được dùng điện thoại khi điều khiển xe.",
        "citations": [citation],
        "status": "complete",
    }
    monkeypatch.setattr("app.chats.api.rag_service.answer", lambda question, **kwargs: rag_result)
    supabase_client.responses.extend(
        [
            [{"id": "user-1"}],
            [{"id": "session-1", "user_id": "user-1"}],
            [{"id": "user-message"}],
            [{"id": "assistant-message"}],
            [{"id": "session-1", "user_id": "user-1", "deleted": False}],
        ]
    )
    response = client.post(
        "/api/v1/chat",
        json={"question": "Có được dùng điện thoại khi đang lái xe không?"},
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "VERIFIED"
    assert response.json()["claims"] == [
        {"claim": citation["excerpt"], "provision_ids": [citation["source_id"]]}
    ]


def test_cross_owner_session_is_not_visible(client, supabase_client) -> None:
    supabase_client.auth_response = {"id": "user-2"}
    supabase_client.responses.extend([[{"id": "user-2"}], []])
    response = client.get(
        "/api/v1/chats/session-1",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 404


def test_chat_response_preserves_citation_metadata_shape() -> None:
    citation = Citation(
        source_id="chunk-1",
        document_id="nd-100-2019",
        document_number="100/2019/NĐ-CP",
        document_title="Nghị định 100/2019/NĐ-CP",
        article="Điều 6",
        clause="Khoản 1",
        point="a",
        page=4,
        source_file="data/sources/nd100.md",
        excerpt="Tốc độ tối đa...",
        pdf_url="https://example.test/nd100.pdf",
    )
    response = ChatResponse(answer="Theo quy định.", citations=[citation])
    assert response.model_dump()["citations"] == [citation.model_dump()]


def test_unauthenticated_chat_is_rejected(client) -> None:
    response = client.post("/api/v1/chat", json={"question": "Tốc độ tối đa là bao nhiêu?"})
    assert response.status_code == 401


def test_rename_requires_non_blank_title(client) -> None:
    response = client.patch(
        "/api/v1/chats/session-1", json={"title": "   "}, headers={"Authorization": "Bearer token"}
    )
    assert response.status_code == 401


def test_legal_explorer_route_returns_document_provisions(client, monkeypatch) -> None:
    monkeypatch.setattr(
        legal_api,
        "chunks",
        lambda: [
            Chunk(
                text="Người lái xe phải chấp hành hiệu lệnh.",
                metadata={
                    "chunk_id": "c-1",
                    "document_id": "nd100",
                    "document_name": "Nghị định 100",
                    "article": "Điều 6",
                    "source_file": "nd100.md",
                    "source_type": "markdown",
                },
            )
        ],
    )
    response = client.get("/api/v1/legal-documents/nd100/provisions?article=Điều%206")
    assert response.status_code == 200
    assert response.json() == [
        {
            "chunk_id": "c-1",
            "document_id": "nd100",
            "document_name": "Nghị định 100",
            "article": "Điều 6",
            "clause": None,
            "point": None,
            "text": "Người lái xe phải chấp hành hiệu lệnh.",
            "source": {
                "source_file": "nd100.md",
                "source_url": None,
                "source_kind": "markdown",
                "source_type": "markdown",
                "pdf_url": None,
                "retrieved_at": None,
            },
        }
    ]
