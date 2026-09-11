from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.chats.service import add_feedback
from app.legal import api as legal_api
from app.rag.schemas import ChatResponse, Citation
from app.rag.service import RAGService


def test_chitchat_does_not_call_retriever() -> None:
    class NeverRetriever:
        def retrieve(self, *args, **kwargs):
            raise AssertionError("chitchat must not retrieve")

    result = RAGService(NeverRetriever()).answer("hi")
    assert result["answer"]
    assert result["status"] == "chitchat"


def test_clarification_response_skips_retrieval() -> None:
    class NeverRetriever:
        def retrieve(self, *args, **kwargs):
            raise AssertionError("clarification must not retrieve")

    result = RAGService(NeverRetriever()).answer("Vượt đèn đỏ thì mức phạt bao nhiêu?")

    assert result["status"] == "clarification_required"
    assert result["citations"] == []
    assert result["options"] == ["ô tô", "xe mô tô, xe gắn máy", "xe thô sơ"]


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


def test_authenticated_chat_creates_session_and_persists_snapshots(
    client, supabase_client, monkeypatch
) -> None:
    supabase_client.auth_response = {"id": "user-1", "email": "person@example.com"}
    monkeypatch.setattr(
        "app.chats.api.rag_service.answer",
        lambda question, **kwargs: {
            "answer": "Được đi tối đa 50 km/h.",
            "citations": [
                {
                    "document": "Nghị định 100",
                    "source_file": "nd100.md",
                    "excerpt": "Tốc độ tối đa...",
                }
            ],
        },
    )
    supabase_client.responses.extend(
        [
            [{"id": "user-1", "email": "person@example.com"}],
            [{"id": "session-1", "user_id": "user-1", "title": "New chat"}],
            [{"id": "session-1", "user_id": "user-1", "deleted": False}],
            [{"id": "user-message", "role": "user", "content": "Tốc độ?"}],
            [{"id": "session-1", "user_id": "user-1", "deleted": False}],
            [
                {
                    "id": "assistant-message",
                    "role": "assistant",
                    "content": "Được đi tối đa 50 km/h.",
                    "response": "Được đi tối đa 50 km/h.",
                    "citations": [{"document": "Nghị định 100"}],
                    "metadata": {"source": "rag"},
                }
            ],
        ]
    )
    response = client.post(
        "/api/v1/chat",
        json={"question": "Tốc độ?", "title": "New chat"},
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-1"
    assert body["answer"] == "Được đi tối đa 50 km/h."
    assert body["citations"][0]["document"] == "Nghị định 100"
    inserts = [call for call in supabase_client.calls if call["method"] == "POST"]
    message_inserts = {
        call["data"]["role"]: call["data"]
        for call in inserts
        if call["data"].get("role") in {"user", "assistant"}
    }
    assert message_inserts["user"]["role"] == "user"
    assert message_inserts["user"]["content"] == "Tốc độ?"
    assert message_inserts["user"]["session_id"] == "session-1"
    assert message_inserts["assistant"]["role"] == "assistant"
    assert message_inserts["assistant"]["content"] == "Được đi tối đa 50 km/h."
    assert message_inserts["assistant"]["response"] == {
        "answer": "Được đi tối đa 50 km/h.",
        "citations": [
            {
                "document": "Nghị định 100",
                "source_file": "nd100.md",
                "excerpt": "Tốc độ tối đa...",
            }
        ],
    }
    assert message_inserts["assistant"]["citations"] == [
        {
            "document": "Nghị định 100",
            "source_file": "nd100.md",
            "excerpt": "Tốc độ tối đa...",
        }
    ]
    assert message_inserts["assistant"]["metadata"] == {
        "citations": [
            {
                "document": "Nghị định 100",
                "source_file": "nd100.md",
                "excerpt": "Tốc độ tối đa...",
            }
        ]
    }


def test_authenticated_chat_normalizes_legacy_rag_result_for_frontend(
    client, supabase_client, monkeypatch
) -> None:
    supabase_client.auth_response = {"id": "user-1"}
    monkeypatch.setattr(
        "app.chats.api.rag_service.answer",
        lambda question, **kwargs: {
            "answer": "Không được dùng điện thoại khi điều khiển xe.",
            "citations": [
                {
                    "document": "Nghị định 168/2024/NĐ-CP",
                    "source_file": "nd168.md",
                    "excerpt": "Dùng tay cầm và sử dụng điện thoại...",
                }
            ],
            "status": "complete",
        },
    )
    supabase_client.responses.extend(
        [
            [{"id": "user-1"}],
            [{"id": "session-1", "user_id": "user-1"}],
            [{"id": "user-message"}],
            [{"id": "assistant-message"}],
            [{"id": "session-1", "user_id": "user-1"}],
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
        {
            "claim": "Dùng tay cầm và sử dụng điện thoại...",
            "provision_ids": [],
        }
    ]


def test_session_reload_returns_owner_messages(client, supabase_client) -> None:
    supabase_client.auth_response = {"id": "user-1"}
    supabase_client.responses.extend(
        [
            [{"id": "user-1"}],
            [{"id": "session-1", "user_id": "user-1", "deleted": False}],
            [
                {"id": "m1", "role": "user", "content": "Tốc độ?"},
                {"id": "m2", "role": "assistant", "content": "50 km/h", "citations": []},
            ],
        ]
    )
    response = client.get(
        "/api/v1/chats/session-1",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    assert [message["id"] for message in response.json()["messages"]] == ["m1", "m2"]


def test_session_reload_preserves_assistant_response_contract(client, supabase_client) -> None:
    supabase_client.auth_response = {"id": "user-1"}
    assistant_response = {
        "status": "VERIFIED",
        "answer": "Không được dùng điện thoại khi điều khiển xe.",
        "claims": [{"claim": "Dùng tay cầm và sử dụng điện thoại..."}],
        "citations": [
            {
                "document": "Nghị định 168/2024/NĐ-CP",
                "excerpt": "Dùng tay cầm và sử dụng điện thoại...",
            }
        ],
    }
    supabase_client.responses.extend(
        [
            [{"id": "user-1"}],
            [{"id": "session-1", "user_id": "user-1", "deleted": False}],
            [
                {"id": "m1", "role": "user", "content": "Có được dùng điện thoại không?"},
                {
                    "id": "m2",
                    "role": "assistant",
                    "content": assistant_response["answer"],
                    "response": assistant_response,
                    "citations": assistant_response["citations"],
                },
            ],
        ]
    )

    response = client.get(
        "/api/v1/chats/session-1",
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 200
    assert response.json()["messages"][1]["response"] == assistant_response


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
        document="Nghị định 100/2019/NĐ-CP",
        article="Điều 6",
        clause="Khoản 1",
        point="a",
        page=4,
        source_file="data/sources/nd100.md",
        excerpt="Tốc độ tối đa...",
        pdf_url="https://example.test/nd100.pdf",
    )
    response = ChatResponse(answer="Theo quy định.", citations=[citation])
    assert response.model_dump() == {
        "answer": "Theo quy định.",
        "citations": [citation.model_dump()],
        "status": None,
        "debug": None,
    }


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
                "source_type": "markdown",
                "retrieved_at": None,
            },
        }
    ]
