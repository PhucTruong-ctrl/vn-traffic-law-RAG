from collections.abc import Sequence
from datetime import date
from types import SimpleNamespace

from app.query.evidence_gate import EvidenceGateResult, EvidenceStatus
from app.query.query_understanding_types import EvidenceType
from app.retrieval.comparison import ComparisonResult
from app.retrieval.contracts import CandidateSet, RetrievalResult
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

def test_incomplete_evidence_uses_configured_default_repair_bound() -> None:
    class IncompleteGate:
        def evaluate(self, plan, context):
            return type("Gate", (), {"status": EvidenceStatus.INCOMPLETE, "evidence_gaps": []})()

    graph = build_query_graph(services(evidence_gate=IncompleteGate()))
    state = graph.invoke({"question": "mức phạt"})

    assert state["repair_attempts"] == 3
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


def test_retrieval_uses_expansion_variants() -> None:
    calls = []
    plan = SimpleNamespace(
        normalized_query="normalized",
        intent="CURRENT",
        effective_date=date(2025, 1, 1),
        missing_query_information=[],
    )
    complete_gate = type(
        "CompleteGate",
        (),
        {
            "evaluate": lambda self, plan, context: type(
                "Result",
                (),
                {"status": EvidenceStatus.COMPLETE, "evidence_gaps": []},
            )()
        },
    )()
    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: plan,
            expander=lambda plan, **_: [
                SimpleNamespace(text="original"),
                SimpleNamespace(text="rewrite"),
            ],
            retriever=lambda query, **kwargs: calls.append(
                (query, kwargs["query_date"])
            )
            or [query],
            evidence_gate=complete_gate,
        )
    )
    graph.invoke({"question": "question", "max_repair_attempts": 0})
    assert calls == [("original", date(2025, 1, 1)), ("rewrite", date(2025, 1, 1))]

def test_hyde_variant_uses_dense_path_without_exact_or_sparse_retrieval() -> None:
    calls = []
    plan = SimpleNamespace(
        normalized_query="normalized",
        intent="CURRENT",
        effective_date=date(2025, 1, 1),
        missing_query_information=[],
    )
    complete_gate = type(
        "CompleteGate",
        (),
        {
            "evaluate": lambda self, plan, context: type(
                "Result",
                (),
                {"status": EvidenceStatus.COMPLETE, "evidence_gaps": []},
            )()
        },
    )()

    def general_retrieval(query, **kwargs):
        calls.append(("general", query))
        return [query]

    def dense_retrieval(query, **kwargs):
        calls.append(("dense", query, kwargs["query_date"]))
        return [query]

    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: plan,
            expander=lambda plan, **_: [
                SimpleNamespace(text="original", source="original"),
                SimpleNamespace(text="synthetic answer", source="hyde"),
            ],
            retriever=general_retrieval,
            dense_retriever=dense_retrieval,
            evidence_gate=complete_gate,
        )
    )

    graph.invoke({"question": "question", "max_repair_attempts": 0})
    assert calls == [
        ("general", "original"),
        ("dense", "synthetic answer", date(2025, 1, 1)),
    ]

def test_comparison_retrieval_keeps_independent_before_and_after() -> None:
    calls = []
    plan = SimpleNamespace(
        normalized_query="normalized",
        intent="COMPARISON",
        comparison_from=date(2023, 1, 1),
        comparison_to=date(2025, 1, 1),
        missing_query_information=[],
    )

    def retrieve(query, **kwargs):
        calls.append((query, kwargs["query_date"]))
        return [f"{query}:{kwargs['query_date']}"]
    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: plan,
            expander=lambda plan, **_: [SimpleNamespace(text="variant")],
            retriever=retrieve,
            evidence_gate=type(
                "CompleteGate",
                (),
                {
                    "evaluate": lambda self, plan, context: type(
                        "Result",
                        (),
                        {"status": EvidenceStatus.COMPLETE, "evidence_gaps": []},
                    )()
                },
            )(),
        )
    )
    state = graph.invoke({"question": "compare", "max_repair_attempts": 0})
    assert calls == [
        ("variant", date(2023, 1, 1)),
        ("variant", date(2025, 1, 1)),
    ]
    assert state["recall_candidates"] == {
        "before": ["variant:2023-01-01"],
        "after": ["variant:2025-01-01"],
    }


def test_normalizes_candidate_set_before_rerank_and_context_expansion() -> None:
    plan = SimpleNamespace(
        normalized_query="question",
        intent="CURRENT",
        effective_date=date(2025, 1, 1),
        missing_query_information=[],
    )
    candidate_set = CandidateSet(query="question", results=[], applied_date=plan.effective_date)
    seen: dict[str, object] = {}

    class CompleteGate:
        def evaluate(self, plan, context: Sequence[RetrievalResult]) -> EvidenceGateResult:
            assert isinstance(context, list)
            return EvidenceGateResult(
                status=EvidenceStatus.COMPLETE,
                evidence_gaps=[],
                covered_provisions=[],
            )

    def rerank(question, candidates):
        seen["rerank"] = candidates
        return candidates

    def expand(candidates, **_):
        seen["expand"] = candidates
        return []

    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: plan,
            retriever=lambda query, **_: candidate_set,
            fusion=lambda candidates: candidates,
            reranker=rerank,
            context_expander=expand,
            evidence_gate=CompleteGate(),
        )
    )
    state = graph.invoke({"question": "question", "max_repair_attempts": 0})

    assert seen == {"rerank": [], "expand": []}
    assert state["reranked"] == []
    assert state["expanded_context"] == []


def test_comparison_sides_stay_separate_through_downstream_nodes() -> None:
    before_date, after_date = date(2023, 1, 1), date(2025, 1, 1)
    plan = SimpleNamespace(
        normalized_query="compare",
        intent="COMPARISON",
        comparison_from=before_date,
        comparison_to=after_date,
        missing_query_information=[],
    )
    seen: dict[str, list[str]] = {"fusion": [], "rerank": [], "expand": [], "gate": []}

    def compare(plan, *, date_from, date_to):
        return ComparisonResult(
            before=CandidateSet(query="before", results=[], applied_date=date_from),
            after=CandidateSet(query="after", results=[], applied_date=date_to),
        )

    def fusion(candidates):
        assert isinstance(candidates, CandidateSet)
        seen["fusion"].append(candidates.query)
        return candidates

    def rerank(question, candidates):
        assert isinstance(candidates, list)
        seen["rerank"].append(candidates)
        return candidates

    def expand(candidates, *, query_date):
        assert isinstance(candidates, list)
        seen["expand"].append(f"{query_date}")
        return []

    class CompleteGate:
        def evaluate(
            self, plan, context: Sequence[RetrievalResult]
        ) -> EvidenceGateResult:
            assert isinstance(context, list)
            seen["gate"].append("before" if len(seen["gate"]) == 0 else "after")
            return EvidenceGateResult(
                status=EvidenceStatus.COMPLETE,
                evidence_gaps=[],
                covered_provisions=[],
            )

    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: plan,
            expander=lambda plan, **_: [SimpleNamespace(text="compare")],
            comparison=compare,
            fusion=fusion,
            reranker=rerank,
            context_expander=expand,
            evidence_gate=CompleteGate(),
            context_builder=lambda candidates: candidates,
        )
    )
    state = graph.invoke({"question": "compare", "max_repair_attempts": 0})

    assert seen["fusion"] == ["before", "after"]
    assert seen["rerank"] == [[], []]
    assert seen["expand"] == [
        f"{before_date}",
        f"{after_date}",
    ]
    assert seen["gate"] == ["before", "after"]
    assert state["expanded_context"] == {"before": [], "after": []}
    assert state["context_package"] == {"before": [], "after": []}


def test_context_expansion_uses_resolved_plan_date() -> None:
    seen = []
    plan = SimpleNamespace(
        normalized_query="question",
        intent="HISTORICAL",
        effective_date=date(2022, 6, 1),
        missing_query_information=[],
    )
    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: plan,
            context_expander=lambda candidates, **kwargs: seen.append(
                kwargs["query_date"]
            )
            or [],
            evidence_gate=type(
                "CompleteGate",
                (),
                {
                    "evaluate": lambda self, plan, context: type(
                        "Result",
                        (),
                        {"status": EvidenceStatus.COMPLETE, "evidence_gaps": []},
                    )()
                },
            )(),
        )
    )
    graph.invoke({"question": "historical", "max_repair_attempts": 0})
    assert seen == [date(2022, 6, 1)]


def test_comparison_without_both_dates_abstains() -> None:
    calls = []
    plan = SimpleNamespace(
        normalized_query="question",
        intent="COMPARISON",
        comparison_from=date(2023, 1, 1),
        comparison_to=None,
        missing_query_information=[],
    )
    graph = build_query_graph(
        services(
            analyzer=lambda question, **_: plan,
            retriever=lambda query, **_: calls.append(query),
        )
    )
    state = graph.invoke({"question": "ambiguous comparison", "max_repair_attempts": 0})
    assert state["final_response"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert calls == []
