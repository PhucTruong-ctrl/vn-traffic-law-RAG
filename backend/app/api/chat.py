"""Verified legal chat endpoint."""

from __future__ import annotations

import uuid
from contextlib import suppress
from dataclasses import asdict, is_dataclass
from datetime import date
from enum import Enum
from typing import Annotated, Any, cast

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.db import get_db
from app.observability.langfuse import emit_query_trace
from app.observability.query_trace import QueryTrace, QueryTraceStore
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
    """Chat-only request contract: the question is the sole client input."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=10_000)

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
    db: Annotated[Any, Depends(_optional_db)],
) -> dict[str, Any]:
    trace_id = http_request.headers.get("X-Trace-ID") or uuid.uuid4().hex
    state: dict[str, Any] = {
        "question": request.question,
        "query_date": date.today(),
    }
    trace = QueryTrace(request.question, trace_id=trace_id, metadata={})
    try:
        if db is None and build_query_graph is _production_build_query_graph:
            raise RuntimeError("workflow database session is not configured")
        services = production_services(session=db) if db is not None else None
        graph = build_query_graph(services)
        trace.add_span("workflow", input=state)
        result = await graph.ainvoke(state)
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
        db.commit()
    with suppress(Exception):
        emit_query_trace(trace)
    final = result.get("final_response") or {}
    verification = result.get("verification_result") or {}
    citations = _citations(result, final)
    status = (
        "VERIFIED"
        if verification.get("status") == "VALID" and citations
        else "ABSTAINED"
    )
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
            citations.append(
                {
                    "provision_id": item.provision_id,
                    "document_id": item.document_id,
                    "document_number": item.document_number,
                    "article": item.article,
                    "source_url": getattr(item, "source_url", None),
                    "source_text": item.source_text,
                    "page_number": item.page_number,
                    "bbox": getattr(item, "bbox", None),
                }
            )
    return (
        citations
        if len(citations) == sum(len(c.get("provision_ids", [])) for c in claims)
        else []
    )


__all__ = ["ChatRequest", "DISCLAIMER", "router"]
