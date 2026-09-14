"""Deterministic generator deadline and retry proofs."""

from __future__ import annotations

from langchain_core.documents import Document


def _settings():
    return type(
        "Settings",
        (),
        {
            "openrouter_api_key": "test-key",
            "model": "test-model",
            "openrouter_base_url": "http://provider",
            "timeout_seconds": 18.0,
        },
    )()


def test_provider_timeout_is_not_automatically_retried(monkeypatch) -> None:
    import app.rag.generator as generator

    calls: list[dict[str, object]] = []

    class Completions:
        def create(self, **_kwargs):
            raise TimeoutError("provider deadline")

    class Provider:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(generator, "get_generation_settings", _settings)
    monkeypatch.setattr(generator, "OpenAI", Provider)

    try:
        generator.generate_answer("Vượt đèn đỏ bị phạt thế nào?", [Document("Điều 6")])
    except TimeoutError as exc:
        assert str(exc) == "provider deadline"
    else:
        raise AssertionError("provider timeout must fail closed")

    assert len(calls) == 1
    assert calls[0]["max_retries"] == 0
    assert calls[0]["timeout"] == 18.0


def test_expired_deadline_fails_before_provider_construction(monkeypatch) -> None:
    import app.rag.generator as generator

    constructed = 0

    def provider(**_kwargs):
        nonlocal constructed
        constructed += 1
        raise AssertionError("expired request must not construct provider")

    monkeypatch.setattr(generator, "get_generation_settings", _settings)
    monkeypatch.setattr(generator, "OpenAI", provider)

    try:
        generator.generate_answer(
            "Vượt đèn đỏ bị phạt thế nào?",
            [Document("Điều 6")],
            deadline=10.0,
            clock=lambda: 10.0,
        )
    except TimeoutError as exc:
        assert str(exc) == "request_timeout"
    else:
        raise AssertionError("expired request must fail closed")
    assert constructed == 0


def test_language_cleanup_retry_is_single_conditional_retry(monkeypatch) -> None:
    import app.rag.generator as generator

    class Completions:
        calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            text = (
                "Aceasta este o sancțiune și este pentru test."
                if self.calls == 1
                else "Mức phạt là 2 triệu đồng."
            )
            return type(
                "Response",
                (),
                {
                    "choices": [
                        type("Choice", (), {"message": type("Message", (), {"content": text})()})()
                    ]
                },
            )()

    completions = Completions()

    class Provider:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": completions})()

    monkeypatch.setattr(generator, "get_generation_settings", _settings)
    monkeypatch.setattr(generator, "OpenAI", Provider)
    result = generator.generate_answer(
        "Vượt đèn đỏ bị phạt thế nào?",
        [Document("Điều 6")],
        deadline=20.0,
        clock=lambda: 10.0,
    )
    assert result == "Mức phạt là 2 triệu đồng."
    assert completions.calls == 2


def test_second_mixed_language_response_fails_closed_without_third_call(monkeypatch) -> None:
    import app.rag.generator as generator

    class Completions:
        calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            message = type(
                "Message", (), {"content": "Aceasta este o sancțiune și este pentru test."}
            )()
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    completions = Completions()

    class Provider:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": completions})()

    monkeypatch.setattr(generator, "get_generation_settings", _settings)
    monkeypatch.setattr(generator, "OpenAI", Provider)
    result = generator.generate_answer(
        "Vượt đèn đỏ bị phạt thế nào?",
        [Document("Điều 6")],
        deadline=20.0,
        clock=lambda: 10.0,
    )
    assert result.startswith("Chưa thể tạo câu trả lời tiếng Việt")
    assert completions.calls == 2
