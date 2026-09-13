"""HTTP interface for the hybrid RAG chat module."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.api import bearer, get_current_user
from app.chats.followup import build_followup_query
from app.chats.service import add_message, create_session, recent_messages, touch_session
from app.database.session import SupabaseClient, get_db

from .analyzer import resolve_vehicle_followup
from .schemas import ChatRequest
from .service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["rag"])
rag_service = RAGService()


def _frontend_response(result: dict[str, Any]) -> dict[str, Any]:
    citations = result.get("citations", [])
    if result.get("status") == "complete":
        claims = result.get("claims")
        if claims is None:
            claims = [
                {
                    "claim": citation.get("excerpt") or result["answer"],
                    "provision_ids": [citation["source_id"]],
                }
                for citation in citations
                if citation.get("source_id")
            ]
        return {
            **result,
            "status": "VERIFIED",
            "claims": claims,
        }
    if result.get("status") == "out_of_scope":
        return {
            **result,
            "status": "OUT_OF_SCOPE",
            "claims": [],
            "abstention": {"reason_code": result.get("reason_code", "OUT_OF_SCOPE")},
        }
    if result.get("status") == "insufficient_evidence":
        return {
            **result,
            "status": "INSUFFICIENT_EVIDENCE",
            "claims": [],
            "abstention": {"reason_code": result.get("reason_code", "INSUFFICIENT_EVIDENCE")},
        }
    return result


@router.post("/chat")
def chat(
    request: ChatRequest,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
) -> dict[str, Any]:
    token = credentials.credentials
    started = perf_counter()
    stages: dict[str, float] = {}
    try:
        stage_started = perf_counter()
        user_id = str(user.get("id") or user.get("user_id") or user["sub"])
        session = (
            touch_session(client, user_id, request.session_id, token)
            if request.session_id
            else create_session(client, user_id, request.title or request.question[:80], token)
        )
        session_id = str(session["id"])
        history = recent_messages(client, user_id, session_id, token) if request.session_id else []
        query = resolve_vehicle_followup(request.question, history)
        if query == request.question.strip():
            query = build_followup_query(query, history)
        stages["history_ms"] = round((perf_counter() - stage_started) * 1000, 2)

        stage_started = perf_counter()
        user_message = add_message(
            client,
            user_id,
            session_id,
            {"content": request.question, "role": "user", "status": "pending"},
            token,
        )
        stages["persistence_ms"] = round((perf_counter() - stage_started) * 1000, 2)

        stage_started = perf_counter()
        result = _frontend_response(
            rag_service.answer(
                query,
                top_k=request.top_k,
                effective_date=request.effective_date,
            )
        )
        stages["rag_ms"] = round((perf_counter() - stage_started) * 1000, 2)

        assistant_message = add_message(
            client,
            user_id,
            session_id,
            {
                "content": result["answer"],
                "role": "assistant",
                "status": result.get("status", "complete"),
                "response": result,
                "citations": result.get("citations", []),
                "metadata": {"citations": result.get("citations", [])},
            },
            token,
        )
        touch_session(client, user_id, session_id, token)
        stages["total_ms"] = round((perf_counter() - started) * 1000, 2)
        logger.info("chat_stage_timings %s", stages)
        return {
            **result,
            "session_id": session_id,
            "conversation_id": session_id,
            "chat_id": session_id,
            "user_message_id": user_message.get("id"),
            "assistant_message_id": assistant_message.get("id"),
        }
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


__all__ = ["ChatRequest", "chat", "router"]
