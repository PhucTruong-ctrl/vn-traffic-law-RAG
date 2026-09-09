from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.generation.gemini import GeminiStructuredGenerator, StructuredGenerationError
from app.generation.schemas import Claim, ClaimType, StructuredAnswer
from app.prompts.fallback import GENERATION_INSTRUCTIONS


def test_schema():
    claim = Claim(claim="c", claim_type=ClaimType.OTHER, provision_ids=["p"])
    answer = StructuredAnswer(answer_summary="s", claims=[claim])
    assert answer.claims[0].claim_type is ClaimType.OTHER
    assert (
        Claim(claim="c", claim_type=ClaimType.OTHER, provision_ids=["p"], case_id="case-1").case_id
        == "case-1"
    )
    with pytest.raises(ValidationError):
        Claim(claim="x", claim_type="OTHER", provision_ids=["p"], extra="x")


def test_adapter():
    calls = []
    payload = {
        "answer_summary": "s",
        "claims": [{"claim": "c", "claim_type": "OTHER", "provision_ids": ["p"]}],
    }
    client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: (
                calls.append(kwargs) or SimpleNamespace(parsed=payload)
            )
        )
    )
    answer = GeminiStructuredGenerator(client).generate("q", "e")
    assert answer.claims[0].provision_ids == ["p"]
    assert calls[0]["model"] == "gemini-3.7-flash"
    assert calls[0]["config"].response_json_schema == StructuredAnswer.model_json_schema()
    assert calls[0]["config"].response_schema is None
    assert "Mỗi claim pháp lý phải gắn với đúng provision_id" in calls[0]["contents"]
    assert "without the @vN version suffix" in calls[0]["contents"]
    prompt = calls[0]["contents"]
    assert "tiếng Việt" in prompt and "thân thiện" in prompt
    assert "case identity" in prompt and "should_abstain=true" in prompt
    assert "hỗ trợ điều gì và còn thiếu điều gì" in prompt
    assert "bước tiếp theo nhỏ nhất" in prompt


def test_failure():
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text="bad"))
    )
    with pytest.raises(StructuredGenerationError):
        GeminiStructuredGenerator(client).generate("q", "e")


def test_default_runtime_path_uses_configured_gemini(monkeypatch):
    import google.genai as genai

    import app.config as config

    calls = []
    payload = {
        "answer_summary": "s",
        "claims": [{"claim": "c", "claim_type": "OTHER", "provision_ids": ["p"]}],
    }
    client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: (
                calls.append(kwargs) or SimpleNamespace(parsed=payload)
            )
        )
    )
    monkeypatch.setattr(
        config,
        "get_generation_settings",
        lambda: SimpleNamespace(model="configured-gemini-model", gemini_api_key="test-key"),
    )
    monkeypatch.setattr(genai, "Client", lambda **kwargs: client)

    answer = GeminiStructuredGenerator().generate("q", "e")

    assert answer.answer_summary == "s"
    assert calls[0]["model"] == "configured-gemini-model"


def test_fallback_instructions_preserve_evidence_limits():
    assert "không bịa điều khoản" in GENERATION_INSTRUCTIONS
    assert "tách từng case" in GENERATION_INSTRUCTIONS
    assert "should_abstain=true" in GENERATION_INSTRUCTIONS
