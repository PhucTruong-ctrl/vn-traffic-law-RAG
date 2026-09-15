"""Shared abstention message."""

ABSTENTION_MESSAGE = "Chưa đủ căn cứ trong dữ liệu pháp luật được truy xuất để trả lời chắc chắn."
CLARIFICATION_REQUIRED_MESSAGE = (
    "Vui lòng nêu rõ hành vi vi phạm hoặc tình huống giao thông cần tra cứu "
    "để tôi xác định mức phạt."
)
RETRIEVAL_FAILURE_MESSAGE = (
    "Hệ thống tra cứu đang quá tải hoặc không phản hồi kịp. Vui lòng thử lại sau ít giây."
)
__all__ = [
    "ABSTENTION_MESSAGE",
    "CLARIFICATION_REQUIRED_MESSAGE",
    "RETRIEVAL_FAILURE_MESSAGE",
]
