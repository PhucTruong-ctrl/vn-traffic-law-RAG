from app.query.evidence_gate import EvidenceStatus
from app.workflow.graph import GraphServices, build_query_graph


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

    graph = build_query_graph(GraphServices(evidence_gate=IncompleteGate()))
    state = graph.invoke(
        {"question": "mức phạt", "max_repair_attempts": 1, "repair_attempts": 0}
    )
    assert state["repair_attempts"] == 1
    assert state["final_response"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_generate_and_verify_are_non_answering_skeletons() -> None:
    class CompleteGate:
        def evaluate(self, plan, context):
            return type("Gate", (), {"status": EvidenceStatus.COMPLETE, "evidence_gaps": []})()

    graph = build_query_graph(GraphServices(evidence_gate=CompleteGate()))
    state = graph.invoke({"question": "mức phạt", "max_repair_attempts": 0})
    assert state["final_response"]["status"] == "SKELETON"
    assert state["verification_result"]["verified"] is False
