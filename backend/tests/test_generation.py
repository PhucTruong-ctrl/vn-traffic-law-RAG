from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.generation.gemini import GeminiStructuredGenerator, StructuredGenerationError
from app.generation.schemas import Claim, ClaimType, StructuredAnswer


def test_schema():
    claim = Claim(claim="c", claim_type=ClaimType.OTHER, provision_ids=["p"])
    answer = StructuredAnswer(answer_summary="s", claims=[claim])
    assert answer.claims[0].claim_type is ClaimType.OTHER
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
            generate_content=lambda **kwargs: calls.append(kwargs)
            or SimpleNamespace(parsed=payload)
        )
    )
    answer = GeminiStructuredGenerator(client).generate("q", "e")
    assert answer.claims[0].provision_ids == ["p"]
    assert calls[0]["model"] == "gemini-3.5-flash"


def test_failure():
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text="bad"))
    )
    with pytest.raises(StructuredGenerationError):
        GeminiStructuredGenerator(client).generate("q", "e")
