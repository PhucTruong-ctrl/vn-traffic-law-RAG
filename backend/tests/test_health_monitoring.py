from fastapi.testclient import TestClient

from app.main import app
from app.observability.health import Metrics


def test_metrics_are_prometheus_safe_and_bounded():
    metrics = Metrics()
    metrics.inc("requests", {"component": "api", "status": "ok", "secret": "no"})
    metrics.observe("latency", 0.5, {"operation": "search"})
    output = metrics.prometheus()
    assert 'requests{component="api",status="ok"} 1' in output
    assert "secret" not in output
    assert "latency_count{operation=\"search\"} 1" in output


def test_health_endpoints_return_safe_shapes(monkeypatch):
    monkeypatch.setattr("app.observability.health._db", lambda: None)
    monkeypatch.setattr("app.observability.health._qdrant", lambda: None)
    monkeypatch.setattr("app.observability.health._provider", lambda: None)
    response = TestClient(app).get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert set(body["checks"]) == {"db", "retrieval", "provider"}
    assert "password" not in json.dumps(body).lower()
