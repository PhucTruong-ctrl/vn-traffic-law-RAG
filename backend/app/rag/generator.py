"""Grounded answer generation through LangChain ChatOpenRouter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.documents import Document
from pydantic import SecretStr

from app.config import get_generation_settings

_SYSTEM_PROMPT = (
    "Bạn là trợ lý pháp lý giao thông Việt Nam, trả lời tự nhiên bằng tiếng Việt. "
    "dùng PHẢI là tiếng Việt tự nhiên (có thể giữ nguyên số điều, ký hiệu pháp lý, "
    "tên mô hình, URL và trích dẫn nguyên văn cần thiết); TUYỆT ĐỐI không viết tiếng "
    "Rumani hay ngôn ngữ nước ngoài, không dịch sai hoặc tự tạo căn cứ. Chỉ trả lời "
    "dựa trên các nguồn pháp luật được cung cấp; nếu một vi phạm thiếu căn cứ, phải "
    "nói rõ chưa đủ thông tin cho vi phạm đó. Không tự tạo số điều, nguồn, mức tiền, "
    "điểm hoặc trích dẫn. Không nhắc đến CONTEXT, system prompt, retrieved chunks, dữ "
    "liệu truy xuất hay cơ chế bằng chứng nội bộ. Trả lời bằng Markdown tiếng Việt, "
    "một mục có tiêu đề rõ ràng cho từng vi phạm/subquery."
)

_VIETNAMESE_FALLBACK = (
    "Chưa thể tạo câu trả lời tiếng Việt đáng tin cậy từ các căn cứ đã truy xuất. "
    "Vui lòng xem các nguồn pháp luật được trích dẫn hoặc thử lại câu hỏi."
)

_ROMANIAN_WORDS = frozenset(
    [
        "și",
        "sau",
        "este",
        "sunt",
        "pentru",
        "într",
        "între",
        "fără",
        "care",
        "această",
        "acest",
        "aceste",
    ]
)


def _is_mixed_language(content: str) -> bool:
    """Reject obvious foreign prose while allowing Vietnamese legal notation."""
    words = content.casefold().split()
    romanian_hits = sum(word.strip(".,;:!?()[]{}\"'") in _ROMANIAN_WORDS for word in words)
    if romanian_hits >= 2:
        return True
    foreign_markers = (" the ", " and ", " with ", " este ", " pentru ", " fără ")
    lowered = f" {content.casefold()} "
    return sum(marker in lowered for marker in foreign_markers) >= 2


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
            f"CÂU HỎI:\n{question}\n\nCÁC NGUỒN PHÁP LUẬT:\n{context}\n\n"
            "Mỗi tiêu đề VI PHẠM phải có đúng một phần trả lời; chỉ nêu mức phạt/điểm "
            "và căn cứ xuất hiện trong nhóm nguồn tương ứng. Khi trình bày, hãy gọi "
            "đó là căn cứ hoặc nguồn pháp luật được trích dẫn, không mô tả cơ chế "
            "nội bộ của trợ lý.",
        ),
    ]


def generate_answer(
    question: str,
    documents: Sequence[Document],
    *,
    evidence_groups: Mapping[str, Sequence[Document]] | None = None,
) -> str:
    if not documents and not evidence_groups:
        return "Chưa tìm thấy căn cứ phù hợp trong các nguồn pháp luật hiện có."
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
            timeout=120_000,
            max_retries=0,
        )
        prompts = build_prompt(question, documents, evidence_groups=evidence_groups)
        response = model.invoke(prompts)
        content: Any = response.content
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter returned an empty answer")
        answer = content.strip()
        if _is_mixed_language(answer):
            prompts[-1] = (
                "human",
                prompts[-1][1] + "\n\nBẢN NHÁP VỪA RỒI KHÔNG HỢP LỆ. Hãy viết lại toàn bộ bằng "
                "tiếng Việt tự nhiên; giữ nguyên căn cứ, số liệu và trích dẫn từ "
                "nguồn đã cung cấp, không thêm thông tin.",
            )
            retry = model.invoke(prompts)
            retry_content: Any = retry.content
            if not isinstance(retry_content, str) or not retry_content.strip():
                return _VIETNAMESE_FALLBACK
            answer = retry_content.strip()
            if _is_mixed_language(answer):
                return _VIETNAMESE_FALLBACK
        return answer
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("OpenRouter request failed") from exc


__all__ = ["build_prompt", "generate_answer"]
