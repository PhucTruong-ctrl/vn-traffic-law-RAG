"""OpenRouter structured-output adapter for legal answers."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request

import app.config as config

from .schemas import StructuredAnswer

MODEL_VERSION = "google/gemini-2.5-flash-lite"
PROMPT_NAME = "legal-generator-v1"
PROMPT_VERSION = "2"
OPENROUTER_CHAT_COMPLETIONS_PATH = "/chat/completions"


class StructuredGenerationError(ValueError):
    """Provider output was absent or failed the structured schema."""


class GenerationConfigurationError(StructuredGenerationError):
    """Generation cannot run because provider credentials/configuration are absent."""


def _content_value(response: Any) -> Any:
    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                return message.get("content")
        return response.get("content")
    return getattr(response, "content", None)


class OpenRouterStructuredGenerator:
    """Generate a :class:`StructuredAnswer` through OpenRouter Chat Completions."""

    model_version = MODEL_VERSION
    prompt_name = PROMPT_NAME
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        opener: Any = request.urlopen,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._timeout = timeout
        self._opener = opener

    def generate(
        self, query: str, evidence: Any, *, feedback: str | None = None
    ) -> StructuredAnswer:
        settings = config.get_generation_settings()
        api_key = self._api_key if self._api_key is not None else settings.openrouter_api_key
        if not api_key:
            raise GenerationConfigurationError(
                "OPENROUTER_API_KEY is required for legal answer generation"
            )
        model = self._model or settings.model or MODEL_VERSION
        base_url = (self._base_url or settings.openrouter_base_url).rstrip("/")
        prompt = (
            "Bạn là trợ lý thông tin pháp luật giao thông Việt Nam. Trả lời bằng tiếng Việt "
            "rõ ràng, thân thiện và chuyên nghiệp; đây không phải là quyết định ràng buộc "
            "của tòa án, cơ quan công an hay tư vấn đại diện pháp lý. Chỉ dùng bằng chứng "
            "hoặc đường dẫn. Mỗi claim pháp lý phải gắn với đúng một provision_id "
            "trong bằng chứng; mỗi provision_id chỉ được dùng cho một claim duy nhất, "
            "không lặp lại giữa các claim. Nếu có nhiều tình huống, giữ số thứ tự và tách "
            "từng tình huống. Nêu kết luận trực tiếp trước, sau đó căn cứ và điều kiện/ngoại lệ. "
            "Luôn nói rõ bằng chứng hỗ trợ điều gì và còn thiếu điều gì; dùng should_abstain=true "
            "khi chưa đủ căn cứ. Kết thúc bằng bước tiếp theo nhỏ nhất nhưng hữu ích."
            f"\nCâu hỏi: {query}\nBằng chứng: {evidence}"
        )
        if feedback:
            prompt += f"\nRepair feedback: {feedback}"
        schema = StructuredAnswer.model_json_schema()
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "structured_answer", "strict": True, "schema": schema},
            },
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{base_url}{OPENROUTER_CHAT_COMPLETIONS_PATH}",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(req, timeout=self._timeout) as response:
                raw = response.read()
            decoded = json.loads(raw)
            content = _content_value(decoded)
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            if not content:
                raise StructuredGenerationError("OpenRouter returned no structured answer")
            if isinstance(content, str):
                content = content.strip()
                if content.startswith("```"):
                    content = content.strip("`")
                    if content.startswith("json"):
                        content = content[4:].lstrip()
                content = json.loads(content)
            return StructuredAnswer.model_validate(content)
        except StructuredGenerationError:
            raise
        except (error.HTTPError, error.URLError, TimeoutError) as exc:
            raise StructuredGenerationError(
                "OpenRouter structured answer generation failed"
            ) from exc
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise StructuredGenerationError(
                "OpenRouter structured answer schema validation failed"
            ) from exc
        except Exception as exc:
            raise StructuredGenerationError(
                "OpenRouter structured answer generation failed"
            ) from exc


__all__ = [
    "OpenRouterStructuredGenerator",
    "MODEL_VERSION",
    "PROMPT_NAME",
    "PROMPT_VERSION",
    "StructuredGenerationError",
    "GenerationConfigurationError",
]
