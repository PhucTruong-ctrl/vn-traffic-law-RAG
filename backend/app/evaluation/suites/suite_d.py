"""Config-driven Suite D generation/verification ablation (VNLRAG-100).

This module only composes an evaluator. It does not call providers or assert
that a run has been performed. The validation gold set is a hard prerequisite:
partial, malformed, or duplicate records are rejected before writer/evaluator
side effects.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.evaluation.gold_set import GoldRecord, validate_record
from app.evaluation.run import EvaluationRunManifest, EvaluationRunWriter

VALIDATION_SET_SIZE = 40


@dataclass(frozen=True, slots=True)
class SuiteDVariant:
    name: str
    layers: tuple[str, ...]


VARIANTS: tuple[SuiteDVariant, ...] = tuple(
    SuiteDVariant(name, layers)
    for name, layers in (
        ("G1", ("prompt",)),
        ("G2", ("prompt", "structured")),
        ("G3", ("prompt", "structured", "citation_id")),
        ("G4", ("prompt", "structured", "citation_id", "temporal")),
        ("G5", ("prompt", "structured", "citation_id", "temporal", "numeric")),
        ("G6", ("prompt", "structured", "citation_id", "temporal", "numeric", "claim_support")),
        (
            "G7",
            (
                "prompt",
                "structured",
                "citation_id",
                "temporal",
                "numeric",
                "claim_support",
                "evidence_completeness",
            ),
        ),
    )
)
VARIANT_CONFIGS = {variant.name: variant for variant in VARIANTS}
SUITE_D_VARIANTS = VARIANTS


class SuiteDPrerequisiteError(RuntimeError):
    def __init__(self, actual: int, *, reason: str = "count") -> None:
        self.actual = actual
        self.reason = reason
        detail = f"found {actual}" if reason == "count" else reason
        super().__init__(
            f"Suite D requires exactly {VALIDATION_SET_SIZE} approved validation records; {detail}"
        )


def validate_validation_set(
    records: Sequence[GoldRecord | Mapping[str, Any]],
) -> tuple[GoldRecord, ...]:
    if len(records) != VALIDATION_SET_SIZE:
        raise SuiteDPrerequisiteError(len(records))
    parsed: list[GoldRecord] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        try:
            value = validate_record(
                record.model_dump(mode="python") if isinstance(record, GoldRecord) else dict(record)
            )
        except Exception as exc:
            raise SuiteDPrerequisiteError(
                len(records), reason=f"record {index} is invalid: {exc}"
            ) from exc
        if value.id in seen:
            raise SuiteDPrerequisiteError(len(records), reason=f"duplicate record id: {value.id}")
        seen.add(value.id)
        if value.review_status.value != "APPROVED":
            raise SuiteDPrerequisiteError(len(records), reason=f"record {value.id} is not APPROVED")
        parsed.append(value)
    return tuple(parsed)


Evaluator = Callable[[SuiteDVariant, GoldRecord], Mapping[str, Any]]


def _record_id(record: GoldRecord, index: int) -> str:
    return record.id or str(index)


def _metric_payload(
    outcome: Mapping[str, Any], record: GoldRecord, question_id: str
) -> dict[str, Any]:
    metrics = outcome.get("metrics", {})
    if isinstance(metrics, Mapping):
        return dict(metrics)
    return {"status": "FAILED", "error": "metrics must be an object"}


def run_suite_d(
    records: Sequence[GoldRecord | Mapping[str, Any]],
    *,
    evaluator: Evaluator,
    writer: EvaluationRunWriter,
    manifest_for: Callable[[SuiteDVariant], EvaluationRunManifest],
    session: Any,
    storage: Any,
    variants: Sequence[SuiteDVariant | str] = VARIANTS,
) -> list[str]:
    """Run configured G variants using injected evaluator and immutable writer."""
    validation_records = validate_validation_set(records)
    selected: list[SuiteDVariant] = []
    for variant in variants:
        if isinstance(variant, str):
            try:
                selected.append(VARIANT_CONFIGS[variant])
            except KeyError as exc:
                raise ValueError(f"unknown Suite D variant: {variant}") from exc
        else:
            selected.append(variant)

    run_ids: list[str] = []
    for variant in selected:
        run_id = writer.start(manifest_for(variant), session=session, storage=storage)
        run_ids.append(run_id)
        failed = False
        try:
            for index, record in enumerate(validation_records):
                question_id = _record_id(record, index)
                try:
                    outcome = dict(evaluator(variant, record))
                except Exception as exc:
                    outcome = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
                if outcome.get("error") or str(outcome.get("status", "")).upper() in {
                    "FAILED",
                    "ERROR",
                }:
                    failed = True
                writer.append_result(
                    run_id,
                    {
                        "question_id": question_id,
                        "input": {
                            "question": record.question,
                            "query_date": record.query_date.isoformat()
                            if record.query_date
                            else None,
                        },
                        "retrieval": {
                            "variant": variant.name,
                            "config": {"layers": list(variant.layers)},
                        },
                        "output": outcome.get("output", {})
                        if isinstance(outcome.get("output", {}), Mapping)
                        else {},
                        "metrics": _metric_payload(outcome, record, question_id),
                    },
                    session=session,
                    storage=storage,
                )
            writer.finish(
                run_id,
                status="FAILED" if failed else "COMPLETED",
                metrics={"per_query": "stored_in_raw_results"},
                metric_availability={
                    "suite_d": "AVAILABLE" if not failed else "ABSENT_EVALUATOR_FAILURE"
                },
                session=session,
                storage=storage,
            )
        except Exception:
            if not failed:
                writer.finish(
                    run_id,
                    status="FAILED",
                    metrics={},
                    metric_availability={"suite_d": "ABSENT_RUN_FAILURE"},
                    session=session,
                    storage=storage,
                )
            raise
    return run_ids


__all__ = [
    "VALIDATION_SET_SIZE",
    "SuiteDVariant",
    "VARIANTS",
    "SUITE_D_VARIANTS",
    "VARIANT_CONFIGS",
    "SuiteDPrerequisiteError",
    "validate_validation_set",
    "run_suite_d",
]
