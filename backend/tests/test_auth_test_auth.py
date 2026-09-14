from __future__ import annotations

import pytest

from app.auth.test_auth import TestUserCredentials as Credentials
from app.auth.test_auth import configured_test_users


def test_configured_test_users_requires_primary_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_USER_EMAIL", raising=False)
    monkeypatch.delenv("TEST_USER_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="TEST_USER_EMAIL"):
        configured_test_users()


def test_configured_test_users_requires_complete_secondary_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_USER_EMAIL", "a@example.test")
    monkeypatch.setenv("TEST_USER_PASSWORD", "password-a")
    monkeypatch.setenv("TEST_USER_B_EMAIL", "b@example.test")
    monkeypatch.delenv("TEST_USER_B_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="TEST_USER_B_EMAIL"):
        configured_test_users()


def test_configured_test_users_returns_credentials_without_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_USER_EMAIL", "a@example.test")
    monkeypatch.setenv("TEST_USER_PASSWORD", "password-a")
    monkeypatch.setenv("TEST_USER_B_EMAIL", "b@example.test")
    monkeypatch.setenv("TEST_USER_B_PASSWORD", "password-b")
    assert configured_test_users() == (
        Credentials("a@example.test", "password-a"),
        Credentials("b@example.test", "password-b"),
    )
