"""Tests for the active automatic-gate API contract."""

from __future__ import annotations

from fastapi.routing import APIRoute


def test_review_routes_are_not_part_of_the_mvp_api() -> None:
    """Human review API routes remain intentionally absent from the MVP."""
    from app.main import app

    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert not any(
        path == "/api/v1/review/items" or path.startswith("/api/v1/review/items/") for path in paths
    )
