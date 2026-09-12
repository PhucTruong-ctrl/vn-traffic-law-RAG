from __future__ import annotations

from langchain_core.documents import Document

from app.rag.analyzer import analyze_question, resolve_vehicle_followup
from app.rag.generator import build_prompt
from app.rag.service import RAGService


def test_generator_prompt_addresses_legal_audience_without_internal_fallback_terms() -> None:
    prompt = build_prompt("Vượt đèn đỏ bị phạt thế nào?", [Document("Điều 6")])
    system, human = prompt

    assert "trả lời tự nhiên" in system[1]
    assert "CONTEXT" in system[1]
    assert "cơ chế bằng chứng nội bộ" in system[1]
    assert "CONTEXT" not in human[1]


def test_generator_mixed_output_retries_once(monkeypatch) -> None:
    import app.rag.generator as generator

    class Model:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        def invoke(self, prompt):
            self.calls += 1
            return type(
                "Response",
                (),
                {
                    "content": "Aceasta este o sancțiune și este pentru test."
                    if self.calls == 1
                    else "Mức phạt là 2 triệu đồng."
                },
            )()

    model = Model()
    constructor_kwargs = {}
    monkeypatch.setattr(
        generator,
        "get_generation_settings",
        lambda: type(
            "S", (), {"openrouter_api_key": "x", "model": "m", "openrouter_base_url": "u"}
        )(),
    )

    def fake_chat_openrouter(**kwargs):
        constructor_kwargs.update(kwargs)
        return model

    monkeypatch.setattr("langchain_openrouter.ChatOpenRouter", fake_chat_openrouter)
    assert (
        generator.generate_answer("Vượt đèn đỏ?", [Document("Điều 6")])
        == "Mức phạt là 2 triệu đồng."
    )
    assert model.calls == 2
    assert constructor_kwargs["timeout"] == 120_000
    assert constructor_kwargs["max_retries"] == 0


def test_generator_clean_vietnamese_does_not_retry(monkeypatch) -> None:
    import app.rag.generator as generator

    class Model:
        calls = 0

        def invoke(self, prompt):
            self.calls += 1
            return type(
                "Response", (), {"content": "Người điều khiển phải chấp hành tín hiệu đèn."}
            )()

    model = Model()
    monkeypatch.setattr(
        generator,
        "get_generation_settings",
        lambda: type(
            "S", (), {"openrouter_api_key": "x", "model": "m", "openrouter_base_url": "u"}
        )(),
    )
    monkeypatch.setattr("langchain_openrouter.ChatOpenRouter", lambda **kwargs: model)
    assert generator.generate_answer("Vượt đèn đỏ?", [Document("Điều 6")])
    assert model.calls == 1


def test_generator_two_mixed_outputs_return_vietnamese_fallback(monkeypatch) -> None:
    import app.rag.generator as generator

    class Model:
        def invoke(self, prompt):
            return type(
                "Response", (), {"content": "Aceasta este o sancțiune și este pentru test."}
            )()

    monkeypatch.setattr(
        generator,
        "get_generation_settings",
        lambda: type(
            "S", (), {"openrouter_api_key": "x", "model": "m", "openrouter_base_url": "u"}
        )(),
    )
    monkeypatch.setattr("langchain_openrouter.ChatOpenRouter", lambda **kwargs: Model())
    result = generator.generate_answer("Vượt đèn đỏ?", [Document("Điều 6")])
    assert result.startswith("Chưa thể tạo câu trả lời tiếng Việt")


class FakeRetriever:
    def __init__(self, responses: dict[str, list[Document]] | None = None) -> None:
        self.responses = responses or {}
        self.queries: list[str] = []

    def retrieve(self, query: str, **_: object) -> list[Document]:
        self.queries.append(query)
        return list(self.responses.get(query, []))


def test_retrieve_query_fanout_is_bounded_and_preserves_vehicle_scopes() -> None:
    cases = [
        (
            "Vượt đèn đỏ bị phạt thế nào?",
            3,
            ("vượt đèn đỏ",),
            ("ô tô", "xe mô tô, xe gắn máy", "xe thô sơ"),
        ),
        (
            "Xe máy và ô tô vượt đèn đỏ bị phạt thế nào?",
            2,
            ("vượt đèn đỏ",),
            ("ô tô", "xe mô tô, xe gắn máy"),
        ),
        (
            "Xe máy vượt đèn đỏ?",
            1,
            ("xe máy", "vượt đèn đỏ"),
            (),
        ),
        (
            "Vượt đèn đỏ và ko đội mũ bảo hiểm",
            2,
            ("vượt đèn đỏ", "không đội mũ bảo hiểm"),
            (),
        ),
    ]

    for question, expected_count, expected_tokens, expected_suffixes in cases:
        retriever = FakeRetriever()
        RAGService(retriever).retrieve(question)
        assert len(retriever.queries) == expected_count
        assert all(
            any(token in query.casefold() for query in retriever.queries)
            for token in expected_tokens
        )
        if expected_suffixes:
            assert sorted(
                query.casefold().rsplit(" đối với ", maxsplit=1)[-1] for query in retriever.queries
            ) == sorted(expected_suffixes)
        else:
            assert all(" đối với " not in query.casefold() for query in retriever.queries)
        assert len(retriever.queries) <= 12


def test_answer_analyzes_question_once(monkeypatch) -> None:
    import app.rag.service as service

    calls = 0
    original = service.analyze_question

    def counting_analysis(question: str):
        nonlocal calls
        calls += 1
        return original(question)

    monkeypatch.setattr(service, "analyze_question", counting_analysis)
    monkeypatch.setattr(service, "generate_answer", lambda *args, **kwargs: "Có căn cứ")
    evidence = Document(
        "Điều khoản",
        metadata={"chunk_id": "a", "document_id": "law-1"},
    )

    result = RAGService(FakeRetriever()).answer("Xe máy vượt đèn đỏ?", chunks=[evidence])

    assert result["status"] == "insufficient_evidence"
    assert calls == 1


def test_speed_limit_road_traffic_questions_are_legal_but_general_questions_are_not() -> None:
    assert (
        analyze_question("Tốc độ tối đa trong khu vực đông dân cư là bao nhiêu km/h?")
        .intents[0]
        .kind
        == "legal"
    )
    assert analyze_question("Thời tiết hôm nay thế nào?").intents[0].kind == "out_of_scope"


def test_red_light_and_no_helmet_decompose_into_both_violations() -> None:
    analysis = analyze_question("Khi vượt đèn đỏ và ko đội mũ bảo hiểm")

    texts = [intent.text.casefold() for intent in analysis.intents]
    assert len(texts) == 2
    assert any("vượt đèn đỏ" in text for text in texts)
    assert any("không đội mũ bảo hiểm" in text for text in texts)


def test_short_car_followup_rewrites_against_latest_legal_turn() -> None:
    history = [
        {"role": "user", "content": "Xe máy vượt đèn đỏ thì mức phạt bao nhiêu?"},
        {"role": "assistant", "content": "Theo quy định hiện hành..."},
    ]

    assert resolve_vehicle_followup("Còn ô tô?", history) == (
        "Mức phạt đối với ô tô vượt đèn đỏ bao nhiêu?"
    )


def test_motorcycle_followup_is_standalone_without_history_prefix_or_duplicate_copula() -> None:
    history = [{"role": "user", "content": "Vượt đèn đỏ thì mức phạt bao nhiêu?"}]

    resolved = resolve_vehicle_followup("Vậy còn đối với xe máy?", history)

    assert "xe mô tô" in resolved
    assert "vượt đèn đỏ" in resolved
    assert "user:" not in resolved
    assert "Current question" not in resolved
    assert "là là" not in resolved


def test_vehicle_followup_uses_at_most_six_history_messages() -> None:
    history = [{"role": "user", "content": "Xe máy vượt đèn đỏ thì mức phạt bao nhiêu?"}] + [
        {"role": "assistant", "content": f"older-{index}"} for index in range(6)
    ]

    assert resolve_vehicle_followup("Còn ô tô?", history) == "Còn ô tô?"


def test_penalty_dimensions_are_bounded_and_keep_violation_context() -> None:
    question = (
        "Vượt đèn đỏ thì mức phạt, trừ điểm GPLX, tước quyền sử dụng GPLX "
        "và xử lý phương tiện thế nào?"
    )

    intents = analyze_question(question).intents

    assert len(intents) == 4
    assert all("vượt đèn đỏ" in intent.text.casefold() for intent in intents)
    assert [intent.text.rsplit("; ", 1)[-1] for intent in intents] == [
        "mức phạt",
        "trừ điểm GPLX",
        "tước quyền sử dụng",
        "xử lý/tạm giữ phương tiện",
    ]


def test_retrieve_uses_rrf_and_diversity_cap_with_deterministic_ties() -> None:
    shared = Document(
        "shared", metadata={"chunk_id": "shared", "document_id": "law", "article": 1, "clause": 1}
    )
    distractor = Document(
        "distractor", metadata={"chunk_id": "d", "document_id": "law", "article": 1, "clause": 2}
    )
    fourth = Document(
        "fourth", metadata={"chunk_id": "fourth", "document_id": "law", "article": 1, "clause": 3}
    )
    distinct_clause = Document(
        "distinct",
        metadata={"chunk_id": "distinct", "document_id": "law", "article": 1, "clause": 4},
    )
    retriever = FakeRetriever(
        {
            "vượt đèn đỏ": [shared, distractor, fourth, distinct_clause],
            "không đội mũ bảo hiểm": [shared, distractor, fourth],
        }
    )

    documents = RAGService(retriever).retrieve("Khi vượt đèn đỏ và ko đội mũ bảo hiểm")

    assert [document.page_content for document in documents] == [
        "shared",
        "distractor",
        "fourth",
        "distinct",
    ]
    assert [document.metadata["chunk_id"] for document in documents] == [
        "shared",
        "d",
        "fourth",
        "distinct",
    ]
    assert len(documents) == 4
    assert [document.metadata["intent"] for document in documents] == [
        ["không đội mũ bảo hiểm", "vượt đèn đỏ"],
        ["không đội mũ bảo hiểm", "vượt đèn đỏ"],
        ["không đội mũ bảo hiểm", "vượt đèn đỏ"],
        ["vượt đèn đỏ"],
    ]


def test_retrieve_deduplicates_documents_in_first_seen_order() -> None:
    first = Document("first", metadata={"chunk_id": "a"})
    duplicate = Document("first", metadata={"chunk_id": "a"})
    second = Document("second", metadata={"chunk_id": "b"})
    retriever = FakeRetriever(
        {
            "vượt đèn đỏ": [first, duplicate],
            "không đội mũ bảo hiểm": [duplicate, second],
        }
    )

    documents = RAGService(retriever).retrieve("Khi vượt đèn đỏ và ko đội mũ bảo hiểm")

    assert [document.page_content for document in documents] == ["first", "second"]
    assert [document.metadata["chunk_id"] for document in documents] == ["a", "b"]
    assert retriever.queries == ["vượt đèn đỏ", "không đội mũ bảo hiểm"]
    assert [document.metadata["intent"] for document in documents] == [
        ["không đội mũ bảo hiểm", "vượt đèn đỏ"],
        ["không đội mũ bảo hiểm"],
    ]


def test_retrieve_fallback_identity_deduplicates_same_source_and_content() -> None:
    first = Document("same", metadata={"source_file": "law.pdf", "page": 1})
    duplicate = Document("same", metadata={"source": "law.pdf", "page": 2})
    retriever = FakeRetriever(
        {
            "vượt đèn đỏ": [first],
            "không đội mũ bảo hiểm": [duplicate],
        }
    )

    documents = RAGService(retriever).retrieve("Khi vượt đèn đỏ và ko đội mũ bảo hiểm")

    assert [document.page_content for document in documents] == ["same"]
    assert [document.metadata.get("chunk_id") for document in documents] == [None]
    assert [document.metadata["intent"] for document in documents] == [
        ["không đội mũ bảo hiểm", "vượt đèn đỏ"],
    ]


def test_retrieve_keeps_distinct_chunk_ids_with_same_content() -> None:
    first = Document("same", metadata={"chunk_id": "a", "source_file": "law.pdf"})
    second = Document("same", metadata={"chunk_id": "b", "source_file": "law.pdf"})
    retriever = FakeRetriever(
        {
            "vượt đèn đỏ": [first],
            "không đội mũ bảo hiểm": [second],
        }
    )

    documents = RAGService(retriever).retrieve("Khi vượt đèn đỏ và ko đội mũ bảo hiểm")

    assert [document.page_content for document in documents] == ["same", "same"]
    assert [document.metadata["chunk_id"] for document in documents] == ["a", "b"]
    assert [document.metadata["intent"] for document in documents] == [
        ["vượt đèn đỏ"],
        ["không đội mũ bảo hiểm"],
    ]


def test_answer_generates_with_partial_evidence_and_abstains_when_empty(
    monkeypatch,
) -> None:
    question = "Khi xe máy vượt đèn đỏ?"
    evidence = Document(
        "Điều khoản về vượt đèn đỏ",
        metadata={"chunk_id": "a", "document_id": "law-1"},
    )
    partial = RAGService(FakeRetriever()).answer(question, chunks=[evidence])
    empty = RAGService(FakeRetriever()).answer(question, chunks=[])

    assert partial["status"] == "insufficient_evidence"
    assert partial["citations"] == []
    assert empty["status"] == "insufficient_evidence"
    assert empty["citations"] == []
