"""Strict request and response models for the RAG chat route."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=10_000)
    session_id: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    top_k: int = Field(default=5, ge=1, le=50)
    effective_date: date | None = None

    @field_validator("question", "title")
    @classmethod
    def non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("question and title must not be blank")
        return value


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: str = Field(min_length=1)
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    page: int = Field(default=1, ge=1)
    source_file: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    pdf_url: str | None = None


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    citation: Citation
    score: float | None = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    status: str | None = None
    debug: dict[str, Any] | None = None


__all__ = ["Citation", "ChatRequest", "ChatResponse", "RetrievedChunk"]
