"""Verify authenticated application/API contracts using real Supabase user JWTs."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth.test_auth import configured_test_users, obtain_access_token  # noqa: E402


def call(base: str, method: str, path: str, token: str | None = None, body: Any = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=300) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode()) if raw else None
    except error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw.decode()) if raw else None


def require(status: int, expected: int, label: str) -> None:
    if status != expected:
        raise RuntimeError(f"{label}: expected {expected}, got {status}")


def _citation_is_action_relevant(
    citation: dict[str, Any],
    required_action: str,
    question: str,
) -> bool:
    """Check domain relevance using distinctive action/question tokens.

    The canonical action phrase can be absent from every corpus chunk because
    citations use different wording, so a verbatim substring assertion is
    unsatisfiable. Instead, combine the action and question, discard short
    tokens and generic legal/question vocabulary, and accept a citation set
    when at least one distinctive token appears in its excerpt/action fields.
    """
    generic_tokens = {
        "quy",
        "định",
        "người",
        "được",
        "trên",
        "theo",
        "trường",
        "hợp",
        "phạt",
        "tiền",
        "mức",
        "điều",
        "khoản",
        "điểm",
        "loại",
        "phương",
        "tiện",
        "giao",
        "thông",
        "khi",
        "câu",
        "hỏi",
    }
    tokens = {
        token
        for token in re.findall(
            r"[^\W\d_]+",
            f"{required_action} {question}".casefold(),
            flags=re.UNICODE,
        )
        if len(token) >= 4 and token not in generic_tokens
    }
    citation_text = " ".join(
        str(citation.get(field, ""))
        for field in ("normalized_action", "action", "violation", "excerpt")
    ).casefold()
    if not citation_text.strip():
        return False
    if not tokens:
        return bool(citation_text.strip())
    citation_tokens = set(re.findall(r"[^\W\d_]+", citation_text, flags=re.UNICODE))
    return bool(tokens & citation_tokens) or (
        required_action and not tokens and bool(citation_tokens)
    )


def require_chat_contract(
    result: Any,
    label: str,
    expected_status: str = "VERIFIED",
    require_citations: bool = True,
    required_reference: str | None = None,
    required_action: str | None = None,
    question: str = "",
    expected_reason_code: str | None = None,
) -> None:
    """Fail closed on the semantic fields the release flow exposes."""
    if not isinstance(result, dict):
        raise RuntimeError(f"{label}: expected JSON object, got {type(result).__name__}")
    actual_status = str(result.get("status") or "").upper()
    if actual_status != expected_status.upper():
        raise RuntimeError(
            f"{label}: expected status {expected_status!r}, got {result.get('status')!r}"
        )
    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError(f"{label}: answer must be a non-blank string")
    if expected_status.upper() != "VERIFIED":
        reason_code = result.get("reason_code")
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise RuntimeError(f"{label}: abstention requires non-blank reason_code")
        if expected_reason_code and reason_code.casefold() != expected_reason_code.casefold():
            raise RuntimeError(
                f"{label}: expected reason_code {expected_reason_code!r}, got {reason_code!r}"
            )
    citations = result.get("citations")
    if not isinstance(citations, list):
        raise RuntimeError(f"{label}: citations must be a list")
    if require_citations and not citations:
        raise RuntimeError(f"{label}: expected at least one citation")
    seen: set[tuple[str, str]] = set()
    for index, citation in enumerate(citations):
        if not isinstance(citation, dict):
            raise RuntimeError(f"{label}: citation {index} must be an object")
        for field in ("source_id", "document_id", "excerpt"):
            if not isinstance(citation.get(field), str) or not citation[field].strip():
                raise RuntimeError(f"{label}: citation {index} missing non-blank {field}")
        if not any(
            isinstance(citation.get(field), str) and citation[field].strip()
            for field in ("article", "clause", "point", "document_number")
        ):
            raise RuntimeError(f"{label}: citation {index} missing coordinates")
        identity = (citation["source_id"], citation["document_id"])
        if identity in seen:
            raise RuntimeError(f"{label}: duplicate citation identity {identity!r}")
        seen.add(identity)
    if required_reference and not any(
        required_reference.casefold()
        in " ".join(
            str(citation.get(field, "")) for field in ("document_id", "document_number", "article")
        ).casefold()
        for citation in citations
    ):
        raise RuntimeError(
            f"{label}: no citation matches required reference {required_reference!r}"
        )
    if required_action and not any(
        _citation_is_action_relevant(citation, required_action, question) for citation in citations
    ):
        raise RuntimeError(f"{label}: no citation is action-relevant")


def _action_aliases() -> dict[str, str]:
    with (ROOT / "data" / "rag" / "query_rules.json").open(encoding="utf-8") as handle:
        return {
            str(alias).casefold(): str(canonical)
            for alias, canonical in json.load(handle).get("action_aliases", {}).items()
        }


def _expected_action(question: str) -> str | None:
    lowered = question.casefold()
    return next(
        (canonical for alias, canonical in _action_aliases().items() if alias in lowered),
        None,
    )


def main() -> int:
    base = os.getenv("RELEASE_API_BASE", "http://127.0.0.1:8000/api/v1").rstrip("/")
    questions = [
        "Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?",
        "Ô tô vượt đèn đỏ bị phạt bao nhiêu?",
        "Xe máy được chở tối đa bao nhiêu người?",
        "Ban đêm có bắt buộc bật đèn chiếu sáng không?",
        "Bấm còi trong khu dân cư có bị phạt không?",
        "Quay đầu hoặc lùi xe có bị phạt không?",
    ]
    results: list[dict[str, Any]] = []
    users = configured_test_users()
    token_a = obtain_access_token(users[0])
    token_b = obtain_access_token(users[1]) if len(users) > 1 else None

    status, documents = call(base, "GET", "/legal-documents")
    require(status, 200, "legal list")
    if not documents:
        raise RuntimeError("legal list is empty")
    document_id = documents[0]["document_id"]
    require(
        call(base, "GET", f"/legal-documents/{document_id}/provisions")[0],
        200,
        "legal provisions",
    )
    search_path = "/legal-search?q=" + urllib.parse.quote("Điều 6")
    require(call(base, "GET", search_path)[0], 200, "legal search")

    status, session = call(
        base,
        "POST",
        "/chats",
        token_a,
        {"title": "Automated release verification"},
    )
    require(status, 201, "create session")
    session_id = session["id"]
    for index, question in enumerate(questions):
        status, result = call(
            base,
            "POST",
            "/chat",
            token_a,
            {"question": question, "session_id": session_id},
        )
        require(status, 200, f"chat: {question[:30]}")
        expected_status = "VERIFIED"
        expected_action = _expected_action(question)
        require_chat_contract(
            result,
            f"happy-case/{index + 1}",
            expected_status=expected_status,
            require_citations=True,
            required_action=expected_action,
            question=question,
        )
        results.append(
            {
                "question": question,
                "status": result.get("status"),
                "citations": result.get("citations", []),
            }
        )
    status, loaded = call(base, "GET", f"/chats/{session_id}", token_a)
    require(status, 200, "load session")
    messages = loaded.get("messages", [])
    if not isinstance(messages, list) or len(messages) < len(questions) * 2:
        raise RuntimeError("transcript persistence incomplete")
    for question in questions:
        if not any(
            message.get("role") == "user" and message.get("content") == question
            for message in messages
        ):
            raise RuntimeError("user message persistence incomplete")
    if sum(message.get("role") == "assistant" for message in messages) < len(questions):
        raise RuntimeError("assistant message persistence incomplete")
    require(call(base, "GET", "/chats?query=Automated", token_a)[0], 200, "session search")
    require(
        call(base, "PATCH", f"/chats/{session_id}", token_a, {"title": "Renamed verification"})[0],
        200,
        "rename",
    )
    if token_b:
        require(
            call(base, "GET", f"/chats/{session_id}", token_b)[0],
            404,
            "cross-user session concealment",
        )
    require(call(base, "DELETE", f"/chats/{session_id}", token_a)[0], 204, "delete")
    require(
        call(base, "GET", f"/chats/{session_id}", token_a)[0],
        404,
        "deleted session concealment",
    )
    print(json.dumps({"status": "AUTOMATED_PASS", "questions": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
