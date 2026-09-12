"""Verify authenticated application/API contracts using real Supabase user JWTs."""

from __future__ import annotations

import json
import os
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


def require_chat_contract(
    result: Any,
    label: str,
    *,
    expected_status: str = "complete",
    require_citations: bool = True,
    required_reference: str | None = None,
) -> None:
    """Fail closed on the semantic fields the release flow exposes."""
    if not isinstance(result, dict):
        raise RuntimeError(f"{label}: expected JSON object, got {type(result).__name__}")
    if result.get("status") != expected_status:
        raise RuntimeError(
            f"{label}: expected status {expected_status!r}, got {result.get('status')!r}"
        )
    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError(f"{label}: answer must be a non-blank string")
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
        identity = (citation["source_id"], citation["document_id"])
        if identity in seen:
            raise RuntimeError(f"{label}: duplicate citation identity {identity!r}")
        seen.add(identity)
    if required_reference and not any(
        required_reference.casefold()
        in " ".join(
            str(citation.get(field, ""))
            for field in ("document_id", "document_number", "article")
        ).casefold()
        for citation in citations
    ):
        raise RuntimeError(
            f"{label}: no citation matches required reference {required_reference!r}"
        )
def main() -> int:
    base = os.getenv("RELEASE_API_BASE", "http://127.0.0.1:8000/api/v1").rstrip("/")
    questions = [
        "Đèn tín hiệu giao thông màu đỏ thì người tham gia giao thông phải làm gì theo Điều 6?",
        "Mức phạt nồng độ cồn đối với người điều khiển ô tô là bao nhiêu?",
        "Theo Điều 6 Nghị định 168, hành vi vượt đèn đỏ bị phạt thế nào?",
        "Đèn đỏ và nồng độ cồn: người lái ô tô bị xử lý ra sao?",
        "Thời tiết ngày mai ở Hà Nội thế nào?",
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
        if index == 0:
            require_chat_contract(result, "exact-reference/traffic-light", required_reference="168")
        elif index == 1:
            require_chat_contract(result, "alcohol/penalty")
        elif index == 2:
            require_chat_contract(result, "exact-reference/article-6", required_reference="168")
        elif index == 3:
            require_chat_contract(result, "multi-intent/traffic-light")
        else:
            require_chat_contract(
                result,
                "out-of-scope",
                expected_status="insufficient_evidence",
                require_citations=False,
            )
            if result.get("citations") != []:
                raise RuntimeError("out-of-scope: citations must be empty")
        results.append(
            {
                "question": question,
                "status": result.get("status"),
                "citations": result.get("citations", []),
            }
        )
    status, loaded = call(base, "GET", f"/chats/{session_id}", token_a)
    require(status, 200, "load session")
    if len(loaded.get("messages", [])) < len(questions) * 2:
        raise RuntimeError("transcript persistence incomplete")
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
