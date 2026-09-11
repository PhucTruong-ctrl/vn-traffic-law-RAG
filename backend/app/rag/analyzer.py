"""Small structured multi-intent decomposition with deterministic fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Intent:
    text: str
    kind: str = "legal"


@dataclass(frozen=True, slots=True)
class Analysis:
    intents: tuple[Intent, ...]
    vehicle_type: str = "any"


_VEHICLE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("car", r"\b(?:ô\s*tô|ô tô|xe hơi|xe ô tô)\b"),
    (
        "motorcycle",
        r"\b(?:xe mô tô|xe máy|xe gắn máy|mô tô|moped)\b",
    ),
    ("bicycle", r"\b(?:xe đạp|đạp điện)\b"),
    ("specialized", r"\b(?:xe chuyên dùng|máy kéo)\b"),
)

VEHICLE_LABELS: dict[str, str] = {
    "car": "ô tô",
    "motorcycle": "xe mô tô, xe gắn máy",
    "bicycle": "xe thô sơ",
    "specialized": "xe chuyên dùng",
}


def vehicle_label(vehicle_type: str) -> str:
    """Map an internal vehicle category key to its canonical Vietnamese label."""
    return VEHICLE_LABELS[vehicle_type]


def detect_vehicle_types(text: str) -> tuple[str, ...]:
    """Return explicitly named vehicle categories in stable pattern order."""
    return tuple(kind for kind, pattern in _VEHICLE_PATTERNS if re.search(pattern, text, re.I))


def detect_vehicle_type(text: str) -> str:
    """Return the explicit vehicle category, or ``any`` when unspecified/ambiguous."""
    found = detect_vehicle_types(text)
    return found[0] if len(found) == 1 else "any"


def resolve_vehicle_followup(question: str, history: object = ()) -> str:
    """Resolve a bounded short vehicle comparison against the latest legal turn."""
    current = " ".join(question.split()).strip()
    vehicle = detect_vehicle_type(current)
    if vehicle == "any" or len(current.split()) > 8:
        return current
    if not re.search(r"\b(còn|vậy|thế|đối với|xe)\b", current, re.I):
        return current
    messages = list(history)[-6:] if isinstance(history, (list, tuple)) else []
    prior = next(
        (
            str(item.get("content", ""))
            for item in reversed(messages)
            if isinstance(item, dict)
            and str(item.get("role", "")).casefold() == "user"
            and classify_intent(str(item.get("content", ""))) == "legal"
        ),
        "",
    )
    if not prior:
        return current
    base = re.sub(
        (
            r"\b(?:xe\s*)?(?:ô\s*tô|xe hơi|xe máy|xe mô tô|xe gắn máy|"
            r"mô tô|moped|xe đạp|đạp điện|xe chuyên dùng|máy kéo)\b"
        ),
        "",
        prior,
        flags=re.I,
    )
    base = re.sub(r"\b(?:phạt|mức phạt|bao nhiêu)\b", "", base, flags=re.I)
    base = " ".join(base.split()).strip(" ,;:-?.")
    if not base:
        return current
    label = vehicle_label(vehicle)
    # Normalize the extracted violation into sentence position and remove
    # filler/copy of the prior question's copula.
    base = base[:1].lower() + base[1:] if base else base
    base = re.sub(r"\s+\bthì\b(?=\s|$)", "", base, flags=re.I)
    return f"Mức phạt đối với {label} {base} bao nhiêu?"


_DIMENSION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("mức phạt", r"\b(?:mức\s*)?phạt\b|\btiền\s*phạt\b"),
    ("trừ điểm GPLX", r"\btrừ\s*điểm\b|\bđiểm\s*(?:giấy phép lái xe|gplx)\b"),
    ("tước quyền sử dụng", r"\btước\s+quyền\s+sử\s*dụng\b|\btước\s*gplx\b"),
    ("xử lý/tạm giữ phương tiện", r"\b(?:xử lý|tạm\s*giữ)\s+(?:phương tiện|xe)\b"),
)


def analyze_question(question: str, model: object | None = None) -> Analysis:
    """Decompose bounded Vietnamese legal compound questions deterministically."""
    if model is not None and hasattr(model, "invoke"):
        try:
            value = model.invoke(question)
            parsed = _from_model(value)
            if parsed:
                return Analysis(tuple(parsed[:4]))
        except Exception:
            pass

    normalized = " ".join(question.split()).strip(" .?!")
    if not normalized:
        return Analysis(())
    normalized = re.sub(r"\bko\b", "không", normalized, flags=re.I)
    violation_phrases = ("vượt đèn đỏ", "không đội mũ bảo hiểm")
    clauses = [
        piece.strip(" .?!")
        for piece in re.split(r"\s+(?:và|đồng thời|ngoài ra)\s+", normalized, flags=re.I)
        if piece.strip(" .?!")
    ]
    if len(clauses) == 1 and all(
        re.search(rf"\b{re.escape(phrase)}\b", normalized, re.I) for phrase in violation_phrases
    ):
        clauses = list(violation_phrases)
    dimensions = [
        (label, match.start())
        for label, pattern in _DIMENSION_PATTERNS
        for match in re.finditer(pattern, normalized, flags=re.I)
    ]
    if len(clauses) <= 1 and not dimensions:
        return Analysis((Intent(normalized, classify_intent(normalized)),))

    context = _violation_context(normalized, dimensions)
    intents: list[Intent] = []
    for clause in clauses:
        if _is_dimension(clause):
            continue
        if classify_intent(clause) == "legal" and _is_meaningful_clause(clause):
            intents.append(Intent(_strip_conversational_prefix(clause), "legal"))
    for label, _ in sorted(dimensions, key=lambda item: item[1]):
        intents.append(Intent(f"{context}; {label}", "legal"))
    stable: list[Intent] = []
    seen: set[str] = set()
    for intent in intents:
        key = " ".join(intent.text.casefold().split())
        if key not in seen:
            seen.add(key)
            stable.append(intent)
    return Analysis(tuple(stable[:4]) or (Intent(normalized, classify_intent(normalized)),))


def _is_dimension(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for _, pattern in _DIMENSION_PATTERNS)


def _strip_conversational_prefix(text: str) -> str:
    return re.sub(r"^Khi\s+", "", text, count=1, flags=re.I)


def _is_meaningful_clause(text: str) -> bool:
    return len(re.findall(r"[^\W\d_]+", text, flags=re.UNICODE)) >= 3


def _violation_context(question: str, dimensions: list[tuple[str, int]]) -> str:
    context = question
    if dimensions:
        first = min(position for _, position in dimensions)
        context = question[:first].strip(" ,;:-")
    context = re.sub(
        r"\b(?:mức\s*)?phạt\b|\btiền\s*phạt\b|\btrừ\s*điểm\b|"
        r"\bđiểm\s*(?:giấy phép lái xe|gplx)\b|\btước\s+quyền\s+sử\s*dụng\b|"
        r"\btước\s*gplx\b|\b(?:xử lý|tạm\s*giữ)\s+(?:phương tiện|xe)\b",
        "",
        context,
        flags=re.I,
    )
    return " ".join(context.split()).strip(" ,;:-") or question


def classify_intent(text: str) -> str:
    lowered = text.casefold()
    if re.search(r"\b(hello|hi|xin chào|cảm ơn|tạm biệt)\b", lowered):
        return "chitchat"
    if re.search(r"\b(google|web|internet|trên mạng|tin tức)\b", lowered):
        return "web"
    if re.search(
        r"\b(luật|điều|khoản|nghị định|thông tư|phạt|giao thông|đường bộ|"
        r"tốc độ|km/?h|khu vực đông dân cư|vượt đèn đỏ|"
        r"không đội mũ bảo hiểm|trừ điểm|tước quyền|tạm giữ|phương tiện)\b",
        lowered,
    ):
        return "legal"
    return "out_of_scope"


def _from_model(value: object) -> list[Intent]:
    raw = getattr(value, "intents", value)
    if isinstance(raw, (list, tuple)):
        items: list[object] = list(raw)
    else:
        return []
    result: list[Intent] = []
    for item in items:
        if isinstance(item, Intent):
            result.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            result.append(
                Intent(item["text"], str(item.get("kind") or classify_intent(item["text"])))
            )
    return result


__all__ = [
    "Analysis",
    "Intent",
    "VEHICLE_LABELS",
    "analyze_question",
    "classify_intent",
    "detect_vehicle_type",
    "detect_vehicle_types",
    "resolve_vehicle_followup",
    "vehicle_label",
]
