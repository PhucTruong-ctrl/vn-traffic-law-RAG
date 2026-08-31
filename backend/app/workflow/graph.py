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

from .state import QueryState

Service = Any


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


def _today(state: QueryState) -> date:
    return state.get("query_date") or state.get("input_date") or date.today()


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


def _retrieve(state: QueryState, services: GraphServices) -> QueryState:
    plan = state.get("query_understanding")
    query = getattr(plan, "normalized_query", None) or _question(state)
    value = _call(
        services.retriever,
        query,
        service_name="retriever",
        method_names=("retrieve",),
        query_date=_today(state),
        vehicle_type=state.get("vehicle_type"),
    )
    return {"recall_candidates": value}


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
    value = _call(
        services.context_expander,
        state.get("reranked", []),
        service_name="context_expander",
        method_names=("expand",),
        query_date=_today(state),
    )
    return {"expanded_context": value}


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
    value = _call(
        services.retriever,
        queries[0] if queries else _question(state),
        service_name="retriever",
        method_names=("retrieve",),
        query_date=_today(state),
        vehicle_type=state.get("vehicle_type"),
    )
    return {"repair_attempts": attempts, "recall_candidates": value}


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
    for index in range(len(order) - 1):
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
