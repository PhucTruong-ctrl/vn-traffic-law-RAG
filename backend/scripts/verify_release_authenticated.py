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


def main() -> int:
    base = os.getenv("RELEASE_API_BASE", "http://127.0.0.1:8000/api/v1").rstrip("/")
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
    questions = [
        "Ô tô vượt đèn đỏ bị phạt bao nhiêu?",
        "Mức phạt nồng độ cồn đối với người điều khiển ô tô là gì?",
        "Khoản 9 Điều 6 Nghị định 168/2024 quy định gì?",
        "Ô tô vượt đèn đỏ bị phạt tiền bao nhiêu và có bị trừ điểm giấy phép không?",
        "Hãy tư vấn luật giao thông của một quốc gia khác đang thay đổi hôm nay.",
    ]
    results = []
    for question in questions:
        status, result = call(
            base,
            "POST",
            "/chat",
            token_a,
            {"question": question, "session_id": session_id},
        )
        require(status, 200, f"chat: {question[:30]}")
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
