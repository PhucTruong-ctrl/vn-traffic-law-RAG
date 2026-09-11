"""Minimal request and response models for the rescue chat path."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ChatRequest(_StrictModel):
    """Request accepted by ``POST /api/v1/chat``."""

    question: str = Field(min_length=1, max_length=10_000)

    @field_validator("question")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class Citation(_StrictModel):
    """Source citation attached to a generated answer."""

    document: str = Field(min_length=1)
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    page: int = Field(ge=1)
    source_file: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    pdf_url: str | None = None

    @field_validator("document", "source_file", "excerpt")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("citation text fields must not be blank")
        return value


class RetrievedChunk(_StrictModel):
    """A retrieved text chunk used as evidence for a response."""

    text: str = Field(min_length=1)
    citation: Citation
    score: float | None = None

    @field_validator("text")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value


class ChatResponse(_StrictModel):
    """Minimal response returned by the rescue chat endpoint."""

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    status: str | None = None
    debug: dict[str, object] | None = None

    @field_validator("answer")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("answer must not be blank")
        return value


__all__ = ["Citation", "ChatRequest", "ChatResponse", "RetrievedChunk"]
