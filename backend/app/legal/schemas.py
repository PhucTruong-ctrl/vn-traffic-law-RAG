"""Strict API models for deterministic legal corpus exploration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LegalSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file: str = Field(min_length=1)
    source_url: str | None = None
    pdf_url: str | None = None
    source_kind: Literal["markdown", "pdf"]
    source_type: str = Field(min_length=1)
    retrieved_at: str | None = None


class LegalDocumentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    document_name: str = Field(min_length=1)
    source: LegalSource
    provision_count: int = Field(ge=0)
    content: str | None = None


class LegalProvision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document_name: str = Field(min_length=1)
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    text: str = Field(min_length=1)
    source: LegalSource


class LegalSearchResult(LegalProvision):
    score: int = Field(ge=0)


class LegalSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    results: list[LegalSearchResult]


__all__ = [
    "LegalDocumentSummary",
    "LegalProvision",
    "LegalSearchResponse",
    "LegalSearchResult",
    "LegalSource",
]
