"""HTTP interface for the hybrid RAG chat module."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from .schemas import ChatRequest, ChatResponse
from .service import RAGService

router = APIRouter(prefix="/api/v1", tags=["rag"])
service = RAGService()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> dict[str, Any]:
    try:
        return service.answer(
            request.question,
            top_k=request.top_k,
            effective_date=request.effective_date,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


__all__ = ["ChatRequest", "chat", "health", "router"]
