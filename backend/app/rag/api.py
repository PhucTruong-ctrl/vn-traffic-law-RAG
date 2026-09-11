"""Small rescue API with no session or database state."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from .retrieval import Retriever
from .service import RescueService

router = APIRouter(prefix="/api/v1", tags=["rescue"])
service = RescueService(
    Retriever(
        chunks_path=os.getenv("RESCUE_CHUNKS", "data/processed/markdown-chunks.jsonl"),
        index_path=os.getenv("RESCUE_INDEX_PATH", "data/processed/index"),
    )
)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    effective_date: date | None = None


@router.post("/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    return service.answer(
        request.question, top_k=request.top_k, effective_date=request.effective_date
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


__all__ = ["ChatRequest", "chat", "health", "router"]
