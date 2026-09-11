"""Deterministic comparison intent parsing and formatting."""

from __future__ import annotations

import re
from collections.abc import Iterable

_VEHICLE_RE = re.compile(
    r"\b(ô tô|xe máy|xe mô tô|xe đạp|xe tải|xe khách|xe con|mô tô|motorcycle|car|truck)\b",
    re.IGNORECASE,
)
_DIMENSIONS = (
    ("mức phạt", ("phạt", "mức phạt", "tiền")),
    ("điều kiện", ("điều kiện", "trường hợp", "khi nào")),
    ("thẩm quyền", ("thẩm quyền", "ai xử lý", "cơ quan")),
    ("tước giấy phép", ("tước bằng", "tước giấy phép", "giấy phép")),
    ("hành vi", ("hành vi", "vi phạm", "lỗi")),
)


def split_compare_intent(question: str) -> dict[str, object]:
    """Extract vehicle types and legal dimensions from comparison question."""
    text = " ".join(question.split())
    if not text:
        raise ValueError("question must not be blank")
    vehicles: list[str] = []
    for match in _VEHICLE_RE.finditer(text):
        value = match.group(1).lower()
        if value not in vehicles:
            vehicles.append(value)
    dimensions = [
        name for name, terms in _DIMENSIONS if any(term in text.lower() for term in terms)
    ]
    return {"question": text, "vehicles": vehicles, "dimensions": dimensions}


def format_compare_result(
    comparisons: Iterable[tuple[str, str, str]],
    *,
    dimensions: Iterable[str] = (),
) -> str:
    """Format comparison rows predictably, preserving caller order."""
    rows = [f"- {left} — {dimension}: {right}" for left, dimension, right in comparisons]
    requested = [str(item).strip() for item in dimensions if str(item).strip()]
    heading = "So sánh" + (f" ({', '.join(requested)})" if requested else "")
    return heading + ("\n" + "\n".join(rows) if rows else "\nChưa có dữ liệu so sánh.")


__all__ = ["format_compare_result", "split_compare_intent"]
