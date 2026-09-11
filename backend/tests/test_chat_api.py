from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.chats.service import add_feedback
from app.legal import api as legal_api
from app.rag.schemas import ChatResponse, Citation


@dataclass
class Chunk:
    text: str
    metadata: dict


def test_feedback_checks_message_ownership_before_insert(supabase_client) -> None:
    supabase_client.responses.append([])
    with pytest.raises(Exception) as exc:
        add_feedback(supabase_client, "owner-1", "session-1", "message-1", {"rating": 5})
    assert getattr(exc.value, "status_code", None) == 404
    assert len(supabase_client.calls) == 1
    assert supabase_client.calls[0]["params"] == {
        "id": "eq.message-1",
        "session_id": "eq.session-1",
        "user_id": "eq.owner-1",
        "select": "*",
    }


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
