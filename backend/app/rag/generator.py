"""Grounded answer generation through LangChain ChatOpenRouter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.documents import Document
from pydantic import SecretStr

from app.config import get_generation_settings

_SYSTEM_PROMPT = (
    "Bạn là trợ lý tra cứu pháp luật giao thông Việt Nam. "
    "Chỉ trả lời dựa trên CONTEXT được cung cấp; nếu một vi phạm thiếu căn cứ, "
    "phải ghi rõ chưa đủ thông tin cho vi phạm đó. Không tự tạo số điều, nguồn, "
    "mức tiền, điểm hoặc trích dẫn. Trả lời bằng Markdown tiếng Việt, một mục "
    "có tiêu đề rõ ràng cho từng vi phạm/subquery."
)


def _metadata(document: Document) -> str:
    metadata = document.metadata or {}
    fields = (
        ("document", metadata.get("document_name") or metadata.get("document_number")),
        ("article", metadata.get("article")),
        ("clause", metadata.get("clause")),
        ("point", metadata.get("point")),
    )
    return "; ".join(f"{key}={value}" for key, value in fields if value is not None)


def _context(
    documents: Sequence[Document], evidence_groups: Mapping[str, Sequence[Document]] | None
) -> str:
    groups = evidence_groups or {"Căn cứ truy xuất": documents}
    blocks: list[str] = []
    for label, group in groups.items():
        blocks.append(f"### VI PHẠM: {label}")
        if not group:
            blocks.append("(THIẾU CĂN CỨ)")
            continue
        for index, document in enumerate(group, 1):
            metadata = _metadata(document)
            header = f"[doc-{index}{': ' + metadata if metadata else ''}]"
            blocks.append(f"{header}\n{document.page_content}")
    return "\n\n".join(blocks)


def build_prompt(
    question: str,
    documents: Sequence[Document],
    *,
    evidence_groups: Mapping[str, Sequence[Document]] | None = None,
) -> list[tuple[str, str]]:
    context = _context(documents, evidence_groups)
    return [
        ("system", _SYSTEM_PROMPT),
        (
            "human",
            f"QUESTION:\n{question}\n\nCONTEXT (chỉ được dùng dữ liệu dưới đây):\n{context}\n\n"
            "Mỗi tiêu đề VI PHẠM phải có đúng một phần trả lời; chỉ nêu mức phạt/điểm và "
            "căn cứ xuất hiện trong phần CONTEXT tương ứng.",
        ),
    ]


def generate_answer(
    question: str,
    documents: Sequence[Document],
    *,
    evidence_groups: Mapping[str, Sequence[Document]] | None = None,
) -> str:
    """Generate only from retrieved documents; provider failures are explicit."""
    if not documents and not evidence_groups:
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
            api_key=SecretStr(settings.openrouter_api_key),
            base_url=settings.openrouter_base_url,
        )
        response = model.invoke(build_prompt(question, documents, evidence_groups=evidence_groups))
        content: Any = response.content
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter returned an empty answer")
        return content.strip()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("OpenRouter request failed") from exc


__all__ = ["build_prompt", "generate_answer"]
