"""Verified legal chat endpoint."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Annotated, Any, cast
from urllib.parse import urlparse

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
logger = logging.getLogger(__name__)


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
            "status": "WORKFLOW_UNAVAILABLE",
            "error_code": "WORKFLOW_UNAVAILABLE",
            "error": str(exc),
            "verification_result": {
                "status": "ERROR",
                "public_status": "INSUFFICIENT_EVIDENCE",
                "reason_code": "WORKFLOW_UNAVAILABLE",
                "error": str(exc),
            },
            "final_response": {},
        }
    trace.finish(result)
    if isinstance(db, Session):
        verification = result.get("verification_result") or {}
        plan = result.get("query_understanding")
        public_status = _response_payload(result, trace_id)["status"]
        row = QueryTraceRow(
            trace_id=trace_id,
            question=request.question,
            intent=str(getattr(plan, "intent", "UNKNOWN")),
            query_date=None,
            vehicle_type=None,
            response_status=str(verification.get("status", "UNKNOWN")),
            citations=_citations(result, result.get("final_response") or {}),
            verification_summary={
                **_json_safe(verification),
                "public_status": public_status,
                "evidence_gaps": result.get("evidence_gaps", []),
            },
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
    plan = result.get("query_understanding")
    plan_status = str(getattr(plan, "status", "")) if plan is not None else ""
    citations = _citations(result, final)
    if verification.get("status") == "VALID" and citations:
        status = "VERIFIED"
    else:
        public_status = result.get("status") or verification.get("public_status")
        if public_status == "WORKFLOW_UNAVAILABLE":
            public_status = "INSUFFICIENT_EVIDENCE"
        if public_status:
            status = str(public_status)
        elif plan_status in {"GREETING", "OUT_OF_SCOPE", "CORPUS_NOT_COVERED"}:
            status = plan_status
        else:
            status = "INSUFFICIENT_EVIDENCE"
    reason = verification.get("reason_code") or getattr(plan, "status_reason", None)
    is_operational_error = status == "WORKFLOW_UNAVAILABLE"
    payload: dict[str, Any] = {
        "status": status,
        "answer": final.get("answer_summary") if status == "VERIFIED" else None,
        "claims": final.get("claims", []) if status == "VERIFIED" else [],
        "citations": citations if status == "VERIFIED" else [],
        "metadata": {"error_code": result.get("error_code")} if is_operational_error else {},
        "abstention": None
        if status in {"VERIFIED", "WORKFLOW_UNAVAILABLE"}
        else {"reason_code": reason or status, "evidence_gaps": result.get("evidence_gaps", [])},
        "disclaimer": DISCLAIMER,
        "trace_id": trace_id,
    }
    return payload


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
            for _node, update in event.items():
                result.update(update if isinstance(update, dict) else {})
        trace.add_span(
            "workflow_result",
            output={"status": (result.get("verification_result") or {}).get("status")},
        )
        verification = result.get("verification_result") or {}
        plan = result.get("query_understanding")
        plan_status = str(getattr(plan, "status", ""))
        plan_intent = str(getattr(plan, "intent", ""))
        if plan_status == "OUT_OF_SCOPE" or plan_intent == "OUT_OF_SCOPE":
            verification["public_status"] = "OUT_OF_SCOPE"
            verification["reason_code"] = "OUT_OF_SCOPE"
            result["status"] = "OUT_OF_SCOPE"
        elif verification.get("status") != "VALID":
            verification["public_status"] = "INSUFFICIENT_EVIDENCE"
            result["status"] = "INSUFFICIENT_EVIDENCE"
    except (RuntimeError, ValueError) as exc:
        logger.exception("workflow execution failed", extra={"trace_id": trace_id})
        result = {
            "status": "WORKFLOW_UNAVAILABLE",
            "error_code": "WORKFLOW_UNAVAILABLE",
            "error": str(exc),
            "verification_result": {
                "status": "ERROR",
                "public_status": "INSUFFICIENT_EVIDENCE",
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


@router.get("/chat/events", response_model=None)
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


_TRUSTED_SOURCE_HOST = "datafiles.chinhphu.vn"


def _trusted_source_url(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname == _TRUSTED_SOURCE_HOST


def _citation_field(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _citation_items(value: Any) -> list[Any]:
    if isinstance(value, dict):
        if {"before", "after"} <= value.keys():
            return _citation_items(value["before"]) + _citation_items(value["after"])
        if "results" in value:
            return _citation_items(value["results"])
        return [item for grouped in value.values() for item in _citation_items(grouped)]
    if value is None or isinstance(value, (str, bytes)):
        return []
    results = _citation_field(value, "results")
    if results is not None:
        return _citation_items(results)
    if isinstance(value, (list, tuple, set, frozenset)):
        return [item for item in value for item in _citation_items(item)]
    return [value]


def _citations(result: dict[str, Any], final: dict[str, Any]) -> list[dict[str, Any]]:
    context = result.get("context_package")
    if context is None:
        context = result.get("expanded_context", [])
    context = _citation_items(context)
    records = {
        _citation_field(item, "provision_id"): item
        for item in context
        if _citation_field(item, "provision_id")
        and _citation_field(item, "review_status", "ACCEPTED") == "ACCEPTED"
        and _trusted_source_url(_citation_field(item, "source_url"))
    }
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    claims = final.get("claims", [])
    if not isinstance(claims, list):
        return []
    for claim in claims:
        if not isinstance(claim, dict):
            model_dump = getattr(claim, "model_dump", None)
            claim = model_dump() if callable(model_dump) else None
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
            item = records.get(provision_id)
            if item is None or provision_id in seen:
                return []
            seen.add(provision_id)
            citation = {
                "provision_id": _citation_field(item, "provision_id"),
                "document_id": _citation_field(item, "document_id"),
                "document_number": _citation_field(item, "document_number"),
                "article": _citation_field(item, "article"),
                "clause": _citation_field(item, "clause"),
                "point": _citation_field(item, "point"),
                "parent_context": _citation_field(item, "parent_context"),
                "source_text": _citation_field(item, "source_text"),
                "page_number": _citation_field(item, "page_number"),
                "legal_context": _citation_field(item, "parent_context"),
                "bbox": _normalized_bbox(_citation_field(item, "bbox")),
                "source_url": _citation_field(item, "source_url"),
                "snapshot_at": _citation_field(item, "snapshot_at"),
                "content_hash": _citation_field(item, "content_hash"),
                "provision_version": _citation_field(item, "provision_version"),
            }
            for identity_field in (
                "provision_version",
                "document_version_id",
                "effective_from",
                "effective_to",
                "source_id",
            ):
                identity_value = _citation_field(item, identity_field)
                if identity_value is not None:
                    if hasattr(identity_value, "isoformat"):
                        identity_value = identity_value.isoformat()
                    citation[identity_field] = identity_value
            citations.append(citation)
    return (
        citations if len(citations) == sum(len(c.get("provision_ids", [])) for c in claims) else []
    )


__all__ = ["ChatRequest", "DISCLAIMER", "router"]
