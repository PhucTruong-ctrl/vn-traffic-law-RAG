from fastapi.testclient import TestClient

from app.main import app


def test_active_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert {
        "/api/v1/chat",
        "/api/v1/health",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/chats",
        "/api/v1/legal-documents",
        "/api/v1/legal-search",
    } <= paths
    assert not any(path.startswith("/api/v1/documents") for path in paths)


def test_health_live() -> None:
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
