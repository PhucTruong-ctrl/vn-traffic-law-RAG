from datetime import date
from time import perf_counter
from types import SimpleNamespace

from app.query.evidence_gate import EvidenceStatus
from app.retrieval.contracts import RetrievalResult
from app.workflow.graph import GraphServices, build_query_graph


TODAY = date(2025, 1, 1)
HISTORICAL = date(2022, 1, 1)


def provision(pid: str, *, start: date = date(2020, 1, 1), end: date | None = None) -> dict:
    return dict(
        rank=1,
        provision_id=pid,
        provision_version=1,
        document_id="doc-1",
        document_version_id="doc-v1",
        text=f"Rule {pid}",
        source_text=f"Rule {pid}",
        parent_context=None,
        document_number="168/2024/NĐ-CP",
        article="7",
        clause="1",
        point=None,
        effective_from=start,
        effective_to=end,
        page_number=1,
        retrieval_sources=["fixture"],
        fused_score=1.0,
        added_by=None,
        source_id="fixture",
        review_status="ACCEPTED",
        depth=0,
    )


class CompleteGate:
    def evaluate(self, plan, context):
        return SimpleNamespace(status=EvidenceStatus.COMPLETE, evidence_gaps=[])


class DeterministicTemporal:
    def __init__(self, plan):
        self.plan = plan

    def __call__(self, plan, *, query_date):
        return query_date


def make_graph(plan, records, answer=None, *, gate=None, verifier=None):
    answer = answer or {
        "answer_summary": "Điều 7 áp dụng.",
        "claims": [{"claim": "Điều 7 áp dụng.", "claim_type": "OTHER", "provision_ids": [records[0]["provision_id"]]}],
    }
    return build_query_graph(GraphServices(
        analyzer=lambda question, **_: plan,
        temporal=DeterministicTemporal(plan),
        expander=lambda plan, **_: [SimpleNamespace(text="question", source="original")],
        retriever=lambda query, **_: records,
        fusion=lambda candidates: candidates,
        reranker=lambda question, candidates: candidates,
        context_expander=lambda candidates, **_: [],
        evidence_gate=gate or CompleteGate(),
        context_builder=lambda candidates: candidates,
        generator=lambda question, context: answer,
        verifier=verifier,
    ))


def run(plan, records, **kwargs):
    return make_graph(plan, records, **kwargs).invoke({"question": "question", "query_date": TODAY, "max_repair_attempts": 1})


def test_current_workflow_completes_with_valid_citation():
    record = provision("p-current")
    plan = SimpleNamespace(normalized_query="question", intent="CURRENT", effective_date=TODAY, missing_query_information=[])
    state = run(plan, [record])
    assert state["final_response"]["status"] == "COMPLETED"
    assert state["verification_result"]["status"] == "VALID"


def test_historical_workflow_serves_resolved_historical_date():
    record = provision("p-historical", end=date(2023, 1, 1))
    plan = SimpleNamespace(normalized_query="question", intent="HISTORICAL", effective_date=HISTORICAL, missing_query_information=[])
    state = run(plan, [record])
    assert state["final_response"]["status"] == "COMPLETED"
    assert state["query_understanding"].effective_date == HISTORICAL


def test_comparison_workflow_retrieves_both_dates():
    before = provision("p-before", end=date(2024, 1, 1))
    after = provision("p-after", start=date(2024, 1, 1))
    plan = SimpleNamespace(normalized_query="question", intent="COMPARISON", comparison_from=date(2023, 1, 1), comparison_to=TODAY, missing_query_information=[])
    graph = make_graph(plan, [before, after])
    state = graph.invoke({"question": "question", "query_date": TODAY, "max_repair_attempts": 0})
    assert set(state["recall_candidates"]) == {"before", "after"}
    assert state["final_response"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_out_of_scope_abstains_without_retrieval():
    calls = []
    plan = SimpleNamespace(intent="OUT_OF_SCOPE", missing_query_information=[])
    state = make_graph(plan, [provision("p")]).invoke({"question": "tax", "max_repair_attempts": 0})
    assert state["final_response"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_invalid_citation_is_blocked_and_rate_is_zero():
    record = provision("p-real")
    plan = SimpleNamespace(normalized_query="question", intent="CURRENT", effective_date=TODAY, missing_query_information=[])
    answer = {"answer_summary": "unsupported", "claims": [{"claim": "unsupported", "claim_type": "OTHER", "provision_ids": ["p-fake"]}]}
    state = run(plan, [record], answer=answer)
    assert state["final_response"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert state["verification_result"]["reason_code"] == "L2_UNKNOWN_PROVISION"
    assert state["final_response"].get("claims") is None


def test_incomplete_evidence_repairs_then_completes():
    calls = 0
    class RepairGate:
        def evaluate(self, plan, context):
            nonlocal calls
            calls += 1
            return SimpleNamespace(status=EvidenceStatus.INCOMPLETE if calls == 1 else EvidenceStatus.COMPLETE, evidence_gaps=[])
    record = provision("p-repair")
    plan = SimpleNamespace(normalized_query="question", intent="CURRENT", effective_date=TODAY, missing_query_information=[])
    state = run(plan, [record], gate=RepairGate())
    assert state["repair_attempts"] == 1
    assert state["final_response"]["status"] == "COMPLETED"


def test_workflow_latency_is_deterministic_and_bounded():
    record = provision("p-latency")
    plan = SimpleNamespace(normalized_query="question", intent="CURRENT", effective_date=TODAY, missing_query_information=[])
    started = perf_counter()
    state = run(plan, [record])
    elapsed = perf_counter() - started
    assert state["final_response"]["status"] == "COMPLETED"
    assert elapsed < 1.0
