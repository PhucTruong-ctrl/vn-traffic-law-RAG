from types import SimpleNamespace

from app.query.evidence_gate import EvidenceStatus
from app.query.query_understanding_types import EvidenceType
from app.workflow.graph import GraphServices, build_query_graph


def services(**overrides):
    defaults = dict(
        temporal=lambda plan, *, query_date: query_date,
        expander=lambda plan, **_: [plan] if plan is not None else [],
        retriever=lambda query, **_: [],
        fusion=lambda candidates: candidates,
        reranker=lambda question, candidates: candidates,
        context_expander=lambda candidates, **_: candidates,
        context_builder=lambda candidates: candidates,
    )
    defaults.update(overrides)
    return GraphServices(**defaults)


def test_graph_registers_only_documented_application_nodes() -> None:
    graph = build_query_graph()
    assert set(graph.nodes) - {"__start__"} == {
        "analyze_query",
        "resolve_temporal",
        "expand_query",
        "retrieve_parallel",
        "fuse",
        "rerank",
        "expand_legal_context",
        "check_evidence",
        "targeted_retrieval",
        "build_context",
        "generate",
        "verify",
        "finalize",
        "abstain",
    }


def test_incomplete_evidence_increments_counter_then_abstains() -> None:
    class IncompleteGate:
        def evaluate(self, plan, context):
            return type("Gate", (), {"status": EvidenceStatus.INCOMPLETE, "evidence_gaps": []})()

    graph = build_query_graph(services(evidence_gate=IncompleteGate()))
    state = graph.invoke(
        {"question": "mức phạt", "max_repair_attempts": 1, "repair_attempts": 0}
    )
    assert state["repair_attempts"] == 1
    assert state["final_response"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_generate_and_verify_are_non_answering_skeletons() -> None:
    class CompleteGate:
        def evaluate(self, plan, context):
            return type("Gate", (), {"status": EvidenceStatus.COMPLETE, "evidence_gaps": []})()

    graph = build_query_graph(services(evidence_gate=CompleteGate()))
    state = graph.invoke({"question": "mức phạt", "max_repair_attempts": 0})
    assert state["final_response"]["status"] == "SKELETON"
    assert state["verification_result"]["verified"] is False


def test_graph_rejects_missing_required_service() -> None:
    graph = build_query_graph(services(retriever=None))
    try:
        graph.invoke({"question": "mức phạt", "max_repair_attempts": 0})
    except RuntimeError as error:
        assert "retriever" in str(error)
    else:
        raise AssertionError("missing retriever must fail explicitly")


def test_complete_evidence_keeps_reranked_seeds_with_expanded_additions() -> None:
    class CompleteGate:
        def evaluate(self, plan, context):
            assert context == ["seed", "addition"]
            return type("Gate", (), {"status": EvidenceStatus.COMPLETE, "evidence_gaps": []})()

    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: SimpleNamespace(normalized_query=question),
            retriever=lambda query, **_: ["seed"],
            context_expander=lambda candidates, **_: ["addition"],
            evidence_gate=CompleteGate(),
        )
    )
    state = graph.invoke({"question": "question", "max_repair_attempts": 0})

    assert state["context_package"] == ["seed", "addition"]


def test_targeted_repair_merges_initial_and_missing_points_provisions() -> None:
    class RepairGate:
        calls = 0

        def evaluate(self, plan, context):
            self.calls += 1
            if self.calls == 1:
                assert context == ["fine"]
                return type(
                    "Gate",
                    (),
                    {
                        "status": EvidenceStatus.INCOMPLETE,
                        "evidence_gaps": [EvidenceType.LICENSE_POINTS],
                    },
                )()
            assert context == ["fine", "points"]
            return type("Gate", (), {"status": EvidenceStatus.COMPLETE, "evidence_gaps": []})()

    responses = iter((["fine"], ["points"]))
    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: SimpleNamespace(normalized_query=question),
            retriever=lambda query, **_: next(responses),
            context_expander=lambda candidates, **_: [],
            evidence_gate=RepairGate(),
        )
    )
    state = graph.invoke({"question": "fine and points", "max_repair_attempts": 1})

    assert state["repair_attempts"] == 1
    assert state["context_package"] == ["fine", "points"]
