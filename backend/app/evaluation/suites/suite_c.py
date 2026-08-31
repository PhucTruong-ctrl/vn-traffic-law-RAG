"""Config-driven retrieval ablation runner (VNLRAG-61).

The validation set is a hard prerequisite: this module never pads, samples, or
runs a partial set.  Once the set is complete, callers provide the retrieval
callable and the existing :class:`EvaluationRunWriter` persists raw outcomes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.evaluation.gold_set import GoldRecord
from app.evaluation.metrics.retrieval import evaluate_retrieval
from app.evaluation.run import EvaluationRunManifest, EvaluationRunWriter

VALIDATION_SET_SIZE = 40


@dataclass(frozen=True)
class SuiteCVariant:
    """One cumulative retrieval composition, in benchmark order."""

    name: str
    additions: tuple[str, ...]


VARIANTS: tuple[SuiteCVariant, ...] = (
    SuiteCVariant("R1", ("legal_chunk", "dense")),
    SuiteCVariant("R2", ("legal_chunk", "dense", "sparse_rrf")),
    SuiteCVariant("R3", ("legal_chunk", "dense", "sparse_rrf", "normalization")),
    SuiteCVariant("R4", ("legal_chunk", "dense", "sparse_rrf", "normalization", "rewrite")),
    SuiteCVariant("R5", ("legal_chunk", "dense", "sparse_rrf", "normalization", "rewrite", "hyde")),
    SuiteCVariant(
        "R6",
        ("legal_chunk", "dense", "sparse_rrf", "normalization", "rewrite", "hyde", "reranker"),
    ),
    SuiteCVariant(
        "R7",
        (
            "legal_chunk",
            "dense",
            "sparse_rrf",
            "normalization",
            "rewrite",
            "hyde",
            "reranker",
            "parent_sibling",
        ),
    ),
    SuiteCVariant(
        "R8",
        (
            "legal_chunk",
            "dense",
            "sparse_rrf",
            "normalization",
            "rewrite",
            "hyde",
            "reranker",
            "parent_sibling",
            "cross_reference",
        ),
    ),
    SuiteCVariant(
        "R9",
        (
            "legal_chunk",
            "dense",
            "sparse_rrf",
            "normalization",
            "rewrite",
            "hyde",
            "reranker",
            "parent_sibling",
            "cross_reference",
            "temporal",
        ),
    ),
    SuiteCVariant(
        "R10",
        (
            "legal_chunk",
            "dense",
            "sparse_rrf",
            "normalization",
            "rewrite",
            "hyde",
            "reranker",
            "parent_sibling",
            "cross_reference",
            "temporal",
            "complete_pipeline",
        ),
    ),
)


class ValidationSetBlocked(RuntimeError):
    """Raised when VNLRAG-93's complete validation set is unavailable."""

    def __init__(self, actual: int) -> None:
        self.actual = actual
        super().__init__(
            f"Suite C requires exactly {VALIDATION_SET_SIZE} validation records; found {actual}"
        )


SUITE_C_VARIANTS = VARIANTS
VARIANT_CONFIGS = {variant.name: variant for variant in VARIANTS}


def validate_validation_set(
    records: Sequence[GoldRecord | Mapping[str, Any]],
) -> tuple[GoldRecord | Mapping[str, Any], ...]:
    """Return records unchanged, or block before any provider/storage work."""

    validated = tuple(records)
    if len(validated) != VALIDATION_SET_SIZE:
        raise ValidationSetBlocked(len(validated))
    return validated


Evaluator = Callable[[SuiteCVariant, GoldRecord | Mapping[str, Any]], Mapping[str, Any]]


def _record_id(record: GoldRecord | Mapping[str, Any], fallback: int) -> str:
    return record.id if isinstance(record, GoldRecord) else str(record.get("id", fallback))


def run_suite_c(
    records: Sequence[GoldRecord | Mapping[str, Any]],
    *,
    evaluator: Evaluator,
    writer: EvaluationRunWriter,
    manifest_for: Callable[[SuiteCVariant], EvaluationRunManifest],
    session: Any,
    storage: Any,
    variants: Sequence[SuiteCVariant | str] = VARIANTS,
) -> list[str]:
    """Run every configured variant and persist immutable per-query outcomes.

    ``evaluator`` owns retrieval wiring. Its returned mapping is copied into a
    JSON-safe result envelope, so provider failures remain raw results rather
    than disappearing from the run.
    """

    validation_records = validate_validation_set(records)
    selected = tuple(
        VARIANT_CONFIGS[variant] if isinstance(variant, str) else variant for variant in variants
    )
    unknown = [variant.name for variant in selected if variant.name not in VARIANT_CONFIGS]
    if unknown:
        raise ValueError(f"unknown Suite C variants: {unknown}")

    run_ids: list[str] = []
    for variant in selected:
        run_id = writer.start(manifest_for(variant), session=session, storage=storage)
        run_ids.append(run_id)
        try:
            metric_records: list[dict[str, object]] = []
            for index, record in enumerate(validation_records):
                try:
                    outcome = dict(evaluator(variant, record))
                except Exception as exc:
                    outcome = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
                writer.append_result(
                    run_id,
                    {
                        "question_id": _record_id(record, index),
                        "input": {
                            "question": record.question
                            if isinstance(record, GoldRecord)
                            else str(record.get("question", ""))
                        },
                        "retrieval": {
                            "variant": variant.name,
                            "config": {"features": list(variant.additions)},
                            "outcome": outcome,
                        },
                        "output": {},
                        "metrics": {},
                    },
                    session=session,
                )
                metric_records.append(
                    {
                        "id": _record_id(record, index),
                        "category": record.category.value
                        if isinstance(record, GoldRecord)
                        else str(record.get("category", "uncategorized")),
                        "retrieved": outcome.get("retrieved", outcome.get("provision_ids", [])),
                        "relevant": record.expected_provision_ids
                        if isinstance(record, GoldRecord)
                        else record.get("expected_provision_ids", []),
                    }
                )
            reports = evaluate_retrieval(metric_records)
            metrics = {
                name: {
                    "value": report.value,
                    "status": report.status,
                    "na_reason": report.na_reason,
                    "per_query": report.per_query,
                    "by_category": report.by_category,
                }
                for name, report in reports.items()
            }
            writer.finish(
                run_id,
                status="COMPLETED",
                metrics=metrics,
                metric_availability={
                    name: "computed" if report.value is not None else f"ABSENT_{report.na_reason}"
                    for name, report in reports.items()
                },
                session=session,
                storage=storage,
            )
        except Exception:
            writer.finish(
                run_id,
                status="FAILED",
                metrics={},
                metric_availability={"retrieval_metrics": "ABSENT_RUN_FAILURE"},
                session=session,
                storage=storage,
            )
            raise
    return run_ids


__all__ = [
    "VALIDATION_SET_SIZE",
    "SuiteCVariant",
    "SUITE_C_VARIANTS",
    "VARIANT_CONFIGS",
    "ValidationSetBlocked",
    "validate_validation_set",
    "run_suite_c",
]
