"""Verified legal chat endpoint."""

from __future__ import annotations

import uuid
from contextlib import suppress
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.db import get_db
from app.observability.langfuse import emit_query_trace
from app.observability.query_trace import QueryTrace, QueryTraceStore
from app.workflow import build_query_graph as _production_build_query_graph
from app.workflow.graph import production_services

# Public test seam; production always receives the composed services.
build_query_graph = _production_build_query_graph


def _optional_db():
    try:
        yield from get_db()
    except Exception:
        yield None


router = APIRouter(prefix="/api/v1", tags=["chat"])
_TRACE_STORE = QueryTraceStore()
DISCLAIMER = "This response is informational and not legal advice."


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=10_000)
    query_date: date | None = None
    vehicle: str | None = Field(default=None, min_length=1, max_length=100)
    comparison: bool = False
    comparison_date: date | None = None

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
        "query_date": request.query_date or date.today(),
        "vehicle_type": request.vehicle,
        "comparison_date": request.comparison_date,
    }
    trace = QueryTrace(request.question, trace_id=trace_id, metadata={"vehicle": request.vehicle})
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
    _TRACE_STORE.save(trace)
    with suppress(Exception):
        emit_query_trace(trace)
    final = result.get("final_response") or {}
    verification = result.get("verification_result") or {}
    status = "VERIFIED" if verification.get("status") == "VALID" else "ABSTAINED"
    payload: dict[str, Any] = {
        "status": status,
        "answer": final.get("answer_summary") if status == "VERIFIED" else None,
        "claims": final.get("claims", []) if status == "VERIFIED" else [],
        "citations": _citations(result, final) if status == "VERIFIED" else [],
        "metadata": {
            "query_date": request.query_date.isoformat() if request.query_date else None,
            "vehicle": request.vehicle,
            "comparison": request.comparison,
            "comparison_date": request.comparison_date.isoformat()
            if request.comparison_date
            else None,
        },
        "abstention": None
        if status == "VERIFIED"
        else {"reason_code": verification.get("reason_code", "INSUFFICIENT_EVIDENCE")},
        "disclaimer": DISCLAIMER,
        "trace_id": trace_id,
    }
    return payload


def _citations(result: dict[str, Any], final: dict[str, Any]) -> list[dict[str, Any]]:
    context = result.get("expanded_context") or result.get("context_package") or []
    by_id = {
        getattr(item, "provision_id", None): item
        for item in (context if isinstance(context, (list, tuple)) else [])
        if getattr(item, "provision_id", None)
        and getattr(item, "review_status", "ACCEPTED") == "ACCEPTED"
    }
    citations: list[dict[str, Any]] = []
    for claim in final.get("claims", []):
        for provision_id in claim.get("provision_ids", []):
            item = by_id.get(provision_id)
            if item is None:
                continue
            citation = {"provision_id": provision_id}
            for field in (
                "document_id",
                "document_number",
                "article",
                "source_url",
                "source_text",
                "page_number",
                "bbox",
            ):
                value = getattr(item, field, None)
                if value is not None:
                    citation[field] = value
            citations.append(citation)
    return citations


__all__ = ["ChatRequest", "DISCLAIMER", "router"]
