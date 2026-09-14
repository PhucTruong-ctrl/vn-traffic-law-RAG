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

    class Provider:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def invoke(self, _prompt):
            raise TimeoutError("provider deadline")

    monkeypatch.setattr(generator, "get_generation_settings", _settings)
    monkeypatch.setattr("langchain_openrouter.ChatOpenRouter", Provider)

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
    monkeypatch.setattr("langchain_openrouter.ChatOpenRouter", provider)

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
        raise AssertionError("expired deadline must fail closed")
    assert constructed == 0


def test_language_cleanup_retry_is_single_conditional_retry(monkeypatch) -> None:
    import app.rag.generator as generator

    class Provider:
        calls = 0

        def __init__(self, **_kwargs):
            pass

        def invoke(self, _prompt):
            self.calls += 1
            text = (
                "Aceasta este o sancțiune și este pentru test."
                if self.calls == 1
                else "Mức phạt là 2 triệu đồng."
            )
            return type("Response", (), {"content": text})()

    provider = Provider()
    monkeypatch.setattr(generator, "get_generation_settings", _settings)

    def make_provider(**kwargs):
        calls.append(kwargs)
        return provider

    calls: list[dict[str, object]] = []
    monkeypatch.setattr("langchain_openrouter.ChatOpenRouter", make_provider)

    result = generator.generate_answer(
        "Vượt đèn đỏ bị phạt thế nào?",
        [Document("Điều 6")],
        deadline=20.0,
        clock=lambda: 10.0,
    )

    assert len(calls) == 2
    assert calls[0]["max_retries"] == 0
    assert calls[1]["max_retries"] == 0
    assert result == "Mức phạt là 2 triệu đồng."
    assert provider.calls == 2


def test_second_mixed_language_response_fails_closed_without_third_call(monkeypatch) -> None:
    import app.rag.generator as generator

    class Provider:
        calls = 0

        def __init__(self, **_kwargs):
            pass

        def invoke(self, _prompt):
            self.calls += 1
            return type(
                "Response", (), {"content": "Aceasta este o sancțiune și este pentru test."}
            )()

    provider = Provider()
    monkeypatch.setattr(generator, "get_generation_settings", _settings)
    monkeypatch.setattr("langchain_openrouter.ChatOpenRouter", lambda **_kwargs: provider)

    result = generator.generate_answer(
        "Vượt đèn đỏ bị phạt thế nào?",
        [Document("Điều 6")],
        deadline=20.0,
        clock=lambda: 10.0,
    )

    assert result.startswith("Chưa thể tạo câu trả lời tiếng Việt")
    assert provider.calls == 2
