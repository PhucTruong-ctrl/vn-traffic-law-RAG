"""Grounded answer generation through LangChain ChatOpenRouter."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.documents import Document

from app.config import get_generation_settings

_SYSTEM_PROMPT = (
    "Bạn là trợ lý tra cứu pháp luật giao thông Việt Nam. "
    "Chỉ trả lời dựa trên các tài liệu được cung cấp; nếu thiếu căn cứ, "
    "nói rõ chưa đủ thông tin. Không tự tạo số điều, nguồn hoặc trích dẫn."
)


def build_prompt(question: str, documents: Sequence[Document]) -> list[tuple[str, str]]:
    context = "\n\n".join(document.page_content for document in documents)
    return [("system", _SYSTEM_PROMPT), ("human", f"QUESTION:\n{question}\n\nCONTEXT:\n{context}")]


def generate_answer(question: str, documents: Sequence[Document]) -> str:
    """Generate only from retrieved documents; provider failures are explicit."""
    if not documents:
        return "Chưa tìm thấy quy định phù hợp trong dữ liệu pháp luật được truy xuất."
    settings = get_generation_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OpenRouter API key is missing (set OPENROUTER_API_KEY)")
    try:
        from langchain_openrouter import ChatOpenRouter
    except ImportError as exc:
        raise RuntimeError(
            "OpenRouter integration is not installed; run `uv sync --project backend`"
        ) from exc

    try:
        model = ChatOpenRouter(
            model=settings.model,
            temperature=0,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        response = model.invoke(build_prompt(question, documents))
        content: Any = response.content
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter returned an empty answer")
        return content.strip()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("OpenRouter request failed") from exc


__all__ = ["build_prompt", "generate_answer"]
