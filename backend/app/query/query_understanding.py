"""Deterministic Vietnamese legal query planning."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any, Protocol, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, PrivateAttr

from app.ingestion.terminology import TERMINOLOGY, TERMINOLOGY_VERSION, canonical_term

from .date_policy import MISSING_QUERY_DATE, resolve_query_date
from .evidence_plan import required_evidence_for
from .query_understanding_types import EvidenceType, QueryIntent


class _GenaiModels(Protocol):
    def generate_content(self, **kwargs: Any) -> Any: ...


class _GenaiClient(Protocol):
    models: _GenaiModels


class _FallbackObject(Protocol):
    def analyze(self, question: str, *, current_date: date) -> QueryPlan: ...


FallbackAnalyzer: TypeAlias = Callable[..., "QueryPlan"] | _FallbackObject


def _safe_fallback_plan(question: str) -> QueryPlan:
    return QueryPlan(
        intent=QueryIntent.OUT_OF_SCOPE,
        effective_date=None,
        comparison_from=None,
        comparison_to=None,
        vehicle_type=None,
        document_number=None,
        article=None,
        clause=None,
        point=None,
        legal_entities=[],
        normalized_query=_normalize(question),
        required_evidence=[],
        missing_query_information=["query_analysis"],
    )


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    intent: QueryIntent
    effective_date: date | None
    comparison_from: date | None
    comparison_to: date | None
    vehicle_type: str | None
    document_number: str | None
    article: str | None
    clause: str | None
    point: str | None
    legal_entities: list[str]
    normalized_query: str
    required_evidence: list[EvidenceType]
    _original_query: str | None = PrivateAttr(default=None)

    @property
    def original_query(self) -> str | None:
        return (
            self._original_query
            or self.__dict__.get("original_query")
            or (self.model_extra or {}).get("original_query")
        )

    missing_query_information: list[str]


class QueryPlanFallback:
    """Structured Gemini fallback for questions deterministic parsing cannot resolve."""

    def __init__(
        self,
        client: _GenaiClient | None = None,
        *,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._model = model

    def analyze(self, question: str, *, current_date: date) -> QueryPlan:
        try:
            client = self._client
            model = self._model
            if client is None or model is None:
                from app.config import get_generation_settings

                settings = get_generation_settings()
                model = model or settings.model
                if client is None:
                    from google import genai

                    client = cast(_GenaiClient, genai.Client(api_key=settings.gemini_api_key))
            from google.genai import types

            assert client is not None

            response = client.models.generate_content(
                model=model,
                contents=(
                    "Analyze this Vietnamese legal question and return only a QueryPlan "
                    f"JSON object. Current date: {current_date.isoformat()}. "
                    f"Question: {question}"
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QueryPlan,
                    temperature=0.2,
                ),
            )
            parsed = getattr(response, "parsed", None)
            if parsed is None:
                parsed = getattr(response, "text", None)
            if parsed is None:
                raise ValueError("Gemini returned no structured query plan")
            return QueryPlan.model_validate(parsed)
        except Exception:
            return _safe_fallback_plan(question)


def _explicit_date_matches(text: str) -> list[tuple[int, int, str]]:
    patterns = (
        r"\bngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}\b",
        r"(?<!\d)\d{1,2}/\d{1,2}/\d{4}(?!\d)",
        r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)",
    )
    return [
        (match.start(), match.end(), match.group())
        for pattern in patterns
        for match in re.finditer(pattern, text, re.I)
    ]


def _date_signals(text: str, current_date: date) -> list[date]:
    matches = _explicit_date_matches(text)
    years = [
        (match.start(), match.end(), match.group())
        for match in re.finditer(r"(?<!\d)(\d{4})(?!\d)", text)
        if not any(start <= match.start() < end for start, end, _ in matches)
        and not _is_document_year(text, match)
    ]
    matches.extend(years)
    values: list[date] = []
    for _, _, signal in sorted(matches):
        parsed = resolve_query_date(signal, current_date=current_date)
        if parsed.parsed_date is not None and not parsed.should_abstain:
            values.append(parsed.parsed_date)
    return list(dict.fromkeys(values))


def _date_signal_texts(text: str) -> list[str]:
    """Return explicit date tokens, including malformed tokens."""
    matches = _explicit_date_matches(text)
    matches.extend(
        (match.start(), match.end(), match.group())
        for match in re.finditer(r"(?<!\d)(\d{4})(?!\d)", text)
        if not any(start <= match.start() < end for start, end, _ in matches)
        and not _is_document_year(text, match)
    )
    return list(dict.fromkeys(signal for _, _, signal in matches))


def _is_document_year(text: str, match: re.Match[str]) -> bool:
    start = match.start()
    window = text[max(0, start - 5) : start + 9]
    return bool(re.search(r"\d{1,4}/" + match.group() + r"/", window, re.I))


def _normalize(text: str) -> str:
    normalized = text
    for canonical, variants in sorted(TERMINOLOGY.items(), key=lambda pair: -len(pair[0])):
        for variant in sorted(variants, key=len, reverse=True):
            normalized = re.sub(
                rf"(?<!\w){re.escape(variant)}(?!\w)",
                canonical,
                normalized,
                flags=re.I,
            )
    return " ".join(normalized.split())


class QueryAnalyzer:
    """Build a QueryPlan without database, vector-store, or model dependencies."""

    def __init__(self, fallback_analyzer: FallbackAnalyzer | None = None) -> None:
        self.fallback_analyzer = fallback_analyzer

    def analyze(
        self,
        question: str,
        *,
        current_date: date,
        effect_change_dates: Iterable[date] = (),
    ) -> QueryPlan:
        text = question.strip()
        lowered = text.casefold()
        document = re.search(
            r"(?<![\w/])(\d{1,4}/\d{4}/(?:nđ|nd|tt|qđ|qdhđ|qcvn|qh)\-?[a-z0-9-]*)(?![\w/])",
            text,
            re.I,
        )
        hierarchy = re.search(r"\bđiều\s*([\w.-]+)", lowered)
        clause = re.search(r"\bkhoản\s*([\w.-]+)", lowered)
        point = re.search(r"\bđiểm\s*([a-zđ])\b", lowered)
        vehicle = next(
            (
                term
                for term in ("xe máy", "xe mô tô", "xe gắn máy", "ô tô", "xe tải", "xe đạp")
                if term in lowered
            ),
            None,
        )
        entities = [
            canonical
            for canonical, variants in TERMINOLOGY.items()
            if any(
                re.search(rf"(?<!\w){re.escape(variant)}(?!\w)", text, re.I) for variant in variants
            )
        ]
        if vehicle:
            canonical_vehicle = canonical_term(vehicle, TERMINOLOGY_VERSION)
            if canonical_vehicle not in entities:
                entities.insert(0, canonical_vehicle)
        dates = _date_signals(text, current_date)
        date_tokens = _date_signal_texts(text)
        comparison = (
            bool(re.search(r"trước\s*(?:và|,)?\s*sau|so sánh|khác nhau|đối chiếu", lowered))
            or len(dates) >= 2
        )
        out_of_scope = bool(
            re.search(
                r"ngoài\s*(?:việt nam|giao thông đường bộ)|tư vấn cá nhân|"
                r"kết luận tai nạn|luật mỹ|luật hoa kỳ",
                lowered,
            )
        )
        date_result = resolve_query_date(
            text, current_date=current_date, effect_change_dates=effect_change_dates
        )
        missing: list[str] = []
        if date_result.should_abstain or any(
            (
                parsed := resolve_query_date(
                    token,
                    current_date=current_date,
                    effect_change_dates=effect_change_dates,
                )
            ).should_abstain
            or parsed.parsed_date is None
            for token in date_tokens
        ):
            missing.append("query_date")
        if out_of_scope:
            intent, effective, comparison_from, comparison_to = (
                QueryIntent.OUT_OF_SCOPE,
                None,
                None,
                None,
            )
        elif comparison:
            intent = QueryIntent.COMPARISON
            comparison_dates = dates[:2]
            comparison_from = comparison_dates[0] if comparison_dates else None
            comparison_to = comparison_dates[1] if len(comparison_dates) > 1 else None
            if comparison_from is None or comparison_to is None:
                missing.append("comparison_dates")
            effective = None
        elif document or hierarchy or clause or point:
            intent, effective, comparison_from, comparison_to = (
                QueryIntent.SOURCE_SEARCH,
                date_result.parsed_date,
                None,
                None,
            )
        elif date_result.parsed_date is not None and date_result.parsed_date < current_date:
            intent, effective, comparison_from, comparison_to = (
                QueryIntent.HISTORICAL,
                date_result.parsed_date,
                None,
                None,
            )
        else:
            intent, effective, comparison_from, comparison_to = (
                QueryIntent.CURRENT,
                date_result.parsed_date or current_date,
                None,
                None,
            )
        if "query_date" in missing and not comparison and not out_of_scope:
            intent, effective, comparison_from, comparison_to = (
                QueryIntent.OUT_OF_SCOPE,
                None,
                None,
                None,
            )
        if missing and intent is not QueryIntent.OUT_OF_SCOPE:
            effective = None
        if self.fallback_analyzer and not (
            document
            or hierarchy
            or clause
            or point
            or vehicle
            or dates
            or date_tokens
            or out_of_scope
        ):
            try:
                fallback = getattr(self.fallback_analyzer, "analyze", self.fallback_analyzer)
                if not callable(fallback):
                    raise TypeError("fallback analyzer must be callable or expose analyze")
                plan = QueryPlan.model_validate(fallback(text, current_date=current_date))
                plan._original_query = text
                return plan
            except Exception:
                return _safe_fallback_plan(text)
        plan = QueryPlan(
            intent=intent,
            effective_date=effective,
            comparison_from=comparison_from,
            comparison_to=comparison_to,
            vehicle_type=vehicle,
            document_number=document.group(1) if document else None,
            article=hierarchy.group(1) if hierarchy else None,
            clause=clause.group(1) if clause else None,
            point=point.group(1) if point else None,
            legal_entities=entities,
            normalized_query=_normalize(text),
            required_evidence=required_evidence_for(intent, text, entities),
            missing_query_information=missing,
        )
        plan._original_query = text
        if (
            date_result.reason_code == MISSING_QUERY_DATE
            and "query_date" not in plan.missing_query_information
        ):
            plan.missing_query_information.append("query_date")
        return plan


__all__ = [
    "EvidenceType",
    "QueryIntent",
    "QueryPlan",
    "QueryPlanFallback",
    "QueryAnalyzer",
    "TERMINOLOGY_VERSION",
]
