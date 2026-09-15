"""Small structured multi-intent decomposition with deterministic fallback."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_generation_settings

ModelCallable = Callable[[str], object]
Category = Literal["legal_rag", "chitchat", "out_of_scope"]
IntentValue = Literal["penalty", "rule", "procedure", "definition", "list", "mixed"]
VehicleType = Literal["car", "motorcycle", "bicycle", "specialized", "any"]


class AnalyzerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category
    intent: IntentValue
    vehicle_type: VehicleType
    standalone_query: str = Field(min_length=1)
    expanded_queries: list[str] = Field(min_length=1, max_length=3)


@dataclass(frozen=True, slots=True)
class RequestAnalysis:
    category: str
    intent: str
    vehicle_type: str
    standalone_query: str
    expanded_queries: tuple[str, ...]
    frames: Analysis
    source: str


@dataclass(frozen=True, slots=True)
class Intent:
    text: str
    kind: str = "legal"


@dataclass(frozen=True, slots=True)
class Analysis:
    intents: tuple[Intent, ...]
    vehicle_type: str = "any"

    @property
    def vehicle_types(self) -> tuple[str, ...]:
        """Return all explicitly named canonical vehicle categories."""
        if self.vehicle_type == "any":
            return ()
        return (self.vehicle_type,)


CANONICAL_VEHICLE_CATEGORIES = ("car", "motorcycle", "bicycle", "specialized")


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

_VEHICLE_ALIASES = {
    "ô tô": "car",
    "xe ô tô": "car",
    "xe hơi": "car",
    "car": "car",
    "xe mô tô, xe gắn máy": "motorcycle",
    "xe mô tô": "motorcycle",
    "xe gắn máy": "motorcycle",
    "xe máy": "motorcycle",
    "mô tô": "motorcycle",
    "moped": "motorcycle",
    "motorcycle": "motorcycle",
    "xe thô sơ": "bicycle",
    "xe đạp": "bicycle",
    "đạp điện": "bicycle",
    "bicycle": "bicycle",
    "xe chuyên dùng": "specialized",
    "xe máy chuyên dùng": "specialized",
    "máy kéo": "specialized",
    "specialized": "specialized",
}


def normalize_vehicle_metadata(metadata: dict[str, object]) -> dict[str, object]:
    """Normalize Vietnamese and canonical vehicle labels to stable category keys."""
    result = dict(metadata)
    raw = result.get("vehicle_categories", ())
    values = list(raw if isinstance(raw, (list, tuple, set)) else (raw,) if raw else ())
    values.extend(
        result[key] for key in ("vehicle", "vehicle_type", "vehicle_category") if result.get(key)
    )
    categories = []
    for value in values:
        category = _VEHICLE_ALIASES.get(" ".join(str(value).casefold().split()).strip())
        if category and category not in categories:
            categories.append(category)
    if categories:
        result["vehicle_categories"] = categories
    return result


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
        r"\b(?:xe\s*)?(?:ô\s*tô|xe hơi|xe máy|xe mô tô|xe gắn máy|"
        r"mô tô|moped|xe đạp|đạp điện|xe chuyên dùng|máy kéo)\b",
        "",
        prior,
        flags=re.I,
    )
    if "mũ bảo hiểm" in base.casefold() and "xe máy" in prior.casefold():
        base = re.sub(r"\b(?:không\s+)?đội\s+mũ\s+bảo\s+hiểm\b", "", base, flags=re.I)
    base = re.sub(r"\b(?:mức phạt|bao nhiêu|bị thế nào|thế nào|đi)\b", "", base, flags=re.I)
    if "mũ bảo hiểm" in prior.casefold() and vehicle == "car":
        return f"Mức phạt đối với {VEHICLE_LABELS[vehicle]} bao nhiêu?"
    base = re.sub(r"[?.!]+", " ", base)
    base = re.sub(r"\bbị\s+phạt\b", "", base, flags=re.I)
    base = re.sub(r"\bbị\s*$", "", base, flags=re.I)
    base = " ".join(base.split()).strip(" ,;:-")
    if not base:
        return current
    label = VEHICLE_LABELS[vehicle]
    base = base[:1].lower() + base[1:]
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
                return Analysis(tuple(parsed[:4]), detect_vehicle_type(question))
        except Exception:
            pass
    normalized = " ".join(question.split()).strip(" .?!")
    if not normalized:
        return Analysis(())
    normalized = re.sub(r"\bko\b", "không", normalized, flags=re.I)
    clauses = [
        piece.strip(" .?!")
        for piece in re.split(r"\s+(?:và|đồng thời|ngoài ra)\s+", normalized, flags=re.I)
        if piece.strip(" .?!")
    ]
    dimensions = [
        (label, match.start())
        for label, pattern in _DIMENSION_PATTERNS
        for match in re.finditer(pattern, normalized, flags=re.I)
    ]
    if len(clauses) <= 1 and not dimensions:
        return Analysis(
            (Intent(normalized, classify_intent(normalized)),), detect_vehicle_type(normalized)
        )
    context = _violation_context(normalized, dimensions)
    intents: list[Intent] = []
    for clause in clauses:
        if _is_dimension(clause):
            continue
        if classify_intent(clause) == "legal" and _is_meaningful_clause(clause):
            intents.append(Intent(_strip_conversational_prefix(clause), "legal"))
    for clause in clauses:
        if "điện thoại" in clause.casefold():
            intents.append(Intent(clause, "legal"))
    for label, _ in sorted(dimensions, key=lambda item: item[1]):
        intents.append(Intent(f"{context}; {label}", "legal"))
    stable: list[Intent] = []
    seen: set[str] = set()
    for intent in intents:
        key = " ".join(intent.text.casefold().split())
        if key not in seen:
            seen.add(key)
            stable.append(intent)
    return Analysis(
        tuple(stable[:4]) or (Intent(normalized, classify_intent(normalized)),),
        detect_vehicle_type(normalized),
    )


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
    """Classify corpus-supported legal, conversational, and refused requests."""
    lowered = text.casefold()
    if re.search(r"\b(hello|hi|xin chào|cảm ơn|tạm biệt)\b", lowered):
        return "chitchat"
    if re.search(r"\b(google|web|internet|trên mạng|tin tức)\b", lowered):
        return "web"
    if re.search(r"\b(?:nd|tt)-\d+-\d{4}__dieu-\d+(?:__khoan-\d+)?(?:__diem-[a-z])?\b", lowered):
        return "legal"
    # Reject clearly foreign legal domains before broad words such as “điều” or
    # “phạt” can make an incidental traffic mention look in scope.
    if _is_dominantly_nontraffic(lowered):
        return "out_of_scope"
    if re.search(
        r"\b(luật|điều|khoản|nghị định|thông tư|phạt|giao thông|đường bộ|"
        r"tốc độ|km/?h|khu vực đông dân cư|vượt đèn đỏ|điện thoại|lái xe|"
        r"không đội mũ bảo hiểm|trừ điểm|tước quyền|tạm giữ|phương tiện|"
        r"đai an toàn|thắt dây|dây an toàn|số người|chở người|"
        r"chở tối đa|tối đa bao nhiêu người|"
        r"đèn chiếu sáng|bật đèn|còi|bấm còi|đi ngược chiều|ngược chiều|"
        r"làn đường|lấn làn|rượu|bia|nồng độ cồn|ma túy|chất kích thích|"
        r"mũ bảo hiểm|thiết bị điện tử|điện tử|đèn tín hiệu|xi nhan|"
        r"chuyển hướng|rẽ)\b",
        lowered,
    ):
        return "legal"
    return "out_of_scope"


_NONTRAFFIC_TERMS = (
    r"thuế|thuế vụ|nhà đất|bất động sản|đất đai|xây dựng",
    r"hình sự|tội phạm|giết người|trộm cắp|ma túy hình sự",
    r"hôn nhân|ly hôn|lao động|hợp đồng|bảo hiểm xã hội",
)
_TRAFFIC_CONTEXT_TERMS = (
    r"giao thông|đường bộ|lái xe|phương tiện|xe máy|ô tô|mô tô|"
    r"giấy phép lái xe|gplx|biển báo|làn đường|đèn tín hiệu|"
    r"vượt đèn đỏ|nồng độ cồn|mũ bảo hiểm|tốc độ",
)


def _is_dominantly_nontraffic(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in _NONTRAFFIC_TERMS) and not any(
        re.search(pattern, text, flags=re.I) for pattern in _TRAFFIC_CONTEXT_TERMS
    )


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


def _clean_fences(content: str) -> str:
    value = content.strip()
    if value.startswith("```") and value.endswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    return value.strip()


def _history_for_prompt(history: object) -> str:
    if not isinstance(history, (list, tuple)):
        return ""
    lines: list[str] = []
    for item in list(history)[-6:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = " ".join(str(item.get("content", "")).split())[:500]
        if role in {"user", "assistant"} and content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _chat_completion(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    response_format: dict[str, Any],
) -> Any:
    """Call the provider with a dynamic JSON-mode payload.

    ``response_format`` is built from the pydantic schema at runtime, so the
    SDK's literal-typed overloads cannot describe it; the payload is therefore
    passed through a plain mapping instead of the typed keyword arguments.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": response_format,
        "max_tokens": 700,
    }
    return client.chat.completions.create(**payload)


def _normalized_model_payload(content: str, fallback_query: str, question: str) -> AnalyzerOutput:
    raw = json.loads(_clean_fences(content))
    if not isinstance(raw, dict):
        raise ValueError("invalid analyzer payload")
    standalone = str(raw.get("standalone_query") or "").strip() or fallback_query
    expanded_raw = raw.get("expanded_queries")
    expanded = (
        [str(item).strip() for item in expanded_raw if str(item).strip()]
        if isinstance(expanded_raw, list)
        else []
    )
    traffic = " ".join((str(raw.get("category", "")), standalone, question)).casefold()
    category_value = str(raw.get("category", "")).casefold()
    category: Category
    if any(
        term in traffic
        for term in ("giao thông", "phạt", "xe", "luật", "nghị định", "điều", "legal")
    ):
        category = "legal_rag"
    elif any(
        term in category_value for term in ("chào", "hello", "cảm ơn", "chitchat", "chit_chat")
    ) and any(
        term in question.casefold() for term in ("chào", "hello", "hi ", "cảm ơn", "bạn là ai")
    ):
        # The model labels any off-topic question as small talk; only accept that
        # label when the question itself greets, so weather/off-topic questions
        # keep routing to out_of_scope instead of a greeting.
        category = "chitchat"
    else:
        category = "out_of_scope"
    vehicle_value = " ".join(str(raw.get("vehicle_type", "")).casefold().split())
    vehicle = cast(
        VehicleType, _VEHICLE_ALIASES.get(vehicle_value) or detect_vehicle_type(standalone)
    )
    if vehicle not in CANONICAL_VEHICLE_CATEGORIES:
        vehicle = "any"
    intent_value = str(raw.get("intent", "")).casefold()
    canonical_intents = {"penalty", "rule", "procedure", "definition", "list", "mixed"}
    intent: IntentValue
    if intent_value in canonical_intents:
        intent = cast(IntentValue, intent_value)
    elif any(
        term in f"{intent_value} {question.casefold()}"
        for term in ("phạt", "tiền", "trừ điểm", "tước")
    ):
        intent = "penalty"
    elif len(expanded) >= 2:
        intent = "mixed"
    else:
        intent = "rule"
    return AnalyzerOutput(
        category=category,
        intent=intent,
        vehicle_type=vehicle,
        standalone_query=standalone,
        expanded_queries=expanded[:3] or [standalone],
    )


def _deterministic_request(question: str, history: object) -> RequestAnalysis:
    standalone = resolve_vehicle_followup(question, history)
    category_name = classify_intent(standalone)
    category = (
        "chitchat"
        if category_name == "chitchat"
        else "out_of_scope"
        if category_name in {"web", "out_of_scope"}
        else "legal_rag"
    )
    frames = analyze_question(standalone)
    expanded = tuple(item.text for item in frames.intents if item.kind == "legal")[:3]
    if not expanded:
        expanded = (standalone,)
    lowered = standalone.casefold()
    intent = (
        "mixed"
        if len(frames.intents) >= 2
        else "penalty"
        if re.search(r"phạt|mức phạt|trừ điểm|tước", lowered)
        else "rule"
    )
    return RequestAnalysis(
        category=category,
        intent=intent,
        vehicle_type=detect_vehicle_type(standalone),
        standalone_query=standalone or question or " ",
        expanded_queries=expanded,
        frames=frames,
        source="deterministic",
    )


def build_analyzer_prompt(question: str, history: object = ()) -> str:
    """Build the strict-JSON analyzer prompt, including bounded chat history."""
    prompt = (
        "Trả về DUY NHẤT một object JSON, không markdown, không giải thích, đúng các khóa "
        "category, intent, vehicle_type, standalone_query, expanded_queries. "
        "Nếu câu hỏi ngắn như 'Còn xe máy thì sao?' hoặc 'Vậy còn ô tô?' nối tiếp "
        "một lượt pháp luật, category phải là legal_rag và standalone_query phải "
        "tự chứa hành vi vi phạm từ lịch sử. Với follow-up ngắn, standalone_query "
        "PHẢI dùng đúng hành vi vi phạm từ lượt pháp luật gần nhất và CHỈ thay thế "
        "hạng xe được nêu trong follow-up; tuyệt đối không được tự tạo hành vi mới "
        "hoặc ghép hạng xe với hành vi chưa từng đi cùng nhau trong lịch sử. "
        "category chỉ legal_rag/chitchat/out_of_scope; intent chỉ "
        "penalty/rule/procedure/definition/list/mixed; vehicle_type chỉ "
        "car/motorcycle/bicycle/specialized/any. "
        "expanded_queries tối đa 3 câu, mỗi câu ngắn gọn và độc lập và PHẢI giữ nguyên "
        "phạm vi câu hỏi: không được thêm tình tiết như địa điểm, loại đường, thời gian "
        "hay tình huống mà câu hỏi không nêu. "
    )
    for message in list(history)[-6:] if isinstance(history, (list, tuple)) else []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "user"))
        content = str(message.get("content", "")).strip()[:500]
        if content:
            prompt += f"\n{role}: {content}"
    return prompt + f"\n\nCâu hỏi hiện tại: {question}"


def analyze_request(
    question: str,
    history: object = (),
    *,
    model: ModelCallable | object | None = None,
    deadline: float | None = None,
    clock: object | None = None,
) -> RequestAnalysis:
    """Analyze a request, falling back deterministically on any model failure."""
    fallback = _deterministic_request(question, history)
    try:
        now = clock if callable(clock) else time.monotonic
        settings = get_generation_settings()
        remaining = deadline - now() if deadline is not None else 15.0
        timeout = min(float(getattr(settings, "analyzer_timeout_seconds", 15.0)), remaining)
        if timeout <= 0:
            return fallback
        prompt = build_analyzer_prompt(question, history)
        if model is not None:
            if hasattr(model, "invoke"):
                response = model.invoke(prompt)
            elif callable(model):
                response = model(prompt)
            else:
                return fallback
            content = getattr(response, "content", response)
        else:
            if not settings.openrouter_api_key:
                return fallback
            client = OpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                max_retries=0,
                timeout=timeout,
            )
            request_format: dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "analyzer",
                    "strict": True,
                    "schema": AnalyzerOutput.model_json_schema(),
                },
            }
            messages: list[dict[str, str]] = [
                {"role": "system", "content": "Chỉ xuất JSON hợp lệ theo schema."},
                {"role": "user", "content": prompt},
            ]
            model_name = getattr(settings, "analyzer_model", "") or settings.model
            try:
                response = _chat_completion(
                    client,
                    model=model_name,
                    messages=messages,
                    response_format=request_format,
                )
            except Exception:
                response = _chat_completion(
                    client,
                    model=model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
            content = response.choices[0].message.content
        if not isinstance(content, str):
            raise ValueError("invalid analyzer response")
        parsed = _normalized_model_payload(content, fallback.standalone_query, question)
        standalone = parsed.standalone_query.strip()
        resolved = resolve_vehicle_followup(question, history)
        if resolved != question and classify_intent(resolved) == "legal":
            standalone = resolved
        resolved_is_legal = classify_intent(resolved) == "legal"
        category = (
            "legal_rag"
            if parsed.category == "out_of_scope" and resolved_is_legal
            else parsed.category
        )
        queries: list[str] = []
        for query in parsed.expanded_queries:
            normalized = query.strip()
            if normalized and normalized.casefold() not in {item.casefold() for item in queries}:
                queries.append(normalized)
        if not queries:
            queries = [standalone]
        return RequestAnalysis(
            category=category,
            intent=parsed.intent,
            vehicle_type=parsed.vehicle_type,
            standalone_query=standalone,
            expanded_queries=tuple(queries[:3]),
            frames=analyze_question(standalone),
            source="model",
        )
    except Exception:
        return fallback


__all__ = [
    "Analysis",
    "AnalyzerOutput",
    "CANONICAL_VEHICLE_CATEGORIES",
    "Intent",
    "RequestAnalysis",
    "VEHICLE_LABELS",
    "analyze_question",
    "analyze_request",
    "classify_intent",
    "detect_vehicle_type",
    "detect_vehicle_types",
    "normalize_vehicle_metadata",
    "resolve_vehicle_followup",
]
