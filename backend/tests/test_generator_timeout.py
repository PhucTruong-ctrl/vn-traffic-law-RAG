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
            "max_retries": 0,
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


def test_long_cited_answer_with_partial_caveat_is_not_refusal() -> None:
    import app.rag.generator as generator

    answer = (
        "Theo Điều 6, người điều khiển phương tiện bị phạt theo mức nêu trong nguồn "
        "[doc-1]. " * 20 + "Chưa đủ thông tin cho phần còn lại."
    )
    assert len(answer) >= 250
    assert not generator.is_refusal_answer(answer)


def test_canonical_refusal_is_detected() -> None:
    import app.rag.generator as generator

    assert generator.is_refusal_answer(generator.CANONICAL_REFUSAL)
