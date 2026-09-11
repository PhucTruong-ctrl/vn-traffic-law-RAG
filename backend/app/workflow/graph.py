"""Controlled LangGraph skeleton for the legal retrieval workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, cast
from urllib.parse import urlparse

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select

from app.config import get_embedding_settings, get_retrieval_settings, get_settings
from app.generation import (
    OpenRouterStructuredGenerator,
    StructuredAnswer,
    StructuredGenerationError,
)
from app.generation.context_builder import build_context
from app.ingestion.actors.index import load_or_fit_sparse_encoder
from app.persistence.models import LegalProvision
from app.persistence.repositories.provisions import ProvisionRepository
from app.persistence.repositories.relations import RelationRepository
from app.persistence.repositories.temporal import TemporalRepository
from app.query.evidence_gate import (
    EvidenceCompletenessGate,
    EvidenceStatus,
    targeted_query_for_gap,
)
from app.query.expansion import QueryExpander
from app.query.query_understanding import QueryAnalyzer
from app.query.temporal_verifier import verify_temporal
from app.retrieval.comparison import ComparisonResult
from app.retrieval.context_expansion import LegalContextExpander
from app.retrieval.contracts import CandidateSet, RetrievalResult
from app.retrieval.embedding import get_embedding_provider
from app.retrieval.filters import build_temporal_filter, deduplicate_results
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.qdrant_store import _default_client
from app.retrieval.sparse import BM25SparseEncoder
from app.verification.workflow import LegalVerificationBoundary

from .repair import MAX_REPAIR_ATTEMPTS, repair_route
from .state import QueryState

Service = Any


def _items(value: Any) -> list[Any]:
    if isinstance(value, CandidateSet):
        return list(value.results)
    if isinstance(value, ComparisonResult):
        return list(value.before.results) + list(value.after.results)
    if isinstance(value, dict):
        if {"before", "after"} <= value.keys():
            return _items(value["before"]) + _items(value["after"])
        return [item for grouped in value.values() for item in _items(grouped)]
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    return list(value)


def _merge_results(existing: Any, additions: Any) -> Any:
    merged = _items(existing) + _items(additions)
    if merged and all(isinstance(item, RetrievalResult) for item in merged):
        merged = deduplicate_results(merged)
    if isinstance(existing, CandidateSet):
        return existing.model_copy(update={"results": merged})
    if isinstance(additions, CandidateSet):
        return additions.model_copy(update={"results": merged})
    return merged


def _fuse_variant_results(
    variant_results: list[tuple[str, Any]],
    *,
    final_top_k: int,
    exact_ids: set[str] = set(),
) -> list[RetrievalResult]:
    """Fuse complete per-variant ranked lists with deterministic RRF."""
    by_id: dict[str, RetrievalResult] = {}
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    for variant_index, (_, value) in enumerate(variant_results):
        for rank, result in enumerate(_items(value), start=1):
            if not isinstance(result, RetrievalResult):
                continue
            provision_id = result.provision_id
            first_seen.setdefault(provision_id, variant_index)
            by_id.setdefault(provision_id, result)
            scores[provision_id] = scores.get(provision_id, 0.0) + 1.0 / (60 + rank)
            current = by_id[provision_id]
            if result.parent_context and not current.parent_context:
                current = current.model_copy(update={"parent_context": result.parent_context})
            sources = list(dict.fromkeys([*current.retrieval_sources, *result.retrieval_sources]))
            by_id[provision_id] = current.model_copy(
                update={"retrieval_sources": sources, "fused_score": scores[provision_id]}
            )
    ordered = sorted(
        by_id,
        key=lambda provision_id: (
            provision_id not in exact_ids,
            -scores[provision_id],
            first_seen[provision_id],
            provision_id,
        ),
    )
    return [
        by_id[provision_id].model_copy(update={"rank": rank})
        for rank, provision_id in enumerate(ordered[:final_top_k], start=1)
    ]


_TRUSTED_SOURCE_HOST = "datafiles.chinhphu.vn"


def _trusted_source_url(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname == _TRUSTED_SOURCE_HOST


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _trusted_context(value: Any) -> Any:
    """Keep only accepted records backed by the official source host."""
    if isinstance(value, CandidateSet):
        return value.model_copy(
            update={
                "results": [item for item in value.results if _trusted_source_url(item.source_url)]
            }
        )
    if isinstance(value, ComparisonResult):
        return ComparisonResult(
            before=_trusted_context(value.before), after=_trusted_context(value.after)
        )
    if isinstance(value, dict):
        if {"before", "after"} <= value.keys():
            return {
                **value,
                "before": _trusted_context(value["before"]),
                "after": _trusted_context(value["after"]),
            }
        return {key: _trusted_context(grouped) for key, grouped in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        filtered = [item for item in value if _trusted_source_url(_field(item, "source_url"))]
        return type(value)(filtered) if not isinstance(value, list) else filtered
    return value


def _comparison_sides(value: Any) -> tuple[Any, Any] | None:
    if isinstance(value, ComparisonResult):
        return value.before, value.after
    if isinstance(value, dict) and {"before", "after"} <= value.keys():
        return value["before"], value["after"]
    return None


def _comparison_result(before: Any, after: Any) -> Any:
    if isinstance(before, CandidateSet) and isinstance(after, CandidateSet):
        return ComparisonResult(before=before, after=after)
    return {"before": before, "after": after}


def _map_comparison(value: Any, operation: Callable[[Any], Any]) -> Any:
    sides = _comparison_sides(value)
    return (
        operation(value)
        if sides is None
        else _comparison_result(operation(sides[0]), operation(sides[1]))
    )


def _comparison_dates(state: QueryState) -> tuple[date, date] | None:
    plan = state.get("query_understanding")
    before = getattr(plan, "comparison_from", None)
    after = getattr(plan, "comparison_to", None)
    return (before, after) if isinstance(before, date) and isinstance(after, date) else None


@dataclass(slots=True)
class GraphServices:
    analyzer: Service = None
    temporal: Service = None
    expander: Service = None
    retriever: Service = None
    dense_retriever: Service = None
    comparison: Service = None
    fusion: Service = None
    reranker: Service = None
    context_expander: Service = None
    evidence_gate: Service = None
    context_builder: Service = None
    generator: Service = None
    verifier: Service = None
    temporal_verifier: Service = None
    legal_verifier: Service = None


def production_services(*, session: Any = None) -> GraphServices:
    if session is None:
        raise RuntimeError("workflow database session is not configured")
    temporal_repository = TemporalRepository(session)
    relation_repository = RelationRepository(session)
    provision_repository = ProvisionRepository(session)
    exact_lookup = __import__("app.retrieval.exact_lookup", fromlist=["ExactLookup"]).ExactLookup(
        provision_repository
    )
    client = _default_client()
    embedder = get_embedding_provider(get_embedding_settings())
    if hasattr(session, "scalars"):
        sparse_texts = list(
            session.scalars(
                select(LegalProvision.retrieval_text).where(
                    LegalProvision.review_status == "ACCEPTED"
                )
            )
        )
        sparse_encoder = load_or_fit_sparse_encoder(sparse_texts)
    else:
        sparse_encoder = BM25SparseEncoder()
    hybrid = HybridRetriever(
        client,
        embedder,
        sparse_encoder,
        exact_lookup,
        temporal_repository=temporal_repository,
        provision_repository=provision_repository,
    )
    expander = LegalContextExpander(relation_repository, temporal_repository)
    return GraphServices(
        temporal=lambda plan, *, query_date: query_date,
        expander=QueryExpander(),
        retriever=hybrid,
        dense_retriever=hybrid,
        fusion=lambda candidates: _items(candidates),
        reranker=lambda question, candidates: candidates,
        context_expander=expander,
        context_builder=lambda candidates: build_context(candidates),
        generator=OpenRouterStructuredGenerator(),
        legal_verifier=LegalVerificationBoundary(),
    )


def _call(
    service: Service, *args: Any, service_name: str, method_names: tuple[str, ...], **kwargs: Any
) -> Any:
    if service is None:
        raise RuntimeError(f"required workflow service {service_name!r} is not configured")
    if callable(service):
        return service(*args, **kwargs)
    for name in method_names:
        method = getattr(service, name, None)
        if callable(method):
            return method(*args, **kwargs)
    raise TypeError(
        f"workflow service {service_name!r} must be callable or expose {', '.join(method_names)}()"
    )


def _question(state: QueryState) -> str:
    return state.get("question") or state.get("input_question", "")


def _plan_date(state: QueryState) -> date | None:
    plan = state.get("query_understanding")
    intent = str(getattr(plan, "intent", ""))
    if intent == "COMPARISON":
        before = getattr(plan, "comparison_from", None)
        after = getattr(plan, "comparison_to", None)
        if isinstance(before, date) and isinstance(after, date):
            return after
        if _exact_references(plan):
            return _today(state)
    if intent in {"HISTORICAL", "SOURCE_SEARCH", "CURRENT"} and isinstance(
        getattr(plan, "effective_date", None), date
    ):
        return plan.effective_date
    temporal = state.get("temporal_context")
    if isinstance(temporal, date):
        return temporal
    if isinstance(temporal, dict):
        for key in ("applied_date", "query_date", "effective_date"):
            if isinstance(value := temporal.get(key), date):
                return value
    return state.get("query_date") or state.get("input_date") or date.today()


def _today(state: QueryState) -> date:
    # Chat requests always seed query_date with today; retain input_date only for
    # legacy internal callers that invoke the graph directly.
    return state.get("query_date") or state.get("input_date") or date.today()


def _exact_reference(plan: Any) -> dict[str, str | None] | None:
    if plan is None:
        return None
    fields = ("document_number", "article", "clause", "point")
    reference = {field: getattr(plan, field, None) for field in fields}
    return reference if any(reference.values()) else None


def _exact_references(plan: Any) -> list[dict[str, str | None]]:
    references = getattr(plan, "references", None) or ()
    if references:
        return [
            {
                field: getattr(reference, field, None)
                for field in ("document_number", "article", "clause", "point")
            }
            for reference in references
        ]
    reference = _exact_reference(plan)
    return [reference] if reference else []


def _max_repair_attempts(state: QueryState) -> int:
    return state.get(
        "max_repair_attempts", get_settings().max_repair_attempts or MAX_REPAIR_ATTEMPTS
    )


def _safe_route(state: QueryState) -> str:
    plan = state.get("query_understanding")
    status = str(getattr(plan, "status", "LEGAL"))
    if status in {"GREETING", "OUT_OF_SCOPE", "CORPUS_NOT_COVERED"}:
        return "abstain"
    if plan is None or str(getattr(plan, "intent", "")) == "OUT_OF_SCOPE":
        return "abstain"
    missing = set(getattr(plan, "missing_query_information", []))
    references = _exact_references(plan)
    if missing.intersection({"query_date", "query_analysis"}):
        return "abstain"
    if str(getattr(plan, "intent", "")) == "COMPARISON":
        if references and len(references) >= 2 and "query_date" not in missing:
            return "expand_query"
        return (
            "abstain"
            if not (
                isinstance(getattr(plan, "comparison_from", None), date)
                and isinstance(getattr(plan, "comparison_to", None), date)
            )
            else "expand_query"
        )
    if missing.intersection({"comparison_dates"}):
        return "abstain"
    return "abstain" if _plan_date(state) is None else "expand_query"


def _canonical_reference_query(question: str) -> str:
    """Rewrite canonical provision IDs into syntax understood by QueryAnalyzer."""
    import re

    pattern = re.compile(
        r"(?:điều\s+khoản\s+)?(?P<document>[a-z]+)-(?P<number>\d{1,4})"
        r"-(?P<year>\d{4})(?:__dieu-(?P<article>\d+))?"
        r"(?:__khoan-(?P<clause>\d+))?(?:__diem-(?P<point>[a-zđ]))?",
        re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        prefix = match.group("document").casefold()
        suffix = {"nd": "NĐ-CP", "tt": "TT", "qd": "QĐ"}.get(prefix, prefix.upper())
        document = f"{match.group('number')}/{match.group('year')}/{suffix}"
        parts = [f"Điều {match.group('article')}" if match.group("article") else document]
        if match.group("article"):
            parts.append(document)
        if match.group("clause"):
            parts.append(f"Khoản {match.group('clause')}")
        if match.group("point"):
            parts.append(f"Điểm {match.group('point')}")
        return " ".join(parts)

    return pattern.sub(replace, question)


def _analyze(state: QueryState, services: GraphServices) -> QueryState:
    question = _question(state)
    analyzer = services.analyzer or QueryAnalyzer()
    analyzed = _call(
        analyzer,
        _canonical_reference_query(question),
        service_name="analyzer",
        method_names=("analyze",),
        current_date=_today(state),
        effect_change_dates=state.get("effect_change_dates", ()),
    )
    if analyzed is not None and hasattr(analyzed, "_original_query"):
        analyzed._original_query = question
    return {
        "query_understanding": analyzed,
        "provision_references": _exact_references(analyzed),
    }


def _resolve_temporal(state: QueryState, services: GraphServices) -> QueryState:
    return {
        "temporal_context": _call(
            services.temporal,
            state.get("query_understanding"),
            service_name="temporal",
            method_names=("resolve",),
            query_date=_today(state),
        )
    }


def _expand_query(state: QueryState, services: GraphServices) -> QueryState:
    return {
        "expansion_set": _call(
            services.expander,
            state.get("query_understanding"),
            service_name="expander",
            method_names=("expand",),
            repair_attempts=state.get("repair_attempts", 0),
            evidence_gaps=state.get("evidence_gaps", []),
        )
    }


def _variant_text(variant: Any) -> str:
    return getattr(variant, "text", None) or str(variant)


def _variant_queries(state: QueryState, plan: Any) -> list[tuple[str, str]]:
    variants = state.get("expansion_set")
    if variants:
        return [
            (_variant_text(variant), getattr(variant, "source", "original")) for variant in variants
        ]
    return [(getattr(plan, "normalized_query", None) or _question(state), "original")]


def _retrieve_one(
    state: QueryState, services: GraphServices, query: str, *, source: str, query_date: date
) -> Any:
    plan = state.get("query_understanding")
    vehicle_type = state.get("vehicle_type") or getattr(plan, "vehicle_type", None)
    if source == "hyde":
        return _call(
            services.dense_retriever,
            query,
            service_name="dense_retriever",
            method_names=("retrieve", "search"),
            query_filter=build_temporal_filter(query_date, vehicle_type=vehicle_type),
            limit=get_retrieval_settings().dense_prefetch,
        )
    references = _exact_references(plan)
    if references and len(references) > 1:
        merged: Any = []
        for reference in references:
            merged = _merge_results(
                merged,
                _call(
                    services.retriever,
                    query,
                    service_name="retriever",
                    method_names=("retrieve",),
                    query_date=query_date,
                    vehicle_type=vehicle_type,
                    exact_reference=reference,
                    candidate_limit=get_retrieval_settings().fusion_limit,
                ),
            )
        return merged
    return _call(
        services.retriever,
        query,
        service_name="retriever",
        method_names=("retrieve",),
        query_date=query_date,
        vehicle_type=vehicle_type,
        exact_reference=_exact_reference(plan),
        candidate_limit=get_retrieval_settings().fusion_limit,
    )


def _cases(plan: Any) -> list[Any]:
    return list(getattr(plan, "cases", ()) or ())


def _case_date(state: QueryState, case: Any) -> date | None:
    value = getattr(case, "temporal_qualifier", None)
    return value if isinstance(value, date) else _plan_date(state)


def _retrieve_case(state: QueryState, services: GraphServices, case: Any) -> Any:
    plan = state.get("query_understanding")
    query_date = _case_date(state, case)
    if query_date is None:
        return []
    scoped = cast(QueryState, dict(state))
    scoped["vehicle_type"] = getattr(case, "vehicle_type", None) or getattr(
        plan, "vehicle_type", None
    )
    queries = [(getattr(case, "query_text", "") or _question(state), "original")]
    queries += [
        (_variant_text(v), getattr(v, "source", "original"))
        for v in (state.get("expansion_set") or ())
    ]
    per_variant = [
        (source, _retrieve_one(scoped, services, query, source=source, query_date=query_date))
        for query, source in queries
    ]
    exact_ids = {
        result.provision_id
        for _, value in per_variant
        for result in _items(value)
        if isinstance(result, RetrievalResult) and "exact" in result.retrieval_sources
    }
    return _fuse_variant_results(
        per_variant,
        final_top_k=get_retrieval_settings().final_top_k,
        exact_ids=exact_ids,
    )


def _retrieve(state: QueryState, services: GraphServices) -> QueryState:
    plan = state.get("query_understanding")
    cases = _cases(plan)
    if cases and str(getattr(plan, "intent", "")) != "COMPARISON":
        grouped = {str(case.case_id): _retrieve_case(state, services, case) for case in cases}
        return {"recall_candidates": grouped, "case_candidates": grouped}
    intent = str(getattr(plan, "intent", ""))
    references = _exact_references(plan)
    if (
        intent == "COMPARISON"
        and references
        and len(references) >= 2
        and _comparison_dates(state) is None
    ):
        query_date = _today(state)
        candidates: Any = []
        for reference in references:
            candidates = _merge_results(
                candidates,
                _call(
                    services.retriever,
                    _question(state),
                    service_name="retriever",
                    method_names=("retrieve",),
                    query_date=query_date,
                    vehicle_type=state.get("vehicle_type"),
                    exact_reference=reference,
                ),
            )
        return {"recall_candidates": candidates}

    if intent == "COMPARISON":
        dates = _comparison_dates(state)
        if dates is None:
            return {"recall_candidates": []}
        before: Any = []
        after: Any = []
        for query, source in _variant_queries(state, plan):
            if source == "hyde":
                before = _merge_results(
                    before,
                    _retrieve_one(state, services, query, source=source, query_date=dates[0]),
                )
                after = _merge_results(
                    after, _retrieve_one(state, services, query, source=source, query_date=dates[1])
                )
            elif services.comparison is not None:
                result = _call(
                    services.comparison,
                    plan,
                    service_name="comparison",
                    method_names=("compare",),
                    date_from=dates[0],
                    date_to=dates[1],
                )
                before = _merge_results(before, result.before)
                after = _merge_results(after, result.after)
            else:
                before = _merge_results(
                    before,
                    _retrieve_one(state, services, query, source=source, query_date=dates[0]),
                )
                after = _merge_results(
                    after, _retrieve_one(state, services, query, source=source, query_date=dates[1])
                )
        return {"recall_candidates": _comparison_result(before, after)}
    query_date = _plan_date(state)
    if query_date is None:
        return {"recall_candidates": []}
    candidates: Any = []
    for query, source in _variant_queries(state, plan):
        candidates = _merge_results(
            candidates, _retrieve_one(state, services, query, source=source, query_date=query_date)
        )
    return {"recall_candidates": candidates}


def _fuse(state: QueryState, services: GraphServices) -> QueryState:
    candidates = state.get("recall_candidates")
    if isinstance(candidates, dict) and not _comparison_sides(candidates):
        return {
            "fused": {
                key: _call(services.fusion, value, service_name="fusion", method_names=("fuse",))
                for key, value in candidates.items()
            }
        }
    return {
        "fused": _map_comparison(
            candidates,
            lambda value: _call(
                services.fusion, value, service_name="fusion", method_names=("fuse",)
            ),
        )
    }


def _rerank(state: QueryState, services: GraphServices) -> QueryState:
    fused: Any = state.get("fused", [])
    if isinstance(fused, dict) and not _comparison_sides(fused):
        return {
            "reranked": {
                key: _call(
                    services.reranker,
                    _question(state),
                    _items(value),
                    service_name="reranker",
                    method_names=("rerank",),
                )
                for key, value in fused.items()
            }
        }
    return {
        "reranked": _map_comparison(
            fused,
            lambda value: _call(
                services.reranker,
                _question(state),
                _items(value),
                service_name="reranker",
                method_names=("rerank",),
            ),
        )
    }


def _expand_context(state: QueryState, services: GraphServices) -> QueryState:
    reranked: Any = state.get("reranked", [])
    if isinstance(reranked, dict) and _cases(state.get("query_understanding")):
        expanded: dict[str, Any] = {}
        for case in _cases(state.get("query_understanding")):
            key = str(case.case_id)
            values = _items(reranked.get(key, []))
            additions = _call(
                services.context_expander,
                values,
                service_name="context_expander",
                method_names=("expand",),
                query_date=_case_date(state, case),
            )
            combined = values + _items(additions)
            expanded[key] = (
                deduplicate_results(combined)
                if combined and all(isinstance(x, RetrievalResult) for x in combined)
                else combined
            )
        return {"expanded_context": expanded}
    sides = _comparison_sides(reranked)
    if sides is not None and (dates := _comparison_dates(state)) is not None:
        expanded_sides: list[Any] = []
        for candidates, side_date in zip(sides, dates, strict=True):
            additions = _call(
                services.context_expander,
                _items(candidates),
                service_name="context_expander",
                method_names=("expand",),
                query_date=side_date,
            )
            values = _items(candidates) + _items(additions)
            expanded_sides.append(
                candidates.model_copy(update={"results": deduplicate_results(values)})
                if isinstance(candidates, CandidateSet)
                else values
            )
        return {"expanded_context": _comparison_result(*expanded_sides)}
    serving_date = _plan_date(state)
    if serving_date is None:
        return {"expanded_context": reranked}
    values = _items(reranked)
    additions = _call(
        services.context_expander,
        values,
        service_name="context_expander",
        method_names=("expand",),
        query_date=serving_date,
    )
    combined = values + _items(additions)
    return {
        "expanded_context": deduplicate_results(combined)
        if combined and all(isinstance(item, RetrievalResult) for item in combined)
        else combined
    }


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _filter_case_context(
    state: QueryState, context: dict[str, Any], case_evidence: dict[str, Any]
) -> dict[str, Any]:
    """Retain only gate-approved provisions for each independently answered case."""
    filtered: dict[str, Any] = {}
    for key, values in context.items():
        evidence = case_evidence.get(key)
        covered = set(_field(evidence, "candidate_provisions", ()) or ())
        if not covered:
            covered.update(_field(evidence, "covered_provisions", ()) or ())
        items = _items(values)
        filtered[key] = [item for item in items if str(_field(item, "provision_id", "")) in covered]
    return filtered


def _check_evidence(state: QueryState, services: GraphServices) -> QueryState:
    gate = services.evidence_gate or EvidenceCompletenessGate()
    context: Any = _trusted_context(state.get("expanded_context", []))
    if isinstance(context, dict) and _cases(state.get("query_understanding")):
        plan = state.get("query_understanding")
        cases = {str(case.case_id): case for case in _cases(plan)}
        case_results = {
            key: _call(
                gate,
                plan.model_copy(update={"cases": [cases[key]]})
                if plan is not None and hasattr(plan, "model_copy") and key in cases
                else plan,
                _items(value),
                service_name="evidence_gate",
                method_names=("evaluate",),
            )
            for key, value in context.items()
        }
        case_gaps = {
            key: list(result.evidence_gaps)
            for key, result in case_results.items()
            if result.status != EvidenceStatus.COMPLETE
        }
        return {
            "expanded_context": context,
            "case_evidence": case_results,
            "evidence_status": (
                EvidenceStatus.COMPLETE if not case_gaps else EvidenceStatus.INCOMPLETE
            ),
            "evidence_gaps": list(
                dict.fromkeys(gap for values in case_gaps.values() for gap in values)
            ),
            "evidence_limitations": case_gaps,
        }
    sides = _comparison_sides(context)
    if sides is None:
        result = _call(
            gate,
            state.get("query_understanding"),
            _items(context),
            service_name="evidence_gate",
            method_names=("evaluate",),
        )
        return {
            "expanded_context": context,
            "evidence_status": result.status,
            "evidence_gaps": list(result.evidence_gaps),
        }
    results: list[Any] = [
        _call(
            gate,
            state.get("query_understanding"),
            _items(side),
            service_name="evidence_gate",
            method_names=("evaluate",),
        )
        for side in sides
    ]
    gaps: list[Any] = list(dict.fromkeys(gap for result in results for gap in result.evidence_gaps))
    return {
        "expanded_context": context,
        "evidence_status": EvidenceStatus.COMPLETE
        if all(result.status == EvidenceStatus.COMPLETE for result in results)
        else EvidenceStatus.INCOMPLETE,
        "evidence_gaps": gaps,
    }


def _evidence_route(state: QueryState) -> str:
    if state.get("evidence_status") == EvidenceStatus.COMPLETE:
        return "build_context"
    if state.get("repair_attempts", 0) >= _max_repair_attempts(state):
        return "abstain"
    return "targeted_retrieval"


def _targeted(state: QueryState, services: GraphServices) -> QueryState:
    attempts = state.get("repair_attempts", 0) + 1
    plan = state.get("query_understanding")
    gaps = state.get("evidence_gaps", [])
    queries = [targeted_query_for_gap(gap, plan) for gap in gaps if plan is not None] or [
        _question(state)
    ]
    expansion_set = state.get("expansion_set") or []
    if services.expander is not None and plan is not None:
        expansion_set = _call(
            services.expander,
            plan,
            service_name="expander",
            method_names=("expand",),
            repair_attempts=attempts,
            evidence_gaps=gaps,
            existing_variants=expansion_set,
        )
    hyde_queries = [
        (_variant_text(variant), "hyde")
        for variant in expansion_set
        if getattr(variant, "source", None) == "hyde"
    ]
    repair_queries = [(query, "original") for query in queries] + hyde_queries
    comparison = _comparison_sides(state.get("recall_candidates"))
    dates = _comparison_dates(state)
    if comparison is not None and dates is not None:
        updated: list[Any] = []
        for existing, repair_date in zip(comparison, dates, strict=True):
            targeted: Any = []
            for query, source in repair_queries:
                targeted = _merge_results(
                    targeted,
                    _retrieve_one(state, services, query, source=source, query_date=repair_date),
                )
            updated.append(_merge_results(existing, targeted))
        return {
            "repair_attempts": attempts,
            "expansion_set": expansion_set,
            "recall_candidates": _comparison_result(*updated),
        }
    serving_date = _plan_date(state)
    if serving_date is None or str(getattr(plan, "intent", "")) == "OUT_OF_SCOPE":
        return {
            "repair_attempts": attempts,
            "expansion_set": expansion_set,
            "recall_candidates": state.get("recall_candidates", []),
        }
    targeted_candidates: Any = []
    for query, source in repair_queries:
        targeted_candidates = _merge_results(
            targeted_candidates,
            _retrieve_one(state, services, query, source=source, query_date=serving_date),
        )
    return {
        "repair_attempts": attempts,
        "expansion_set": expansion_set,
        "recall_candidates": _merge_results(
            state.get("recall_candidates", []), targeted_candidates
        ),
    }


def _build_context(state: QueryState, services: GraphServices) -> QueryState:
    context: Any = _trusted_context(state.get("expanded_context", state.get("reranked", [])))
    if isinstance(context, dict) and _cases(state.get("query_understanding")):
        case_evidence = state.get("case_evidence") or {}
        scoped_context = _filter_case_context(state, context, case_evidence)
        value = _call(
            services.context_builder,
            scoped_context,
            service_name="context_builder",
            method_names=("build",),
        )
        return (
            {"context_package": scoped_context, "prompt_context": value}
            if isinstance(value, str)
            else {"context_package": value}
        )
    sides = _comparison_sides(context)
    if sides is None:
        value = _call(
            services.context_builder,
            context,
            service_name="context_builder",
            method_names=("build",),
        )
        return (
            {"context_package": context, "prompt_context": value}
            if isinstance(value, str)
            else {"context_package": value}
        )
    values = [
        _call(
            services.context_builder, side, service_name="context_builder", method_names=("build",)
        )
        for side in sides
    ]
    return {"context_package": _comparison_result(*values)}


def _normalize_answer_numbers(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {name: _normalize_answer_numbers(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_normalize_answer_numbers(item, key) for item in value]
    if key == "numbers" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return value


def _is_quota_error(exc: BaseException) -> bool:
    tokens = ("resource_exhausted", "quota", "rate limit", "rate_limit", "429")
    current: BaseException | None = exc
    seen: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            return False
        seen.add(id(current))
        if any(token in str(current).casefold() for token in tokens):
            return True
        current = current.__cause__ or current.__context__
    return False


def _evidence_fallback(state: QueryState) -> StructuredAnswer | None:
    """Build a minimal answer from gate-approved, scoped evidence only."""
    plan = state.get("query_understanding")
    intent = str(getattr(plan, "intent", ""))
    supported = {"CURRENT", "HISTORICAL", "COMPARISON", "SOURCE_SEARCH"}
    if intent not in supported or state.get("evidence_status") != EvidenceStatus.COMPLETE:
        return None

    def field(item: Any, name: str, default: Any = None) -> Any:
        return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)

    def records(value: Any) -> list[Any]:
        return [
            item
            for item in _items(value)
            if field(item, "review_status", "ACCEPTED") == "ACCEPTED"
            and field(item, "provision_id")
            and str(field(item, "text", "")).strip()
        ]

    raw_context = state.get("context_package")
    if raw_context is None:
        return None
    sides = _comparison_sides(raw_context)
    if sides is not None:
        scoped = [records(side) for side in sides]
        if not all(scoped):
            return None
        selected = [item for side in scoped for item in side]
    elif isinstance(raw_context, dict) and _cases(plan):
        selected = [item for value in raw_context.values() for item in records(value)]
    else:
        selected = records(raw_context)
    if not selected:
        return None

    # Preserve the accepted provision text and ID; never invent legal content.
    unique: dict[str, Any] = {}
    for item in selected:
        unique.setdefault(str(field(item, "provision_id")), item)
    claims = [
        {
            "claim": str(field(item, "text")).strip(),
            "claim_type": "OTHER",
            "provision_ids": [provision_id],
        }
        for provision_id, item in unique.items()
    ]
    return StructuredAnswer.model_validate(
        {"answer_summary": " ".join(claim["claim"] for claim in claims), "claims": claims}
    )


_source_search_fallback = _evidence_fallback


def _generate(state: QueryState, services: GraphServices) -> QueryState:
    try:
        answer = _call(
            services.generator or OpenRouterStructuredGenerator(),
            _question(state),
            state.get(
                "prompt_context", state.get("context_package", state.get("expanded_context", []))
            ),
            service_name="generator",
            method_names=("generate",),
        )
    except StructuredGenerationError as exc:
        fallback = _evidence_fallback(state) if _is_quota_error(exc) else None
        if fallback is not None:
            return {"draft_answer": fallback}
        quota = _is_quota_error(exc)
        return {
            "draft_answer": None,
            "verification_result": {
                "status": "ABSTAIN" if quota else "REPAIRABLE",
                "reason_code": "GENERATION_QUOTA_EXHAUSTED" if quota else "L1_SCHEMA_INVALID",
                "error": str(exc),
            },
        }
    try:
        if str(getattr(state.get("query_understanding"), "intent", "")) == "COMPARISON":
            fallback = _evidence_fallback(state)
            if fallback is not None:
                return {"draft_answer": fallback}
        if answer.should_abstain:
            fallback = _evidence_fallback(state)
            if fallback is not None:
                return {"draft_answer": fallback}
        return {"draft_answer": answer}
    except Exception as exc:
        return {
            "draft_answer": None,
            "verification_result": {
                "status": "ABSTAIN",
                "reason_code": "L1_SCHEMA_INVALID",
                "error": str(exc),
            },
        }


def _verify(state: QueryState, services: GraphServices) -> QueryState:
    draft = state.get("draft_answer")
    if draft is None:
        return {
            "verification_result": state.get(
                "verification_result", {"status": "REPAIRABLE", "reason_code": "L1_SCHEMA_INVALID"}
            )
        }
    try:
        answer = StructuredAnswer.model_validate(_normalize_answer_numbers(draft))
    except Exception as exc:
        return {
            "verification_result": {
                "status": "ABSTAIN",
                "reason_code": "L1_SCHEMA_INVALID",
                "error": str(exc),
            }
        }
    if answer.should_abstain:
        return {
            "verification_result": {"status": "ABSTAIN", "reason_code": "INSUFFICIENT_EVIDENCE"}
        }
    context_by_id: dict[str, Any] = {}
    raw_context = state.get("context_package")
    if raw_context is None:
        raw_context = state.get("expanded_context", [])
    context_items = _items(raw_context)
    if isinstance(raw_context, dict):
        context_items = [item for grouped in raw_context.values() for item in _items(grouped)]

    def field(item: Any, name: str, default: Any = None) -> Any:
        return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)

    for item in context_items:
        if field(item, "review_status", "ACCEPTED") != "ACCEPTED":
            continue
        provision_id = field(item, "provision_id")
        if provision_id and provision_id not in context_by_id:
            context_by_id[provision_id] = item
    context = list(context_by_id.values())
    if not all(getattr(claim, "provision_ids", None) for claim in answer.claims):
        return {"verification_result": {"status": "ABSTAIN", "reason_code": "L1_SCHEMA_INVALID"}}
    legal = _call(
        services.legal_verifier or LegalVerificationBoundary(),
        answer,
        context,
        query_date=_plan_date(state),
        service_name="legal_verifier",
        method_names=("verify",),
    )
    if not legal.passed:
        return {
            "verification_result": {
                "status": "ABSTAIN",
                "reason_code": legal.reason_code or "VERIFICATION_FAILURE",
                "issues": list(legal.issues),
                "missing": list(legal.missing),
            }
        }
    cited: list[Any] = []
    used_provision_ids: set[str] = set()
    for claim in answer.claims:
        if (
            len(claim.provision_ids) != 1
            or len(set(claim.provision_ids)) != 1
            or claim.provision_ids[0] in used_provision_ids
        ):
            return {
                "verification_result": {
                    "status": "ABSTAIN",
                    "reason_code": "L2_CITATION_MISSING",
                }
            }
        provision_id = claim.provision_ids[0]
        claim_record = context_by_id.get(provision_id)
        if claim_record is None:
            return {
                "verification_result": {
                    "status": "ABSTAIN",
                    "reason_code": "L2_CITATION_MISSING",
                }
            }
        used_provision_ids.add(provision_id)
        cited.append(claim_record)
    temporal = (
        _call(
            services.temporal_verifier,
            cited,
            query_date=_plan_date(state),
            service_name="temporal_verifier",
            method_names=("verify",),
        )
        if services.temporal_verifier is not None
        else verify_temporal(cited, query_date=_plan_date(state))
    )
    if not temporal.verified:
        return {
            "verification_result": {
                "status": "ABSTAIN",
                "reason_code": temporal.reason_code or "L3_TEMPORAL_INVALID",
            }
        }
    return {"verification_result": {"status": "VALID", "verified_claims": answer.claims}}


def _finalize(state: QueryState) -> QueryState:
    verification: dict[str, Any] = state.get("verification_result", {})
    draft = state.get("draft_answer")
    if verification.get("status") != "VALID" or draft is None:
        return _abstain(state)
    answer = StructuredAnswer.model_validate(draft)
    final_response = dict(state.get("final_response") or {})
    final_response.update(
        {
            "status": final_response.get("status", "COMPLETED"),
            "answer_summary": answer.answer_summary,
            "claims": [claim.model_dump() for claim in answer.claims],
        }
    )
    for field in ("missing_information", "evidence_limitations"):
        if hasattr(answer, field):
            final_response[field] = getattr(answer, field)
        elif field in state:
            final_response[field] = state.get(field)
    return {"final_response": final_response}


def _abstain(state: QueryState) -> QueryState:
    verification = dict(state.get("verification_result") or {})
    plan = state.get("query_understanding")
    plan_status = str(getattr(plan, "status", ""))
    plan_intent = str(getattr(plan, "intent", ""))
    out_of_scope = plan_status == "OUT_OF_SCOPE" or plan_intent == "OUT_OF_SCOPE"
    verification.setdefault("status", "ABSTAIN")
    verification.setdefault(
        "reason_code", "OUT_OF_SCOPE" if out_of_scope else "INSUFFICIENT_EVIDENCE"
    )
    public_status = "OUT_OF_SCOPE" if out_of_scope else "INSUFFICIENT_EVIDENCE"
    verification["public_status"] = public_status
    return {
        "verification_result": verification,
        "status": public_status,
        "final_response": {"status": public_status, "answer": None},
    }


def build_query_graph(services: GraphServices | None = None) -> CompiledStateGraph:
    services = services or GraphServices()
    graph = StateGraph(QueryState)
    nodes: dict[str, Callable[..., QueryState]] = {
        "analyze_query": lambda s: _analyze(s, services),
        "resolve_temporal": lambda s: _resolve_temporal(s, services),
        "expand_query": lambda s: _expand_query(s, services),
        "retrieve_parallel": lambda s: _retrieve(s, services),
        "fuse": lambda s: _fuse(s, services),
        "rerank": lambda s: _rerank(s, services),
        "expand_legal_context": lambda s: _expand_context(s, services),
        "check_evidence": lambda s: _check_evidence(s, services),
        "targeted_retrieval": lambda s: _targeted(s, services),
        "build_context": lambda s: _build_context(s, services),
        "generate": lambda s: _generate(s, services),
        "verify": lambda s: _verify(s, services),
        "finalize": _finalize,
        "abstain": _abstain,
        "regenerate": lambda s: {**s, "repair_attempts": s.get("repair_attempts", 0) + 1},
        "temporal_retry": lambda s: {**s, "repair_attempts": s.get("repair_attempts", 0) + 1},
    }
    for name, node in nodes.items():
        graph.add_node(name, node)
    order = [
        "analyze_query",
        "resolve_temporal",
        "expand_query",
        "retrieve_parallel",
        "fuse",
        "rerank",
        "expand_legal_context",
        "check_evidence",
    ]
    graph.add_edge(START, order[0])
    graph.add_edge(order[0], order[1])
    graph.add_conditional_edges("resolve_temporal", _safe_route)
    for index in range(2, len(order) - 1):
        graph.add_edge(order[index], order[index + 1])
    graph.add_conditional_edges("check_evidence", _evidence_route)
    graph.add_edge("targeted_retrieval", "fuse")
    graph.add_edge("build_context", "generate")
    graph.add_edge("generate", "verify")
    graph.add_conditional_edges(
        "verify",
        lambda state: (
            "finalize"
            if state.get("verification_result", {}).get("status") == "VALID"
            else repair_route(state, max_attempts=_max_repair_attempts(state))
        ),
    )
    graph.add_edge("regenerate", "generate")
    graph.add_edge("temporal_retry", "resolve_temporal")
    graph.add_edge("finalize", END)
    graph.add_edge("abstain", END)
    return graph.compile()


__all__ = ["GraphServices", "build_query_graph", "production_services"]
