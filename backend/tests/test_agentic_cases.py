from datetime import date
from types import SimpleNamespace

from app.query.evidence_gate import EvidenceCompletenessGate, EvidenceStatus
from app.query.query_understanding import QueryAnalyzer
from app.query.query_understanding_types import EvidenceType
from app.retrieval.comparison import ComparisonResult
from app.retrieval.contracts import CandidateSet, RetrievalResult
from app.workflow import graph as workflow_graph
from app.workflow.graph import GraphServices, build_query_graph

TODAY = date(2026, 9, 9)


def _record(provision_id: str, text: str, *, vehicle: str | None = None):
    return SimpleNamespace(
        provision_id=provision_id,
        text=f"{vehicle or ''} {text}".strip(),
        source_text="",
        parent_context=None,
        review_status="ACCEPTED",
    )


def _retrieval_result(provision_id: str, text: str) -> RetrievalResult:
    return RetrievalResult(
        rank=1,
        provision_id=provision_id,
        provision_version=1,
        document_id="doc-1",
        document_version_id="doc-version-1",
        text=text,
        source_text=text,
        parent_context=None,
        document_number="1/2026",
        document_type="DECREE",
        article=None,
        clause=None,
        point=None,
        effective_from=date(2020, 1, 1),
        effective_to=None,
        page_number=1,
        bbox=None,
        retrieval_sources=["test"],
        fused_score=None,
        added_by=None,
        source_id=None,
        depth=0,
    )


def _plan(question: str):
    return QueryAnalyzer().analyze(question, current_date=TODAY)


def _services(**overrides):
    values = dict(
        temporal=lambda plan, **_: TODAY,
        expander=lambda plan, **_: [],
        fusion=lambda candidates: candidates,
        reranker=lambda question, candidates: candidates,
        context_expander=lambda candidates, **_: [],
        context_builder=lambda context: context,
    )
    values.update(overrides)
    return GraphServices(**values)


def test_coordinated_vehicle_cases_fan_out_and_keep_citations_isolated():
    plan = _plan("xe máy và ô tô vượt đèn đỏ phạt sao?")
    calls: list[tuple[str, str | None]] = []

    def retrieve(query, *, vehicle_type=None, **_):
        calls.append((query, vehicle_type))
        return [
            _record(
                f"{vehicle_type}-provision",
                "Hành vi vượt đèn đỏ bị phạt 10 đồng.",
                vehicle=vehicle_type,
            )
        ]

    state = build_query_graph(
        _services(
            analyzer=lambda question, **_: plan,
            retriever=retrieve,
            evidence_gate=type(
                "CompleteGate",
                (),
                {
                    "evaluate": lambda self, plan, context: SimpleNamespace(
                        status=EvidenceStatus.COMPLETE, evidence_gaps=[]
                    )
                },
            )(),
            generator=lambda question, context: {
                "answer_summary": "ok",
                "claims": [
                    {
                        "claim": "xe",
                        "claim_type": "OTHER",
                        "provision_ids": ["xe máy-provision"],
                        "case_id": "case-1",
                    },
                    {
                        "claim": "oto",
                        "claim_type": "OTHER",
                        "provision_ids": ["ô tô-provision"],
                        "case_id": "case-2",
                    },
                ],
            },
            legal_verifier=type(
                "V", (), {"verify": lambda self, *args, **kwargs: SimpleNamespace(passed=True)}
            )(),
            temporal_verifier=type(
                "T", (), {"verify": lambda self, *args, **kwargs: SimpleNamespace(verified=True)}
            )(),
        )
    ).invoke({"question": "xe máy và ô tô vượt đèn đỏ phạt sao?", "max_repair_attempts": 0})
    assert {vehicle for _, vehicle in calls} == {"xe máy", "ô tô"}
    claims = state["final_response"]["claims"]
    assert {claim["case_id"]: claim["provision_ids"] for claim in claims} == {
        "case-1": ["xe máy-provision"],
        "case-2": ["ô tô-provision"],
    }


def test_actor_and_vehicle_alternatives_create_independent_case_queries():
    plan = _plan("người lái xe máy hoặc ô tô vi phạm thì phạt thế nào?")
    assert len(plan.cases) >= 2
    assert {case.vehicle_type for case in plan.cases} >= {"xe máy", "ô tô"}
    assert all(case.query_text for case in plan.cases)


def test_multiple_requested_violations_require_evidence_for_all_types():
    plan = _plan("vượt đèn đỏ và đi sai làn phạt bao nhiêu?")
    assert EvidenceType.VIOLATION_DEFINITION in plan.required_evidence
    assert EvidenceType.MONETARY_PENALTY in plan.required_evidence
    result = EvidenceCompletenessGate().evaluate(
        plan, [_record("p", "Hành vi vượt đèn đỏ bị phạt 10 đồng.")]
    )
    assert result.status is EvidenceStatus.INCOMPLETE
    assert EvidenceType.VIOLATION_DEFINITION in result.evidence_gaps


def test_distinct_sanctions_remain_distinct_claims_and_provisions():
    plan = _plan("xe máy và ô tô vượt đèn đỏ phạt sao?")
    context = {
        "case-1": [_record("sanction-a", "Người điều khiển xe máy vượt đèn đỏ bị phạt 10 đồng.")],
        "case-2": [_record("sanction-b", "Người điều khiển ô tô vượt đèn đỏ bị phạt 20 đồng.")],
    }
    results = {
        key: EvidenceCompletenessGate().evaluate(
            plan.model_copy(update={"cases": [case for case in plan.cases if case.case_id == key]}),
            value,
        )
        for key, value in context.items()
    }
    assert {
        case_id: result.case_results[0].candidate_provisions for case_id, result in results.items()
    } == {"case-1": ["sanction-a"], "case-2": ["sanction-b"]}


def test_temporal_comparison_keeps_before_and_after_evidence_isolated():
    before, after = (
        CandidateSet(
            query="q",
            results=[_retrieval_result("before", "before")],
            applied_date=date(2020, 1, 1),
        ),
        CandidateSet(
            query="q", results=[_retrieval_result("after", "after")], applied_date=date(2026, 1, 1)
        ),
    )
    value = ComparisonResult(before=before, after=after)
    seen: list[list[str]] = []
    mapped = workflow_graph._map_comparison(
        value, lambda side: seen.append([item.provision_id for item in side.results]) or side
    )
    assert seen == [["before"], ["after"]]
    assert mapped.before.results[0].provision_id != mapped.after.results[0].provision_id


def test_ambiguity_and_negation_are_explicit_limitations():
    plan = _plan("xe máy, không rõ có bị phạt không")
    result = EvidenceCompletenessGate().evaluate(
        plan, [_record("p", "Hành vi vi phạm bị phạt 10 đồng.", vehicle="xe máy")]
    )
    assert result.status is EvidenceStatus.INCOMPLETE
    assert result.case_results[0].gap_reasons


def test_partial_evidence_never_reports_complete():
    plan = _plan("phạt bao nhiêu và bị trừ bao nhiêu điểm?")
    result = EvidenceCompletenessGate().evaluate(
        plan, [_record("p", "Hành vi vi phạm bị phạt 10 đồng.")]
    )
    assert result.status is EvidenceStatus.INCOMPLETE
    assert EvidenceType.LICENSE_POINTS in result.evidence_gaps


def test_single_case_query_retains_legacy_query_shape():
    plan = _plan("xe máy vượt đèn đỏ phạt sao?")
    assert len(plan.cases) == 1
    assert plan.case_queries == [plan.normalized_query]
    assert plan.cases[0].case_id == "case-1"
