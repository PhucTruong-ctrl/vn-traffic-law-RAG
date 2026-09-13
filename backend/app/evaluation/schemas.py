"""Strict, provider-independent schemas for deterministic RAG evaluation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Coordinate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: str = Field(min_length=1)
    article: str | None = None
    clause: str | None = None
    point: str | None = None


class ExpectedCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    query: str = Field(min_length=1)
    expected_coordinates: list[Coordinate] = Field(default_factory=list)
    retrieval_required: bool = True
    abstention_expected: bool = False


class CitationPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinate: Coordinate
    valid: bool = True


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    retrieved_coordinates: list[Coordinate] = Field(default_factory=list)
    citations: list[CitationPrediction] = Field(default_factory=list)
    answer: str = ""
    abstained: bool = False
    latency_ms: float = Field(ge=0)
    manual_answer_correctness: bool | None = None


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    retrieval_hit_at_k: bool | None = None
    document_accuracy: float | None = None
    article_accuracy: float | None = None
    clause_accuracy: float | None = None
    point_accuracy: float | None = None
    citation_validity: bool | None = None
    answer_correctness_manual: bool | None = None
    abstention_accuracy: bool
    latency_ms: float


class LatencySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    mean_ms: float | None = Field(default=None, ge=0)
    p50_ms: float | None = Field(default=None, ge=0)
    p95_ms: float | None = Field(default=None, ge=0)


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_count: int = Field(ge=0)
    case_results: list[CaseResult]
    retrieval_hit_at_k: float | None = None
    document_accuracy: float | None = None
    article_accuracy: float | None = None
    clause_accuracy: float | None = None
    point_accuracy: float | None = None
    citation_validity: float | None = None
    answer_correctness_manual: float | None = None
    abstention_accuracy: float | None = None
    latency: LatencySummary


__all__ = [
    "CaseResult",
    "CitationPrediction",
    "Coordinate",
    "EvaluationSummary",
    "ExpectedCase",
    "LatencySummary",
    "Prediction",
]
