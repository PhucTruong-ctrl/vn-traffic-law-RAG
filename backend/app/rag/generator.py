"""Prompt construction and optional OpenAI-compatible generation."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def build_prompt(question: str, context: str) -> list[dict[str, str]]:
    """Build a grounded chat prompt; the model is never trusted for citations."""
    return [
        {
            "role": "system",
            "content": (
                "Bạn là trợ lý tra cứu pháp luật giao thông Việt Nam. "
                "Chỉ trả lời dựa trên CONTEXT; nếu thiếu căn cứ, nói rõ chưa đủ thông tin. "
                "Không tự tạo số điều, nguồn hoặc trích dẫn."
            ),
        },
        {"role": "user", "content": f"QUESTION:\n{question}\n\nCONTEXT:\n{context}"},
    ]


def _fallback(question: str, context: str) -> str:
    if not context.strip():
        return "Chưa tìm thấy quy định phù hợp trong dữ liệu pháp luật được truy xuất."
    return (
        "Dựa trên các quy định được truy xuất, câu hỏi của bạn được trả lời bằng "
        "nội dung sau:\n\n" + context
    )


def generate_answer(question: str, context: str, *, settings: Any = None) -> str:
    """Call OpenRouter when configured, otherwise fall back."""
    api_key = getattr(settings, "api_key", None) if settings is not None else None
    base_url = getattr(settings, "base_url", None) if settings is not None else None
    model = getattr(settings, "model", None) if settings is not None else None
    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    base_url = base_url or os.getenv("OPENROUTER_BASE_URL")
    model = model or os.getenv("LLM_MODEL") or "google/gemini-2.5-flash"
    if not api_key:
        return _fallback(question, context)
    base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
    payload = json.dumps({"model": model, "messages": build_prompt(question, context)}).encode()
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode())
        answer = body["choices"][0]["message"]["content"]
        return (
            answer.strip()
            if isinstance(answer, str) and answer.strip()
            else _fallback(question, context)
        )
    except (OSError, ValueError, KeyError, IndexError, TypeError, urllib.error.URLError):
        return _fallback(question, context)


__all__ = ["build_prompt", "generate_answer"]
