"""Server-only bootstrap and password authentication for release verification."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class TestUserCredentials:
    email: str
    password: str


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for authenticated release verification")
    return value


def configured_test_users() -> tuple[TestUserCredentials, ...]:
    users = [TestUserCredentials(_required("TEST_USER_EMAIL"), _required("TEST_USER_PASSWORD"))]
    email_b = os.getenv("TEST_USER_B_EMAIL", "").strip()
    password_b = os.getenv("TEST_USER_B_PASSWORD", "").strip()
    if bool(email_b) != bool(password_b):
        raise RuntimeError("TEST_USER_B_EMAIL and TEST_USER_B_PASSWORD must be supplied together")
    if email_b:
        users.append(TestUserCredentials(email_b, password_b))
    return tuple(users)


def _supabase() -> tuple[str, str]:
    url = _required("SUPABASE_URL").rstrip("/")
    service_key = _required("SUPABASE_SERVICE_ROLE_KEY")
    return url, service_key


def _request(method: str, url: str, *, headers: dict[str, str], json: Any = None) -> Any:
    response = httpx.request(method, url, headers=headers, json=json, timeout=20)
    if response.is_error:
        raise RuntimeError(f"Supabase test-auth request failed ({response.status_code})")
    return response.json() if response.content else None


def ensure_test_user(user: TestUserCredentials) -> dict[str, Any]:
    """Create/update one user using service-role admin API; never returns a token."""
    url, service_key = _supabase()
    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
    users = _request("GET", f"{url}/auth/v1/admin/users?email={user.email}", headers=headers)
    existing = next(
        (item for item in users.get("users", []) if item.get("email") == user.email), None
    )
    payload = {"email": user.email, "password": user.password, "email_confirm": True}
    if existing:
        return _request(
            "PUT", f"{url}/auth/v1/admin/users/{existing['id']}", headers=headers, json=payload
        )
    return _request("POST", f"{url}/auth/v1/admin/users", headers=headers, json=payload)


def obtain_access_token(user: TestUserCredentials | None = None) -> str:
    """Ensure user exists, then sign in through normal password flow."""
    credentials = user or configured_test_users()[0]
    ensure_test_user(credentials)
    url, anon_key = _supabase()
    result = _request(
        "POST",
        f"{url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": credentials.email, "password": credentials.password},
    )
    token = result.get("access_token") if isinstance(result, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("Supabase password sign-in returned no access token")
    return token


__all__ = [
    "TestUserCredentials",
    "configured_test_users",
    "ensure_test_user",
    "obtain_access_token",
]
