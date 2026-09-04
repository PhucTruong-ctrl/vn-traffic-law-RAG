"""Gemini structured-output adapter for legal answers."""

from __future__ import annotations

from typing import Any, Protocol, cast

from .schemas import StructuredAnswer

MODEL_VERSION = "gemini-3.5-flash"
PROMPT_NAME = "legal-generator-v1"
PROMPT_VERSION = "1"


class _Models(Protocol):
    def generate_content(self, **kwargs: Any) -> Any: ...


class _Client(Protocol):
    models: _Models


class StructuredGenerationError(ValueError):
    """Provider output was absent or failed the structured schema."""


class GeminiStructuredGenerator:
    """Generate a :class:`StructuredAnswer` using Gemini's JSON schema mode."""

    model_version = MODEL_VERSION
    prompt_name = PROMPT_NAME
    prompt_version = PROMPT_VERSION

    def __init__(self, client: _Client | None = None, *, model: str | None = None) -> None:
        self._client = client
        self._model = model

    def generate(
        self, query: str, evidence: Any, *, feedback: str | None = None
    ) -> StructuredAnswer:
        client = self._client
        model = self._model
        if client is None or model is None:
            from google import genai

            from app.config import get_generation_settings

            settings = get_generation_settings()
            model = model or settings.model
            client = cast(_Client, client or genai.Client(api_key=settings.gemini_api_key))
        from google.genai import types

        prompt = (
            "Use only the supplied legal evidence. Return only a structured legal answer. "
            "Every legal claim must cite a provision ID from the evidence. "
            f"Question: {query}\nEvidence: {evidence}"
        )
        if feedback:
            prompt += f"\nRepair feedback: {feedback}"
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=StructuredAnswer,
                    temperature=0.2,
                ),
            )
            value = getattr(response, "parsed", None)
            if value is None:
                value = getattr(response, "text", None)
            if value is None:
                raise StructuredGenerationError("Gemini returned no structured answer")
            try:
                return StructuredAnswer.model_validate(value)
            except Exception as exc:
                message = "Gemini structured answer schema validation failed"
                raise StructuredGenerationError(message) from exc
        except StructuredGenerationError:
            raise
        except Exception as exc:
            raise StructuredGenerationError("Gemini structured answer generation failed") from exc


__all__ = [
    "GeminiStructuredGenerator",
    "MODEL_VERSION",
    "PROMPT_NAME",
    "PROMPT_VERSION",
    "StructuredGenerationError",
]
