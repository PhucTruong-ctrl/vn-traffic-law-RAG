"""Controlled LangGraph skeleton for the legal retrieval workflow.

The services are deliberately injected: this module owns orchestration, not
provider or legal-answer policy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.query.evidence_gate import EvidenceCompletenessGate, EvidenceStatus, targeted_query_for_gap
from app.query.query_understanding import QueryAnalyzer
from app.retrieval.comparison import ComparisonResult
from app.retrieval.contracts import CandidateSet, RetrievalResult
from app.retrieval.filters import deduplicate_results

from .state import QueryState

Service = Any


def _items(value: Any) -> list[Any]:
    if isinstance(value, CandidateSet):
        return list(value.results)
    if value is None:
        return []
    return list(value)


def _merge_results(existing: Any, additions: Any) -> Any:
    """Merge retrieval values while retaining the original CandidateSet shape."""
    merged = _items(existing) + _items(additions)
    if merged and all(isinstance(item, RetrievalResult) for item in merged):
        merged = deduplicate_results(merged)
    if isinstance(existing, CandidateSet):
        return existing.model_copy(update={"results": merged})
    if isinstance(additions, CandidateSet):
        return additions.model_copy(update={"results": merged})
    return merged



@dataclass(slots=True)
class GraphServices:
    """Injected collaborators for graph nodes.

    ``analyzer`` and ``evidence_gate`` have deterministic defaults.  Retrieval
    collaborators are required once their node executes; a missing one is a
    configuration error, not an empty retrieval result.
    """

    analyzer: Service = None
    temporal: Service = None
    expander: Service = None
    retriever: Service = None
    comparison: Service = None
    fusion: Service = None
    reranker: Service = None
    context_expander: Service = None
    evidence_gate: Service = None
    context_builder: Service = None
    generator: Service = None
    verifier: Service = None


def _call(
    service: Service,
    *args: Any,
    service_name: str,
    method_names: tuple[str, ...],
    **kwargs: Any,
) -> Any:
    """Call an injected service and fail clearly on invalid wiring."""
    if service is None:
        raise RuntimeError(
            f"required workflow service {service_name!r} is not configured"
        )
    if callable(service):
        return service(*args, **kwargs)
    for name in method_names:
        method = getattr(service, name, None)
        if callable(method):
            return method(*args, **kwargs)
    expected = ", ".join(method_names)
    raise TypeError(
        f"workflow service {service_name!r} must be callable or expose {expected}()"
    )





def _question(state: QueryState) -> str:
    return state.get("question") or state.get("input_question", "")
def _plan_date(state: QueryState) -> date | None:
    """Return the plan's serving date, never an arbitrary fallback date."""
    plan = state.get("query_understanding")
    intent = str(getattr(plan, "intent", ""))
    if intent == "COMPARISON":
        return getattr(plan, "comparison_to", None)
    effective_date = getattr(plan, "effective_date", None)
    if intent in {"HISTORICAL", "SOURCE_SEARCH", "CURRENT"} and isinstance(
        effective_date, date
    ):
        return effective_date
    temporal = state.get("temporal_context")
    if isinstance(temporal, date):
        return temporal
    if isinstance(temporal, dict):
        for key in ("applied_date", "query_date", "effective_date"):
            if isinstance(value := temporal.get(key), date):
                return value
    return getattr(plan, "effective_date", None) or state.get("query_date") or state.get(
        "input_date"
    )


def _today(state: QueryState) -> date:
    return state.get("query_date") or state.get("input_date") or date.today()


def _exact_reference(plan: Any) -> dict[str, str | None] | None:
    if plan is None:
        return None
    fields = ("document_number", "article", "clause", "point")
    reference = {field: getattr(plan, field, None) for field in fields}
    return reference if any(reference.values()) else None


def _safe_route(state: QueryState) -> str:
    plan = state.get("query_understanding")
    if plan is None or str(getattr(plan, "intent", "")) == "OUT_OF_SCOPE":
        return "abstain"
    missing = set(getattr(plan, "missing_query_information", []))
    if missing.intersection({"query_date", "comparison_dates", "query_analysis"}):
        return "abstain"
    if str(getattr(plan, "intent", "")) == "COMPARISON":
        if not (
            isinstance(getattr(plan, "comparison_from", None), date)
            and isinstance(getattr(plan, "comparison_to", None), date)
        ):
            return "abstain"
    elif _plan_date(state) is None:
        return "abstain"
    return "expand_query"


def _analyze(state: QueryState, services: GraphServices) -> QueryState:
    plan = _call(
        services.analyzer or QueryAnalyzer(),
        _question(state),
        service_name="analyzer",
        method_names=("analyze",),
        current_date=_today(state),
    )
    return {"query_understanding": plan} if plan is not None else {}


def _resolve_temporal(state: QueryState, services: GraphServices) -> QueryState:
    value = _call(
        services.temporal,
        state.get("query_understanding"),
        service_name="temporal",
        method_names=("resolve",),
        query_date=_today(state),
    )
    return {"temporal_context": value}


def _expand_query(state: QueryState, services: GraphServices) -> QueryState:
    plan = state.get("query_understanding")
    value = _call(
        services.expander,
        plan,
        service_name="expander",
        method_names=("expand",),
        repair_attempts=state.get("repair_attempts", 0),
        evidence_gaps=state.get("evidence_gaps", []),
    )
    return {"expansion_set": value}


def _variant_text(variant: Any) -> str:
    return getattr(variant, "text", None) or str(variant)


def _variant_queries(state: QueryState, plan: Any) -> list[str]:
    variants = state.get("expansion_set")
    if variants:
        return [_variant_text(variant) for variant in variants]
    return [getattr(plan, "normalized_query", None) or _question(state)]


def _retrieve_one(
    state: QueryState,
    services: GraphServices,
    query: str,
    *,
    query_date: date,
) -> Any:
    plan = state.get("query_understanding")
    return _call(
        services.retriever,
        query,
        service_name="retriever",
        method_names=("retrieve",),
        query_date=query_date,
        vehicle_type=getattr(plan, "vehicle_type", None) or state.get("vehicle_type"),
        exact_reference=_exact_reference(plan),
    )


def _retrieve(state: QueryState, services: GraphServices) -> QueryState:
    plan = state.get("query_understanding")
    intent = str(getattr(plan, "intent", ""))
    queries = _variant_queries(state, plan)
    if intent == "COMPARISON":
        date_from = getattr(plan, "comparison_from", None)
        date_to = getattr(plan, "comparison_to", None)
        if not isinstance(date_from, date) or not isinstance(date_to, date):
            return {"recall_candidates": []}
        before: Any = []
        after: Any = []
        for query in queries:
            if services.comparison is not None:
                comparison_plan = plan
                if query != getattr(plan, "normalized_query", None) and hasattr(
                    plan, "model_copy"
                ):
                    comparison_plan = plan.model_copy(update={"normalized_query": query})
                result = _call(
                    services.comparison,
                    comparison_plan,
                    service_name="comparison",
                    method_names=("compare",),
                    date_from=date_from,
                    date_to=date_to,
                )
                before = _merge_results(before, result.before)
                after = _merge_results(after, result.after)
            else:
                before = _merge_results(
                    before, _retrieve_one(state, services, query, query_date=date_from)
                )
                after = _merge_results(
                    after, _retrieve_one(state, services, query, query_date=date_to)
                )
        if isinstance(before, CandidateSet) and isinstance(after, CandidateSet):
            comparison = ComparisonResult(before=before, after=after)
        else:
            comparison = {"before": before, "after": after}
        return {"recall_candidates": comparison}
    query_date = _plan_date(state)
    if query_date is None:
        return {"recall_candidates": []}
    candidates: Any = []
    for query in queries:
        candidates = _merge_results(
            candidates, _retrieve_one(state, services, query, query_date=query_date)
        )
    return {"recall_candidates": candidates}


def _fuse(state: QueryState, services: GraphServices) -> QueryState:
    value = _call(
        services.fusion,
        state.get("recall_candidates"),
        service_name="fusion",
        method_names=("fuse",),
    )
    return {"fused": value}


def _rerank(state: QueryState, services: GraphServices) -> QueryState:
    value = _call(
        services.reranker,
        _question(state),
        state.get("fused", []),
        service_name="reranker",
        method_names=("rerank",),
    )
    return {"reranked": value}


def _expand_context(state: QueryState, services: GraphServices) -> QueryState:
    query_date = _plan_date(state)
    if query_date is None:
        return {"expanded_context": state.get("reranked", [])}
    additions = _call(
        services.context_expander,
        state.get("reranked", []),
        service_name="context_expander",
        method_names=("expand",),
        query_date=query_date,
    )
    expanded = _items(state.get("reranked", [])) + _items(additions)
    if expanded and all(isinstance(item, RetrievalResult) for item in expanded):
        expanded = deduplicate_results(expanded)
    return {"expanded_context": expanded}


def _check_evidence(state: QueryState, services: GraphServices) -> QueryState:
    gate = services.evidence_gate or EvidenceCompletenessGate()
    plan = state.get("query_understanding")
    context: list[Any] = state.get("expanded_context", [])
    result = _call(
        gate,
        plan,
        context,
        service_name="evidence_gate",
        method_names=("evaluate",),
    )
    return {"evidence_status": result.status, "evidence_gaps": list(result.evidence_gaps)}


def _evidence_route(state: QueryState) -> str:
    if state.get("evidence_status") == EvidenceStatus.COMPLETE:
        return "build_context"
    if state.get("repair_attempts", 0) >= state.get("max_repair_attempts", 1):
        return "abstain"
    return "targeted_retrieval"
def _targeted(state: QueryState, services: GraphServices) -> QueryState:
    attempts = state.get("repair_attempts", 0) + 1
    plan = state.get("query_understanding")
    gaps = state.get("evidence_gaps", [])
    queries = [targeted_query_for_gap(gap, plan) for gap in gaps if plan is not None]
    if not queries:
        queries = [_question(state)]
    query_date = _plan_date(state)
    if query_date is None or str(getattr(plan, "intent", "")) == "OUT_OF_SCOPE":
        return {
            "repair_attempts": attempts,
            "recall_candidates": state.get("recall_candidates", []),
        }
    targeted_candidates: Any = []
    for query in queries:
        result = _call(
            services.retriever,
            query,
            service_name="retriever",
            method_names=("retrieve",),
            query_date=query_date,
            vehicle_type=getattr(plan, "vehicle_type", None) or state.get("vehicle_type"),
            exact_reference=_exact_reference(plan),
        )
        targeted_candidates = _merge_results(targeted_candidates, result)
    return {
        "repair_attempts": attempts,
        "recall_candidates": _merge_results(
            state.get("recall_candidates", []), targeted_candidates
        ),
    }




def _build_context(state: QueryState, services: GraphServices) -> QueryState:
    value = _call(
        services.context_builder,
        state.get("expanded_context", state.get("reranked", [])),
        service_name="context_builder",
        method_names=("build",),
    )
    return {"context_package": value}


def _generate(state: QueryState, services: GraphServices) -> QueryState:
    return {"draft_answer": {"status": "SKELETON", "answer": None}}


def _verify(state: QueryState, services: GraphServices) -> QueryState:
    return {"verification_result": {"status": "SKELETON", "verified": False}}


def _finalize(state: QueryState) -> QueryState:
    return {"final_response": state.get("draft_answer", {"status": "SKELETON", "answer": None})}


def _abstain(state: QueryState) -> QueryState:
    return {"final_response": {"status": "INSUFFICIENT_EVIDENCE", "answer": None}}


def build_query_graph(services: GraphServices | None = None) -> CompiledStateGraph:
    """Compile the fixed-order graph and bounded evidence-repair loop."""
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
    graph.add_edge("verify", "finalize")
    graph.add_edge("finalize", END)
    graph.add_edge("abstain", END)
    return graph.compile()


__all__ = ["GraphServices", "build_query_graph"]
