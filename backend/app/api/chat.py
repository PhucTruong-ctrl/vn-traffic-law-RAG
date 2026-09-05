"""Verified legal chat endpoint."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.workflow import build_query_graph

router = APIRouter(prefix="/api/v1", tags=["chat"])

DISCLAIMER = "This response is informational and not legal advice."


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=10_000)
    query_date: date | None = None
    vehicle: str | None = Field(default=None, min_length=1, max_length=100)
    comparison: bool = False

    @field_validator("question")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


@router.post("/chat", response_model=None)
async def chat(request: Annotated[ChatRequest, Body()]) -> dict[str, Any]:
    """Run the controlled LangGraph workflow and return its verified result."""
    trace_id = uuid.uuid4().hex
    state: dict[str, Any] = {
        "question": request.question,
        "query_date": request.query_date or date.today(),
        "vehicle_type": request.vehicle,
    }
    result = await build_query_graph().ainvoke(state)
    final = result.get("final_response") or {}
    verification = result.get("verification_result") or {}
    status = "VERIFIED" if verification.get("status") == "VALID" else "ABSTAINED"
    payload: dict[str, Any] = {
        "status": status,
        "answer": final.get("answer_summary") if status == "VERIFIED" else None,
        "claims": final.get("claims", []) if status == "VERIFIED" else [],
        "citations": _citations(result, final),
        "metadata": {
            "query_date": request.query_date.isoformat() if request.query_date else None,
            "vehicle": request.vehicle,
            "comparison": request.comparison,
        },
        "abstention": None
        if status == "VERIFIED"
        else {"reason_code": verification.get("reason_code", "INSUFFICIENT_EVIDENCE")},
        "disclaimer": DISCLAIMER,
        "trace_id": trace_id,
    }
    return payload


def _citations(result: dict[str, Any], final: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose citation metadata from verified claims and retrieved context."""
    context = result.get("expanded_context") or result.get("context_package") or []
    by_id = {getattr(item, "provision_id", None): item for item in context if getattr(item, "provision_id", None)}
    citations: list[dict[str, Any]] = []
    for claim in final.get("claims", []):
        for provision_id in claim.get("provision_ids", []):
            item = by_id.get(provision_id)
            citation = {"provision_id": provision_id}
            if item is not None:
                for field in ("document_id", "document_number", "article", "source_url"):
                    value = getattr(item, field, None)
                    if value is not None:
                        citation[field] = value
            citations.append(citation)
    return citations


__all__ = ["ChatRequest", "DISCLAIMER", "router"]
