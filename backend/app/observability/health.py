"""Dependency health checks and Prometheus-compatible metrics."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from sqlalchemy import text

from app.api.db import get_engine
from app.config import get_embedding_settings, get_qdrant_settings
from app.retrieval.qdrant_store import PROVISION_ALIAS


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    status: str
    detail: str | None = None

    def as_dict(self) -> dict[str, str]:
        value = {"status": self.status}
        if self.detail:
            value["detail"] = self.detail
        return value


class Metrics:
    """Small process-local counter/histogram registry with safe labels."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
        self._durations: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = {}

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> tuple[str, tuple[tuple[str, str], ...]]:
        clean = tuple(sorted((k, v) for k, v in (labels or {}).items() if k in {"component", "operation", "status"}))
        return name, clean

    def inc(self, name: str, labels: dict[str, str] | None = None, value: int = 1) -> None:
        with self._lock:
            key = self._key(name, labels)
            self._counters[key] = self._counters.get(key, 0) + value

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            key = self._key(name, labels)
            self._durations.setdefault(key, []).append(value)

    def prometheus(self) -> str:
        with self._lock:
            lines: list[str] = []
            for (name, labels), value in sorted(self._counters.items()):
                suffix = _labels(labels)
                lines.append(f"{name}{suffix} {value}")
            for (name, labels), values in sorted(self._durations.items()):
                suffix = _labels(labels)
                lines.append(f"{name}_count{suffix} {len(values)}")
                lines.append(f"{name}_sum{suffix} {sum(values):.6f}")
            return "\n".join(lines) + ("\n" if lines else "")


def _labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f'{k}="{v.replace(chr(92), chr(92)+chr(92)).replace(chr(34), chr(92)+chr(34))}"' for k, v in labels) + "}"


metrics = Metrics()

def _run(name: str, check: Callable[[], None]) -> HealthCheck:
    started = time.perf_counter()
    try:
        check()
    except Exception:
        metrics.inc("vnlaw_health_checks_total", {"component": name, "status": "unhealthy"})
        return HealthCheck(name, "degraded")
    finally:
        metrics.observe("vnlaw_health_check_duration_seconds", time.perf_counter() - started, {"component": name})
    metrics.inc("vnlaw_health_checks_total", {"component": name, "status": "healthy"})
    return HealthCheck(name, "healthy")


def _db() -> None:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


def _qdrant() -> None:
    from app.retrieval.qdrant_store import ensure_qdrant_collection
    client = ensure_qdrant_collection()
    client.get_collection(PROVISION_ALIAS)


def _provider() -> None:
    settings = get_embedding_settings()
    if settings.provider not in {"gemini", "jina"}:
        raise RuntimeError("unsupported provider")
    if not (settings.gemini_api_key if settings.provider == "gemini" else settings.jina_api_key):
        raise RuntimeError("provider not configured")


def readiness() -> dict[str, Any]:
    unhealthy = [c.name for c in checks if c.status != "healthy"]
    return {
        "status": "ready" if not unhealthy else "degraded",
        "checks": {c.name: c.as_dict() for c in checks},
    }
