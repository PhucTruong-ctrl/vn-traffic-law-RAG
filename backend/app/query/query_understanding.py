"""Deterministic Vietnamese legal query planning."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any, Protocol, TypeAlias
from urllib import request

from pydantic import BaseModel, ConfigDict, PrivateAttr

from app.ingestion.terminology import TERMINOLOGY, TERMINOLOGY_VERSION, canonical_term

from .date_policy import MISSING_QUERY_DATE, resolve_query_date
from .evidence_plan import required_evidence_for
from .query_understanding_types import EvidenceType, QueryIntent


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


class CaseSpec(BaseModel):
    """One independently answerable decomposition of a legal query."""

    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str
    query_text: str
    vehicle_type: str | None = None
    actor: str | None = None
    requested_evidence: list[EvidenceType] = []
    ambiguity: list[str] = []
    missing_information: list[str] = []


class ProvisionReference(BaseModel):
    """Canonical provision reference extracted from a legal question."""

    model_config = ConfigDict(extra="forbid", strict=True)

    document_number: str
    article: str | None = None
    clause: str | None = None
    point: str | None = None


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
    references: list[ProvisionReference] = []
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
    case_queries: list[str] = []
    cases: list[CaseSpec] = []
    status: str = "LEGAL"
    status_reason: str | None = None
    evidence_gaps: list[str] = []


class QueryPlanFallback:
    """Structured OpenRouter fallback for questions deterministic parsing cannot resolve."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        model: str | None = None,
        timeout: float = 60.0,
        opener: Any = request.urlopen,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout = timeout
        self._opener = opener

    def analyze(self, question: str, *, current_date: date) -> QueryPlan:
        try:
            from app.config import get_generation_settings

            settings = get_generation_settings()
            model = self._model or settings.model
            if not model or not settings.openrouter_api_key:
                raise ValueError("OpenRouter configuration is incomplete")
            prompt = (
                "Analyze this Vietnamese legal question and return only a QueryPlan JSON object. "
                f"Current date: {current_date.isoformat()}. Question: {question}"
            )
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "query_plan",
                        "strict": True,
                        "schema": QueryPlan.model_json_schema(),
                    },
                },
            }
            if self._client is not None:
                response = self._client(
                    payload,
                    api_key=settings.openrouter_api_key,
                    base_url=settings.openrouter_base_url,
                    timeout=self._timeout,
                )
            else:
                req = request.Request(
                    f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {settings.openrouter_api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with self._opener(req, timeout=self._timeout) as response:
                    response = json.loads(response.read())
            if isinstance(response, dict):
                content = response["choices"][0]["message"]["content"]
            else:
                content = getattr(response, "content", None)
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            if isinstance(content, str):
                content = content.strip()
                if content.startswith("```"):
                    content = content.strip("`")
                    if content.startswith("json"):
                        content = content[4:].lstrip()
                content = json.loads(content)
            return QueryPlan.model_validate(content)
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


def _build_cases(
    text: str,
    normalized: str,
    vehicle: str | None,
    evidence: list[EvidenceType],
    missing: list[str],
) -> tuple[list[str], list[CaseSpec]]:
    vehicles = [
        v
        for v in ("xe máy", "ô tô", "xe mô tô", "xe gắn máy", "xe tải", "xe đạp")
        if re.search(rf"(?<!\w){re.escape(v)}(?!\w)", text, re.I)
    ]
    if "xe máy" in vehicles and "xe mô tô" in vehicles:
        vehicles.remove("xe mô tô")
    vehicles = list(dict.fromkeys(vehicles))
    actors = re.findall(r"\b(người (?:lái|điều khiển)|chủ xe)\b", text.casefold())
    count = min(max(len(vehicles), 1), 2)
    violations = [
        part.strip() for part in re.split(r"\s+(?:và|hoặc)\s+", text, flags=re.I) if part.strip()
    ]
    if len(violations) > 1:
        count = min(len(violations), 2)
    cases = []
    for i in range(count):
        v = vehicles[i] if i < len(vehicles) else vehicle
        query = (
            violations[i]
            if len(violations) > 1
            else (normalized if count == 1 else f"{v} {normalized}")
        )
        ambiguity = (
            ["negation_or_uncertainty"]
            if re.search(r"không rõ|chưa rõ|có bị|không biết", text, re.I)
            else []
        )
        cases.append(
            CaseSpec(
                case_id=f"case-{i + 1}",
                query_text=query,
                vehicle_type=v,
                actor=actors[0] if actors else None,
                requested_evidence=list(evidence),
                ambiguity=ambiguity,
                missing_information=list(missing),
            )
        )
    return [c.query_text for c in cases], cases


def _default_corpus_document_ids() -> frozenset[str]:
    """Return approved identifiers from committed corpus manifests."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "data" / "manifests"
    ids: set[str] = set()
    for path in root.rglob("*.manifest.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("review_status") == "ACCEPTED" and isinstance(
            payload.get("document_id"), str
        ):
            ids.add(payload["document_id"].casefold())
    return frozenset(ids)


def _document_id_for_number(number: str, approved: frozenset[str]) -> str | None:
    match = re.fullmatch(
        r"\s*(\d{1,4})\s*/\s*(\d{4})\s*/\s*([a-zđ]+)(?:\s*-\s*([a-z0-9]+))?\s*",
        number,
        re.I,
    )
    if match is None:
        return None
    serial, year, prefix, suffix = match.groups()
    prefix = prefix.casefold().replace("đ", "d")
    suffix = suffix.casefold().replace("đ", "d") if suffix else None
    if prefix == "nd" and suffix == "cp":
        base = f"nd-{serial}-{year}"
    elif prefix == "tt":
        base = f"tt-{serial}-{year}"
    else:
        return None
    return base if base in approved else None


class QueryAnalyzer:
    """Build a QueryPlan without database, vector-store, or model dependencies."""

    def __init__(
        self,
        fallback_analyzer: FallbackAnalyzer | None = None,
        *,
        approved_document_ids: Iterable[str] | None = None,
    ) -> None:
        self.fallback_analyzer = fallback_analyzer
        self.approved_document_ids = frozenset(
            value.casefold() for value in (approved_document_ids or _default_corpus_document_ids())
        )

    def analyze(
        self,
        question: str,
        *,
        current_date: date,
        effect_change_dates: Iterable[date] = (),
    ) -> QueryPlan:
        text = question.strip()
        lowered = text.casefold()
        hierarchy = re.search(r"\bđiều\s*([\w.-]+)", lowered)
        clause = re.search(r"\bkhoản\s*([\w.-]+)", lowered)
        point = re.search(r"\bđiểm\s*([a-zđ])\b", lowered)
        document = re.search(
            r"(?<![\w/])(\d{1,4}/\d{4}/(?:nđ|nd|tt|qđ|qdhđ|qcvn|qh)\-?[a-z0-9-]*)(?![\w/])",
            text,
            re.I,
        )
        greeting = bool(
            re.fullmatch(
                r"(?:xin\s+chào|chào|hello|hi|hey|alo|good\s+(?:morning|afternoon|evening))(?:\s+\w+)?[!.?]*",
                lowered,
            )
        )
        if greeting:
            plan = _safe_fallback_plan(text)
            plan.status = "GREETING"
            plan.status_reason = "GREETING"
            plan.missing_query_information = []
            plan._original_query = text
            return plan
        vehicle = next(
            (
                canonical
                for canonical, variants in TERMINOLOGY.items()
                if any(
                    re.search(rf"(?<!\w){re.escape(variant)}(?!\w)", text, re.I)
                    for variant in variants
                )
                and canonical.startswith("xe ")
            ),
            next(
                (
                    term
                    for term in ("xe máy", "xe mô tô", "xe gắn máy", "ô tô", "xe tải", "xe đạp")
                    if term in lowered
                ),
                None,
            ),
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
                r"ngoài\s*(?:việt nam|giao thông đường bộ)|"
                r"ngoài\s+(?:14\s+)?văn bản(?:\s+đang)?\s+phục vụ|"
                r"nguồn\s+ngoài\s+(?:14\s+)?văn bản|"
                r"tư vấn cá nhân|kết luận tai nạn|luật mỹ|luật hoa kỳ",
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
        covered_document = (
            _document_id_for_number(document.group(1), self.approved_document_ids)
            if document
            else None
        )
        corpus_not_covered = bool(document and covered_document is None)
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
        if (
            "query_date" in missing
            and not comparison
            and not out_of_scope
            and not corpus_not_covered
        ):
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
            or corpus_not_covered
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
        status = (
            "OUT_OF_SCOPE"
            if out_of_scope
            else ("CORPUS_NOT_COVERED" if corpus_not_covered else "LEGAL")
        )
        status_reason = status if status != "LEGAL" else None
        references: list[ProvisionReference] = []
        canonical_pattern = re.compile(
            r"(?P<document>[a-z]+-\d{1,4}-\d{4})"
            r"(?:__dieu-(?P<article>\d+))?"
            r"(?:__khoan-(?P<clause>\d+))?"
            r"(?:__diem-(?P<point>[a-zđ]))?",
            re.I,
        )
        for match in canonical_pattern.finditer(lowered):
            references.append(
                ProvisionReference(
                    document_number=match.group("document"),
                    article=match.group("article"),
                    clause=match.group("clause"),
                    point=match.group("point"),
                )
            )
        human_pattern = re.compile(
            r"(?:điều\s+(?P<human_article>\d+)\s+)"
            r"(?:nghị\s+định\s+)?"
            r"(?P<document>\d{1,4}/\d{4}/[a-zđ]+(?:-[a-z0-9]+)?)"
            r"(?:\s+khoản\s+(?P<human_clause>\d+))?"
            r"(?:\s+điểm\s+(?P<human_point>[a-zđ]))?",
            re.I,
        )
        for match in human_pattern.finditer(lowered):
            document_number = match.group("document")
            prefix, suffix = document_number.rsplit("/", 1)
            document_number = f"{prefix}/{suffix.upper()}"
            references.append(
                ProvisionReference(
                    document_number=document_number,
                    article=match.group("human_article"),
                    clause=match.group("human_clause"),
                    point=match.group("human_point"),
                )
            )
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
            references=references,
            legal_entities=entities,
            normalized_query=_normalize(text),
            required_evidence=required_evidence_for(intent, text, entities),
            missing_query_information=missing,
            case_queries=[],
            cases=[],
            status=status,
            status_reason=status_reason,
        )
        if (
            date_result.reason_code == MISSING_QUERY_DATE
            and "query_date" not in plan.missing_query_information
        ):
            plan.missing_query_information.append("query_date")
        if intent is not QueryIntent.COMPARISON:
            plan.case_queries, plan.cases = _build_cases(
                text,
                plan.normalized_query,
                vehicle,
                plan.required_evidence,
                plan.missing_query_information,
            )
        plan._original_query = text
        return plan


__all__ = [
    "EvidenceType",
    "QueryIntent",
    "CaseSpec",
    "QueryPlan",
    "QueryPlanFallback",
    "QueryAnalyzer",
    "TERMINOLOGY_VERSION",
]
