"""Gemini structured-output adapter for legal answers."""

from __future__ import annotations

from typing import Any, Protocol, cast

import app.config as config

from .schemas import StructuredAnswer

MODEL_VERSION = "gemini-3.7-flash"
PROMPT_NAME = "legal-generator-v1"
PROMPT_VERSION = "2"


class _Models(Protocol):
    def generate_content(self, **kwargs: Any) -> Any: ...


class _Client(Protocol):
    models: _Models


class StructuredGenerationError(ValueError):
    """Provider output was absent or failed the structured schema."""


class GenerationConfigurationError(StructuredGenerationError):
    """Generation cannot run because provider credentials/configuration are absent."""


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
            settings = config.get_generation_settings()
            model = model or settings.model or MODEL_VERSION
            if client is None:
                if not settings.gemini_api_key:
                    raise GenerationConfigurationError(
                        "GEMINI_API_KEY is required for legal answer generation"
                    )
                try:
                    from google import genai
                except ImportError as exc:
                    raise GenerationConfigurationError(
                        "google-genai is required for legal answer generation"
                    ) from exc
                client = cast(_Client, genai.Client(api_key=settings.gemini_api_key))
        from google.genai import types

        prompt = (
            "Bạn là trợ lý thông tin pháp luật giao thông Việt Nam. Trả lời bằng tiếng Việt "
            "rõ ràng, thân thiện và chuyên nghiệp; đây không phải là quyết định ràng buộc "
            "của tòa án, cơ quan công an hay tư vấn đại diện pháp lý. "
            "Chỉ dùng bằng chứng pháp lý được cung cấp cho các kết luận pháp luật; không "
            "được bịa điều khoản, mức phạt, ngày hiệu lực, trích dẫn, đường dẫn hoặc trích "
            "dẫn văn bản. Mỗi claim pháp lý phải gắn với đúng provision_id trong bằng chứng, "
            "bỏ hậu tố phiên bản @vN nếu nhãn ngữ cảnh có hậu tố đó "
            "(without the @vN version suffix). "
            "Nếu có nhiều tình huống, giữ số thứ tự và tách từng tình huống; nếu tương thích "
            "hãy ghi nhận case identity trong claim. Nêu kết luận trực tiếp trước, sau đó căn cứ "
            "và điều kiện/ngoại lệ. Luôn nói rõ bằng chứng trong corpus hỗ trợ điều gì và còn "
            "thiếu điều gì; dùng should_abstain=true khi chưa đủ căn cứ. Kết thúc bằng bước "
            "tiếp theo nhỏ nhất nhưng hữu ích (hoặc thông tin tối thiểu cần bổ sung). "
            "Không gộp các claim không cùng căn cứ vào một trích dẫn. "
            f"\nCâu hỏi: {query}\nBằng chứng: {evidence}"
        )
        if feedback:
            prompt += f"\nRepair feedback: {feedback}"
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    # Passing the plain schema avoids the SDK's Pydantic adapter
                    # emitting unsupported ``additional_properties`` fields.
                    response_json_schema=StructuredAnswer.model_json_schema(),
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
    "GenerationConfigurationError",
]
