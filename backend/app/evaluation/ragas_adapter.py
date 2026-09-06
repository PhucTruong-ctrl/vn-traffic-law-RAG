"""Optional Ragas integration that never bypasses legal verification.

Ragas is used only for quality metrics.  Legal acceptance remains owned by the
verification boundary and is represented as an explicit filter in the adapter.
Unavailable dependencies, empty inputs, and unverified answers produce NA,
not fabricated scores.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .metrics.retrieval import MetricReport


@dataclass(frozen=True, slots=True)
class RagasEvaluation:
    metrics: dict[str, MetricReport]
    status: str
    reason: str | None = None


def _na(name: str, reason: str) -> MetricReport:
    return MetricReport.na(reason)


def evaluate_ragas(
    records: Sequence[Mapping[str, Any]],
    *,
    legal_verified_only: bool = True,
    evaluator: Any = None,
) -> RagasEvaluation:
    """Evaluate supplied records through an injected Ragas evaluator.

    The adapter deliberately does not import or instantiate provider clients.
    Callers must inject a compatible evaluator, making missing metrics explicit.
    Each record must carry ``verification_status == 'VALID'`` when the legal
    filter is enabled; rejected records are excluded rather than relabeled.
    """
    if not records:
        reason = "no evaluation records"
        return RagasEvaluation({"faithfulness": _na("faithfulness", reason), "answer_relevancy": _na("answer_relevancy", reason)}, "na", reason)
    eligible = [
        record
        for record in records
        if not legal_verified_only or record.get("verification_status") == "VALID"
    ]
    if not eligible:
        reason = "no legally verified records"
        return RagasEvaluation({"faithfulness": _na("faithfulness", reason), "answer_relevancy": _na("answer_relevancy", reason)}, "na", reason)
    if evaluator is None:
        reason = "ragas evaluator is not configured"
        return RagasEvaluation({"faithfulness": _na("faithfulness", reason), "answer_relevancy": _na("answer_relevancy", reason)}, "na", reason)
    try:
        raw = evaluator(eligible)
    except Exception as exc:
        reason = f"ragas evaluation failed: {type(exc).__name__}"
        return RagasEvaluation({"faithfulness": _na("faithfulness", reason), "answer_relevancy": _na("answer_relevancy", reason)}, "error", reason)
    if not isinstance(raw, Mapping):
        reason = "ragas evaluator returned a non-object"
        return RagasEvaluation({"faithfulness": _na("faithfulness", reason), "answer_relevancy": _na("answer_relevancy", reason)}, "error", reason)
    metrics: dict[str, MetricReport] = {}
    for name in ("faithfulness", "answer_relevancy"):
        value = raw.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[name] = MetricReport(float(value), status="ok")
        else:
            metrics[name] = _na(name, f"ragas metric {name!r} unavailable")
    return RagasEvaluation(metrics, "ok")


__all__ = ["RagasEvaluation", "evaluate_ragas"]
