from datetime import date
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


def test_retrieve_passes_query_plan_exact_reference() -> None:
    calls = []
    plan = SimpleNamespace(
        normalized_query="Điều 7",
        document_number="168/2024/NĐ-CP",
        article="7",
        clause="1",
        point="đ",
        vehicle_type="xe máy",
        intent="SOURCE_SEARCH",
        effective_date=date(2024, 1, 1),
        missing_query_information=[],
    )

    def retrieve(query, **kwargs):
        calls.append((query, kwargs))
        return []

    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: plan,
            temporal=lambda plan, **_: date(2024, 1, 1),
            retriever=retrieve,
            evidence_gate=type(
                "CompleteGate",
                (),
                {"evaluate": lambda self, plan, context: type(
                    "Gate", (), {"status": EvidenceStatus.COMPLETE, "evidence_gaps": []}
                )()},
            )(),
        )
    )
    graph.invoke({"question": "Điều 7", "max_repair_attempts": 0})
    assert calls[0][1]["exact_reference"] == {
        "document_number": "168/2024/NĐ-CP",
        "article": "7",
        "clause": "1",
        "point": "đ",
    }


def test_targeted_repair_retrieves_and_merges_every_gap() -> None:
    calls = []

    class Gate:
        count = 0

        def evaluate(self, plan, context):
            self.count += 1
            if self.count == 1:
                return type(
                    "Result",
                    (),
                    {
                        "status": EvidenceStatus.INCOMPLETE,
                        "evidence_gaps": [
                            EvidenceType.MONETARY_PENALTY,
                            EvidenceType.LICENSE_POINTS,
                        ],
                    },
                )()
            assert context == ["initial", "penalty", "points"]
            return type(
                "Result", (), {"status": EvidenceStatus.COMPLETE, "evidence_gaps": []}
            )()

    responses = iter((["initial"], ["penalty"], ["points"]))

    def retrieve(query, **kwargs):
        calls.append(query)
        return next(responses)

    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: SimpleNamespace(
                normalized_query=question,
                intent="CURRENT",
                effective_date=date(2026, 1, 1),
                missing_query_information=[],
            ),
            retriever=retrieve,
            context_expander=lambda candidates, **_: [],
            evidence_gate=Gate(),
        )
    )
    state = graph.invoke({"question": "initial", "max_repair_attempts": 1})
    assert state["repair_attempts"] == 1
    assert len(calls) == 3


def test_out_of_scope_plan_abstains_before_retrieval() -> None:
    calls = []
    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: SimpleNamespace(
                intent="OUT_OF_SCOPE", missing_query_information=[]
            ),
            retriever=lambda query, **_: calls.append(query),
        )
    )
    state = graph.invoke({"question": "tax advice", "max_repair_attempts": 0})
    assert state["final_response"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert calls == []
