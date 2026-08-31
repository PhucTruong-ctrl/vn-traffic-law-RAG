"""Suite B embedding benchmark runner (VNLRAG-98).

The runner is deliberately fixture-friendly, but refuses to evaluate anything
other than the complete 40-record development set.  VNLRAG-92 must therefore
be complete before a run can create evaluation artifacts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.gold_set import GoldRecord, validate_record
from app.evaluation.metrics.retrieval import evaluate_retrieval
from app.evaluation.run import EvaluationRunManifest, EvaluationRunWriter
from app.retrieval.qdrant_store import build_collection_config
from app.storage.object_storage import ObjectStoragePort

SUITE_NAME = "suite-b"
DEVELOPMENT_SET_SIZE = 40
PREREQUISITE = "VNLRAG-92"


@dataclass(frozen=True, slots=True)
class EmbeddingVariant:
    """Immutable embedding configuration recorded in a benchmark manifest."""

    key: str
    name: str
    model_id: str
    vector_size: int
    collection: str


E1 = EmbeddingVariant("E1", "Gemini Embedding 2", "gemini-embedding-2", 768, "suite_b_e1_v1")
E2 = EmbeddingVariant(
    "E2", "Jina Embeddings v5 text-nano", "jina-embeddings-v5-text-nano", 768, "suite_b_e2_v1"
)
E3 = EmbeddingVariant(
    "E3", "Jina Embeddings v5 text-small", "jina-embeddings-v5-text-small", 1024, "suite_b_e3_v1"
)
VARIANTS: tuple[EmbeddingVariant, ...] = (E1, E2, E3)
VARIANT_BY_KEY = {variant.key: variant for variant in VARIANTS}


class SuiteBPrerequisiteError(RuntimeError):
    """Raised when the complete development set is not available."""


def variant_descriptor(key: str) -> EmbeddingVariant:
    try:
        return VARIANT_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"unknown Suite B variant: {key}") from exc


def collection_config(variant: EmbeddingVariant) -> dict[str, Any]:
    """Return isolated collection settings; never changes the active alias."""
    return build_collection_config(dense_vector_size=variant.vector_size)


def _records(records: Sequence[GoldRecord | Mapping[str, Any]]) -> list[GoldRecord]:
    parsed = [
        record if isinstance(record, GoldRecord) else validate_record(dict(record))
        for record in records
    ]
    if len(parsed) != DEVELOPMENT_SET_SIZE:
        raise SuiteBPrerequisiteError(
            f"{PREREQUISITE} incomplete: Suite B requires exactly {DEVELOPMENT_SET_SIZE} "
            f"development records, got {len(parsed)}"
        )
    return parsed


def run_suite_b(
    records: Sequence[GoldRecord | Mapping[str, Any]],
    retrieve: Callable[[GoldRecord, EmbeddingVariant], Mapping[str, Any]],
    *,
    session: Session,
    storage: ObjectStoragePort,
    writer: EvaluationRunWriter | None = None,
    variants: Sequence[str] = ("E1", "E2", "E3"),
    git_commit: str = "unknown",
    corpus_version: str = "unknown",
    corpus_hash: str = "unknown",
    gold_set_version: str = "unknown",
    gold_set_hash: str = "unknown",
) -> list[str]:
    """Run deterministic fixtures for each embedding variant.

    ``retrieve`` may be a deterministic fake in unit tests. Its mapping must
    contain ``retrieved`` (or ``results``); optional ``latency_ms``,
    ``token_usage``, ``estimated_cost``, ``provider``, and ``error`` fields are
    retained verbatim in the raw result.
    """
    gold = _records(records)
    selected = [variant_descriptor(key) for key in variants]
    run_writer = writer or EvaluationRunWriter()
    run_ids: list[str] = []
    for variant in selected:
        manifest = EvaluationRunManifest(
            git_commit=git_commit,
            corpus_version=corpus_version,
            corpus_hash=corpus_hash,
            gold_set_version=gold_set_version,
            gold_set_hash=gold_set_hash,
            suite=SUITE_NAME,
            variant=variant.key,
            config_snapshot={
                "collection": variant.collection,
                "dense_vector_size": variant.vector_size,
            },
            model_ids={"embedding": variant.model_id},
        )
        run_id = run_writer.start(manifest, session=session, storage=storage)
        run_ids.append(run_id)
        metric_records: list[dict[str, Any]] = []
        try:
            for record in gold:
                outcome = dict(retrieve(record, variant))
                retrieved = outcome.get("retrieved", outcome.get("results", []))
                if not isinstance(retrieved, Sequence) or isinstance(retrieved, (str, bytes)):
                    raise ValueError("fixture outcome retrieved must be a sequence")
                metric_records.append(
                    {
                        "id": record.id,
                        "category": record.category.value,
                        "retrieved": list(retrieved),
                        "relevant": record.expected_provision_ids,
                    }
                )
                run_writer.append_result(
                    run_id,
                    {
                        "question_id": record.id,
                        "input": {"question": record.question},
                        "retrieval": outcome,
                        "output": {},
                        "metrics": {},
                    },
                    session=session,
                )
            metrics = {
                name: report.__dict__
                for name, report in evaluate_retrieval(metric_records).items()
            }
            run_writer.finish(
                run_id,
                status="COMPLETED",
                metrics=metrics,
                metric_availability={name: "AVAILABLE" for name in metrics},
                session=session,
                storage=storage,
            )
        except Exception as exc:
            run_writer.finish(
                run_id,
                status="FAILED",
                metrics={},
                metric_availability={"retrieval": f"ABSENT_PROVIDER_FAILURE: {exc}"},
                session=session,
                storage=storage,
            )
            raise
    return run_ids


__all__ = [
    "DEVELOPMENT_SET_SIZE",
    "E1",
    "E2",
    "E3",
    "EmbeddingVariant",
    "PREREQUISITE",
    "SUITE_NAME",
    "SuiteBPrerequisiteError",
    "VARIANTS",
    "collection_config",
    "run_suite_b",
    "variant_descriptor",
]
