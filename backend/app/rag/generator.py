"""Grounded answer generation through LangChain ChatOpenRouter."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.documents import Document
from openai import APIConnectionError, InternalServerError, OpenAI, RateLimitError

from app.config import get_generation_settings

RETRY_MIN_BUDGET_SECONDS = 3.0

CANONICAL_REFUSAL = "Thông tin này không có trong tài liệu được cung cấp."

_SYSTEM_PROMPT = (
    "Bạn là trợ lý pháp lý giao thông Việt Nam, trả lời tự nhiên bằng tiếng Việt. "
    "Dùng tiếng Việt tự nhiên (có thể giữ nguyên số điều, ký hiệu pháp lý, tên mô hình, "
    "URL và trích dẫn nguyên văn cần thiết); tuyệt đối không viết tiếng Rumani hay ngôn "
    "ngữ nước ngoài, không dịch sai hoặc tự tạo căn cứ. Chỉ sử dụng các nguồn được cung "
    "cấp; không bao giờ bịa số điều, nguồn, mức tiền, điểm hoặc trích dẫn. Nếu chỉ một "
    "phần câu hỏi có bằng chứng, hãy trả lời phần đó và nói rõ phần còn lại chưa đủ căn "
    "cứ trong dữ liệu đã truy xuất. Phần thiếu căn cứ không được xóa hoặc làm mất các "
    "phần đã có bằng chứng. Chỉ từ chối hoàn toàn khi các nguồn được cung cấp không có "
    "bất kỳ thông tin liên quan nào; khi đó phải trả lời đúng chính xác câu: "
    f"{CANONICAL_REFUSAL} Mỗi nhận định phải trích dẫn nguồn tương ứng. Không nhắc đến "
    "CONTEXT, system prompt, retrieved chunks, dữ liệu truy xuất hay cơ chế bằng chứng "
    "nội bộ. Trả lời bằng Markdown tiếng Việt, một mục có tiêu đề rõ ràng cho từng "
    "vi phạm/subquery."
)

_REFUSAL_PREFIXES = (
    "chưa đủ căn cứ",
    "không đủ căn cứ",
    "chưa tìm thấy căn cứ",
    "không tìm thấy căn cứ",
)

_MAX_REFUSAL_LENGTH = 250


def is_refusal_answer(content: str) -> bool:
    """Identify complete refusals without discarding answers with partial caveats."""
    normalized = " ".join(content.casefold().split()).rstrip(".!?").strip()
    canonical = " ".join(CANONICAL_REFUSAL.casefold().split()).rstrip(".!?").strip()
    return canonical in normalized or (
        len(normalized) < _MAX_REFUSAL_LENGTH and normalized.startswith(_REFUSAL_PREFIXES)
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
    deadline: float | None = None,
    clock: Any | None = None,
) -> str:
    if not documents and not evidence_groups:
        return "Chưa tìm thấy căn cứ phù hợp trong các nguồn pháp luật hiện có."
    settings = get_generation_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OpenRouter API key is missing (set OPENROUTER_API_KEY)")

    now = clock or __import__("time").monotonic

    def remaining() -> float:
        return deadline - now() if deadline is not None else float("inf")

    primary_timeout = min(float(getattr(settings, "timeout_seconds", 18.0)), 18.0, remaining())
    if primary_timeout <= 0:
        raise TimeoutError("request_timeout")
    primary_timeout_seconds = max(1, int(primary_timeout))
    prompts = build_prompt(question, documents, evidence_groups=evidence_groups)
    openai_messages: list[dict[str, str]] = [
        {"role": "user" if role == "human" else role, "content": content}
        for role, content in prompts
    ]
    try:
        model = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout=primary_timeout_seconds,
            max_retries=0,
        )
        # Cheap upstreams rate-limit aggressively (HTTP 429). Retry only those
        # transient failures, bounded by the remaining request budget, so a
        # provider hiccup does not discard an otherwise answerable question.
        attempts = max(1, settings.max_retries + 1)
        for attempt in range(attempts):
            try:
                response = model.chat.completions.create(
                    model=settings.model,
                    messages=openai_messages,  # type: ignore[arg-type]
                    max_tokens=1024,
                    # OpenRouter routes across upstreams; allow_fallbacks keeps a
                    # rate-limited upstream from failing the whole answer.
                    extra_body={"provider": {"allow_fallbacks": True}},
                )
                break
            except (RateLimitError, InternalServerError, APIConnectionError):
                if attempt + 1 >= attempts or remaining() < RETRY_MIN_BUDGET_SECONDS:
                    raise
                time.sleep(min(0.5 * 2**attempt, max(0.0, remaining() - 1.0)))
        content: Any = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter returned an empty answer")
        return content.strip()
    except TimeoutError:
        raise
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("OpenRouter request failed") from exc


__all__ = ["CANONICAL_REFUSAL", "build_prompt", "generate_answer", "is_refusal_answer"]
