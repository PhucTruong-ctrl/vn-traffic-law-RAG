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
    if result.get("status") == "verified":
        claims = result.get("claims")
        if claims is None:
            claims = []
        return {
            **result,
            "status": "VERIFIED",
            "claims": claims,
        }
    if result.get("status") == "out_of_scope" or result.get("reason_code") == "out_of_scope":
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
    outcomes: dict[str, str] = {}
    timeout_stage: str | None = None
    timing_logged = False

    def log_timing() -> None:
        nonlocal timing_logged
        if timing_logged:
            return
        timing_logged = True
        record: dict[str, Any] = {
            "total_ms": round((perf_counter() - started) * 1000, 2),
            "stages_ms": {key: value for key, value in stages.items()},
            "outcomes": {key: value for key, value in outcomes.items()},
        }
        if timeout_stage:
            record["timeout_stage"] = timeout_stage
        logger.info("chat_timing %s", record)

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
        stages["route_analyze_ms"] = round((perf_counter() - stage_started) * 1000, 2)
        outcomes["route_analyze"] = "ok"

        stage_started = perf_counter()
        user_message = add_message(
            client,
            user_id,
            session_id,
            {"content": request.question, "role": "user", "status": "pending"},
            token,
        )
        outcomes["persistence"] = "ok"

        stage_started = perf_counter()
        raw_result = rag_service.answer(
            query,
            top_k=request.top_k,
            effective_date=request.effective_date,
        )
        service_timing = raw_result.pop("_timing", None)
        result = _frontend_response(raw_result)
        stages["rag_ms"] = round((perf_counter() - stage_started) * 1000, 2)
        outcomes["rag"] = str(result.get("status", "ok"))
        if isinstance(service_timing, dict):
            for key, value in service_timing.get("stages_ms", {}).items():
                if isinstance(value, (int, float)) and 0 <= value <= 30000:
                    stages[str(key)] = round(float(value), 2)
            for key, value in service_timing.get("outcomes", {}).items():
                if isinstance(value, str) and len(value) <= 32:
                    outcomes[str(key)] = value
            if isinstance(service_timing.get("timeout_stage"), str):
                timeout_stage = service_timing["timeout_stage"][:64]

        assistant_message = add_message(
            client,
            user_id,
            session_id,
            {
                "content": result["answer"],
                "role": "assistant",
                "status": result.get("status", "INSUFFICIENT_EVIDENCE"),
                "response": result,
                "citations": result.get("citations", []),
                "metadata": {"citations": result.get("citations", [])},
            },
            token,
        )
        touch_session(client, user_id, session_id, token)
        outcomes["request"] = "ok"
        log_timing()
        return {
            **result,
            "session_id": session_id,
            "conversation_id": session_id,
            "chat_id": session_id,
            "user_message_id": user_message.get("id"),
            "assistant_message_id": assistant_message.get("id"),
        }
    except HTTPException:
        outcomes["request"] = "http_error"
        log_timing()
        raise
    except Exception:
        logger.exception("chat request failed")
        outcomes["request"] = "failed"
        log_timing()
        # Provider and schema failures are user-visible abstentions, never 5xx
        # responses or persisted unverified drafts.
        fallback = {
            "answer": "Chưa thể tạo câu trả lời đáng tin cậy từ các căn cứ đã truy xuất.",
            "citations": [],
            "claims": [],
            "status": "insufficient_evidence",
            "reason_code": "generation_failed",
        }
        try:
            assistant_message = add_message(
                client,
                user_id,
                session_id,
                {
                    "content": fallback["answer"],
                    "role": "assistant",
                    "status": fallback["status"],
                    "response": fallback,
                    "citations": [],
                    "metadata": {"citations": []},
                },
                token,
            )
            return {
                **fallback,
                "session_id": session_id,
                "conversation_id": session_id,
                "chat_id": session_id,
                "user_message_id": user_message.get("id"),
                "assistant_message_id": assistant_message.get("id"),
            }
        except Exception as persistence_exc:
            raise HTTPException(status_code=503, detail="Chat request failed") from persistence_exc


__all__ = ["ChatRequest", "chat", "router"]
