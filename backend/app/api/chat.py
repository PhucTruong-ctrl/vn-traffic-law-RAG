"""Verified legal chat endpoint."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Annotated, Any, cast

from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.api.conversations import OWNER_COOKIE, _conversation, _title, owner_key
from app.api.db import get_db
from app.observability.langfuse import emit_query_trace
from app.observability.query_trace import QueryTrace, QueryTraceStore
from app.persistence.models import Conversation, Message
from app.persistence.models import QueryTrace as QueryTraceRow
from app.workflow import build_query_graph as _production_build_query_graph
from app.workflow.graph import production_services

build_query_graph = _production_build_query_graph


def _optional_db():
    database = get_db()
    try:
        session = next(database)
    except RuntimeError:
        yield None
        return
    try:
        yield session
    finally:
        with suppress(StopIteration):
            next(database)


router = APIRouter(prefix="/api/v1", tags=["chat"])
_TRACE_STORE = QueryTraceStore()
DISCLAIMER = "This response is informational and not legal advice."


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(cast(Any, value)))
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=10_000)
    conversation_id: uuid.UUID | None = None

    @field_validator("question")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


@router.post("/chat", response_model=None)
async def chat(
    request: Annotated[ChatRequest, Body()],
    http_request: Request,
    response: Response,
    db: Annotated[Any, Depends(_optional_db)],
) -> dict[str, Any]:
    key = owner_key(response, http_request.cookies.get(OWNER_COOKIE))
    conversation = None
    user_message = assistant_message = None
    if db is not None and isinstance(db, Session) and request.conversation_id is not None:
        conversation = _conversation(db, request.conversation_id, key)
    if db is not None and isinstance(db, Session):
        if conversation is None:
            conversation = Conversation(owner_key=key, title=_title(request.question))
            db.add(conversation)
            db.flush()
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            status="COMPLETED",
            content=request.question,
        )
        assistant_message = Message(
            conversation_id=conversation.id, role="assistant", status="PENDING", content=""
        )
        db.add_all([user_message, assistant_message])
        conversation.last_activity_at = conversation.updated_at = datetime.now(UTC)
        db.flush()
    trace_id = http_request.headers.get("X-Trace-ID") or uuid.uuid4().hex
    state: dict[str, Any] = {"question": request.question, "query_date": date.today()}
    trace = QueryTrace(request.question, trace_id=trace_id, metadata={})
    try:
        if db is None and build_query_graph is _production_build_query_graph:
            raise RuntimeError("workflow database session is not configured")
        services = production_services(session=db) if db is not None else None
        graph = build_query_graph(services)
        trace.add_span("workflow", input=state)
        result = await graph.ainvoke(state)
    except (RuntimeError, ValueError) as exc:
        result = {
            "verification_result": {
                "status": "ABSTAIN",
                "reason_code": "WORKFLOW_UNAVAILABLE",
                "error": str(exc),
            },
            "final_response": {},
        }
    trace.finish(result)
    if isinstance(db, Session):
        verification = result.get("verification_result") or {}
        row = QueryTraceRow(
            trace_id=trace_id,
            question=request.question,
            intent="UNKNOWN",
            query_date=None,
            vehicle_type=None,
            response_status=str(verification.get("status", "UNKNOWN")),
            citations=_citations(result, result.get("final_response") or {}),
            verification_summary=_json_safe(verification),
        )
        db.add(row)
        db.flush()
    elif db is not None:
        db.add(trace)
        db.commit()
    with suppress(Exception):
        emit_query_trace(trace)
    payload = _response_payload(result, trace_id)
    if isinstance(db, Session) and assistant_message and conversation and user_message:
        assistant_message.content = payload.get("answer") or (payload.get("abstention") or {}).get(
            "reason_code", ""
        )
        assistant_message.status = "COMPLETED"
        query_trace = db.query(QueryTraceRow).filter(QueryTraceRow.trace_id == trace_id).first()
        if query_trace is not None:
            assistant_message.query_trace_id = query_trace.id
        conversation.last_activity_at = conversation.updated_at = datetime.now(UTC)
        db.commit()
        payload.update(
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
        )
    return payload


_WORKFLOW_STAGES = (
    ("analyze_query", "Phân tích câu hỏi"),
    ("resolve_temporal", "Xác định hiệu lực theo thời gian"),
    ("retrieve_parallel", "Tra cứu điều khoản"),
    ("check_evidence", "Kiểm tra bằng chứng"),
    ("verify", "Xác minh câu trả lời"),
)


def _response_payload(result: dict[str, Any], trace_id: str) -> dict[str, Any]:
    final = result.get("final_response") or {}
    verification = result.get("verification_result") or {}
    citations = _citations(result, final)
    status = "VERIFIED" if verification.get("status") == "VALID" and citations else "ABSTAINED"
    return {
        "status": status,
        "answer": final.get("answer_summary") if status == "VERIFIED" else None,
        "claims": final.get("claims", []) if status == "VERIFIED" else [],
        "citations": citations if status == "VERIFIED" else [],
        "metadata": {},
        "abstention": None
        if status == "VERIFIED"
        else {"reason_code": verification.get("reason_code", "INSUFFICIENT_EVIDENCE")},
        "disclaimer": DISCLAIMER,
        "trace_id": trace_id,
    }


async def _run_workflow(
    request: ChatRequest,
    http_request: Request,
    db: Any,
    progress: Any = None,
) -> dict[str, Any]:
    trace_id = http_request.headers.get("X-Trace-ID") or uuid.uuid4().hex
    state: dict[str, Any] = {"question": request.question, "query_date": date.today()}
    trace = QueryTrace(request.question, trace_id=trace_id, metadata={})
    try:
        if db is None and build_query_graph is _production_build_query_graph:
            raise RuntimeError("workflow database session is not configured")
        services = production_services(session=db) if db is not None else None
        graph = build_query_graph(services)
        trace.add_span("workflow", input=state)
        if progress:
            await progress("workflow_started", "Bắt đầu tra cứu")
        result: dict[str, Any] = {}
        async for event in graph.astream(state, stream_mode="updates"):
            if not isinstance(event, dict):
                continue
            for node, update in event.items():
                result.update(update if isinstance(update, dict) else {})
                if progress:
                    await progress(node, dict(_WORKFLOW_STAGES).get(node, node))
        trace.add_span(
            "workflow_result",
            output={"status": (result.get("verification_result") or {}).get("status")},
        )
    except (RuntimeError, ValueError) as exc:
        result = {
            "verification_result": {
                "status": "ABSTAIN",
                "reason_code": "WORKFLOW_UNAVAILABLE",
                "error": str(exc),
            },
            "final_response": {},
        }
    trace.finish(result)
    if db is None:
        _TRACE_STORE.save(trace)
    else:
        verification = result.get("verification_result") or {}
        plan = result.get("query_understanding")
        db.add(
            QueryTraceRow(
                trace_id=trace_id,
                question=request.question,
                intent=str(getattr(plan, "intent", "UNKNOWN")),
                query_date=None,
                vehicle_type=None,
                response_status=str(verification.get("status", "UNKNOWN")),
                citations=_citations(result, result.get("final_response") or {}),
                verification_summary=_json_safe(verification),
            )
        )
        db.flush()
    with suppress(Exception):
        emit_query_trace(trace)
    return {"trace_id": trace_id, "payload": _response_payload(result, trace_id)}


async def chat_events(
    question: str,
    http_request: Request,
    db: Annotated[Any, Depends(_optional_db)],
) -> StreamingResponse:
    request = ChatRequest(question=question)
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def progress(stage: str, message: str) -> None:
        await queue.put({"stage": stage, "message": message})

    async def stream() -> AsyncIterator[str]:
        task = asyncio.create_task(_run_workflow(request, http_request, db, progress))
        try:
            while True:
                if task.done() and queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                except TimeoutError:
                    continue
                if event is None:
                    break
                yield f"event: progress\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            outcome = await task
            yield (
                f"event: result\ndata: "
                f"{json.dumps(outcome['payload'], ensure_ascii=False, default=str)}\n\n"
            )
        except asyncio.CancelledError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _normalized_bbox(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    keys = ("left", "top", "right", "bottom")
    if any(key not in value for key in keys):
        return None
    try:
        return {key: float(value[key]) for key in keys}
    except (TypeError, ValueError):
        return None


def _citations(result: dict[str, Any], final: dict[str, Any]) -> list[dict[str, Any]]:
    context = result.get("expanded_context") or result.get("context_package") or []
    if isinstance(context, dict):
        context = [
            item
            for side in context.values()
            for item in (side.results if hasattr(side, "results") else side)
        ]
    elif hasattr(context, "results"):
        context = context.results
    records = {
        getattr(item, "provision_id", None): item
        for item in context
        if getattr(item, "provision_id", None)
        and getattr(item, "review_status", "ACCEPTED") == "ACCEPTED"
    }
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    claims = final.get("claims", [])
    if not isinstance(claims, list):
        return []
    for claim in claims:
        if not isinstance(claim, dict):
            return []
        provision_ids = claim.get("provision_ids", [])
        if not isinstance(provision_ids, list) or any(
            not isinstance(provision_id, str) or not provision_id for provision_id in provision_ids
        ):
            return []
        if len(set(provision_ids)) != len(provision_ids):
            return []
        for provision_id in provision_ids:
            if provision_id in seen:
                return []
            item = records.get(provision_id)
            if item is None:
                return []
            seen.add(provision_id)
            citation = {
                "provision_id": item.provision_id,
                "document_id": item.document_id,
                "document_number": item.document_number,
                "article": item.article,
                "clause": item.clause,
                "point": item.point,
                "parent_context": item.parent_context,
                "source_text": getattr(item, "source_text", None),
                "page_number": getattr(item, "page_number", None),
                "legal_context": "\n\n".join(
                    part
                    for part in (
                        item.parent_context,
                        item.source_text or item.text,
                    )
                    if part
                ),
                "bbox": _normalized_bbox(getattr(item, "bbox", None)),
            }
            source_url = getattr(item, "source_url", None)
            if isinstance(source_url, str) and source_url:
                citation["source_url"] = source_url
            for identity_field in (
                "provision_version",
                "document_version_id",
                "effective_from",
                "effective_to",
                "source_id",
            ):
                identity_value = getattr(item, identity_field, None)
                if identity_value is not None:
                    if hasattr(identity_value, "isoformat"):
                        identity_value = identity_value.isoformat()
                    citation[identity_field] = identity_value
            citations.append(citation)
    return (
        citations if len(citations) == sum(len(c.get("provision_ids", [])) for c in claims) else []
    )


__all__ = ["ChatRequest", "DISCLAIMER", "router"]
