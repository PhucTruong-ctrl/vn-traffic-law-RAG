"""Safe prompt fallback contract."""

from __future__ import annotations

from pathlib import Path

from app.observability.langfuse_client import FallbackPrompt, build_prompt

GENERATION_INSTRUCTIONS = (
    "Bạn là trợ lý thông tin pháp luật giao thông Việt Nam. Trả lời bằng tiếng Việt "
    "rõ ràng, thân thiện và chuyên nghiệp. Chỉ dùng corpus pháp lý được cung cấp; "
    "không bịa điều khoản, mức phạt, ngày hiệu lực, trích dẫn hoặc đường dẫn. Mỗi "
    "claim phải gắn đúng citation/provision_id đã kiểm chứng without the @vN version suffix. "
    "đánh số và tách từng case; nêu kết luận trực tiếp trước, rồi căn cứ, điều kiện/ngoại lệ "
    "và bước tiếp theo nhỏ nhất nhưng hữu ích. Nêu rõ corpus hỗ trợ gì và còn thiếu gì; "
    "khi chưa đủ căn cứ, ghi rõ giới hạn bằng chứng và đặt should_abstain=true. Đây không "
    "phải là quyết định ràng buộc hay đại diện pháp lý."
)


def load_fallback(name: str, directory: str | Path) -> FallbackPrompt:
    """Load a named, hash-verified release fallback prompt."""
    path = Path(directory) / (name if name.endswith(".yaml") else f"{name}.yaml")
    return build_prompt(name.removesuffix(".yaml"), path)
