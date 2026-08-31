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

from app.config import get_settings
from app.evaluation.gold_set import GoldRecord, validate_record
from app.evaluation.metrics.retrieval import evaluate_retrieval
from app.evaluation.run import EvaluationRunManifest, EvaluationRunWriter
from app.retrieval.qdrant_store import CollectionConfig, build_collection_config
from app.storage.object_storage import ObjectStoragePort

DOCUMENT_IR_SCHEMA_VERSION = "document-ir-v2"
FALLBACK_PROMPT_VERSIONS = {
    "query_analyzer": "1",
    "query_rewriter": "1",
    "hyde": "1",
    "generator": "1",
    "claim_verifier": "1",
}

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


def collection_config(variant: EmbeddingVariant) -> CollectionConfig:
    """Return isolated collection settings; never changes the active alias."""
    return build_collection_config(dense_vector_size=variant.vector_size)


def _records(records: Sequence[GoldRecord | Mapping[str, Any]]) -> list[GoldRecord]:
    parsed = [
        validate_record(record.model_dump(mode="python"))
        if isinstance(record, GoldRecord)
        else validate_record(dict(record))
        for record in records
    ]
    if len(parsed) != DEVELOPMENT_SET_SIZE:
        raise SuiteBPrerequisiteError(
            f"{PREREQUISITE} incomplete: Suite B requires exactly {DEVELOPMENT_SET_SIZE} "
            f"development records, got {len(parsed)}"
        )
    return parsed


def _manifest_provenance() -> tuple[dict[str, str], dict[str, str], str]:
    settings = get_settings()
    prompt_versions = {
        name: getattr(settings, f"fallback_prompt_version_{name}", "") or version
        for name, version in FALLBACK_PROMPT_VERSIONS.items()
    }
    return (
        prompt_versions,
        {"document_ir_schema": DOCUMENT_IR_SCHEMA_VERSION},
        settings.prompt_source,
    )


def _metric_availability(reports: Mapping[str, Any]) -> dict[str, str]:
    return {
        name: "AVAILABLE"
        if report.value is not None
        else f"ABSENT_{(report.na_reason or 'UNAVAILABLE').upper().replace(' ', '_')}"
        for name, report in reports.items()
    }


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _estimate_cost(
    outcome: Mapping[str, Any],
    variant: EmbeddingVariant,
    pricing: Mapping[str, Mapping[str, float]] | None,
) -> tuple[float | None, str | None]:
    """Price provider token usage using rates configured by model ID.

    Rates are USD per million tokens. ``total_tokens`` may use
    ``total_per_million``; otherwise input/output usage is priced separately.
    """
    if outcome.get("estimated_cost") is not None:
        return _number(outcome["estimated_cost"]), None
    if pricing is None:
        return None, "pricing unavailable"
    rates = pricing.get(variant.model_id)
    if not isinstance(rates, Mapping):
        return None, "pricing unavailable"
    usage = outcome.get("token_usage")
    if isinstance(usage, Mapping):
        total = _number(usage.get("total_tokens", usage.get("total")))
        input_tokens = _number(usage.get("input_tokens", usage.get("prompt_tokens")))
        output_tokens = _number(usage.get("output_tokens", usage.get("completion_tokens")))
    else:
        total = _number(usage)
        input_tokens = output_tokens = None
    if total is not None and _number(rates.get("total_per_million")) is not None:
        return total * float(rates["total_per_million"]) / 1_000_000, None
    input_rate = _number(rates.get("input_per_million"))
    output_rate = _number(rates.get("output_per_million"))
    if input_tokens is None and output_tokens is None and total is not None:
        input_tokens = total
    if input_tokens is None or input_rate is None:
        return None, "token usage unavailable"
    cost = input_tokens * input_rate
    if output_tokens is not None:
        if output_rate is None:
            return None, "pricing unavailable"
        cost += output_tokens * output_rate
    return cost / 1_000_000, None


def _aggregate_optional(outcomes: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    values = [_number(outcome.get(field)) for outcome in outcomes]
    usable = [value for value in values if value is not None]
    if not usable:
        return {"value": None, "count": 0, "reason": "no eligible values"}
    return {"value": sum(usable) / len(usable), "count": len(usable)}


def _aggregate_tokens(outcomes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals: dict[str, float] = {}
    count = 0
    for outcome in outcomes:
        usage = outcome.get("token_usage")
        if isinstance(usage, Mapping):
            numeric = {
                str(key): float(value)
                for key, value in usage.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
        else:
            total = _number(usage)
            numeric = {"total_tokens": total} if total is not None else {}
        if numeric:
            count += 1
            for key, value in numeric.items():
                totals[key] = totals.get(key, 0.0) + value
    if not totals:
        return {"value": None, "count": 0, "reason": "no eligible values"}
    return {"value": totals, "count": count}


def run_suite_b(
    records: Sequence[GoldRecord | Mapping[str, Any]],
    retrieve: Callable[[GoldRecord, EmbeddingVariant], Mapping[str, Any]],
    *,
    session: Session,
    storage: ObjectStoragePort,
    writer: EvaluationRunWriter | None = None,
    prepare_collection: Callable[[EmbeddingVariant, CollectionConfig, Session], None] | None = None,
    pricing: Mapping[str, Mapping[str, float]] | None = None,
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
    prompt_versions, parser_versions, prompt_source = _manifest_provenance()
    for variant in selected:
        if prepare_collection is not None:
            prepare_collection(variant, collection_config(variant), session)
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
                "pricing": dict(pricing.get(variant.model_id, {})) if pricing else None,
                "prompt_source": prompt_source,
            },
            model_ids={"embedding": variant.model_id},
            prompt_versions=prompt_versions,
            parser_versions=parser_versions,
        )
        run_id = run_writer.start(manifest, session=session, storage=storage)
        run_ids.append(run_id)
        try:
            metric_records: list[dict[str, Any]] = []
            outcomes: list[Mapping[str, Any]] = []
            provider_failed = False
            for record in gold:
                try:
                    outcome = dict(retrieve(record, variant))
                except Exception as exc:
                    outcome = {
                        "status": "FAILED",
                        "provider": "retrieval",
                        "error": f"{type(exc).__name__}: {exc}",
                        "retrieved": [],
                    }
                if outcome.get("error") or str(outcome.get("status", "")).upper() in {
                    "FAILED",
                    "ERROR",
                }:
                    provider_failed = True
                retrieved = outcome.get("retrieved", outcome.get("results", []))
                if outcome.get("estimated_cost") is None:
                    estimated_cost, cost_reason = _estimate_cost(outcome, variant, pricing)
                    if estimated_cost is not None:
                        outcome["estimated_cost"] = estimated_cost
                    elif cost_reason is not None:
                        outcome["cost_unavailable_reason"] = cost_reason
                else:
                    estimated_cost = _number(outcome["estimated_cost"])
                    if estimated_cost is None:
                        outcome["cost_unavailable_reason"] = "invalid estimated cost"
                if not isinstance(retrieved, Sequence) or isinstance(retrieved, (str, bytes)):
                    outcome = {
                        **outcome,
                        "status": "FAILED",
                        "provider": outcome.get("provider", "retrieval"),
                        "error": "fixture outcome retrieved must be a sequence",
                        "retrieved": [],
                    }
                    retrieved = []
                    provider_failed = True
                outcomes.append(outcome)
                metric_records.append(
                    {
                        "id": record.id,
                        "category": record.category.value,
                        "retrieved": list(retrieved),
                        "relevant": record.expected_provision_ids,
                    }
                )
                raw_input = {"question": record.question}
                if record.query_date is not None:
                    raw_input["query_date"] = record.query_date.isoformat()
                run_writer.append_result(
                    run_id,
                    {
                        "question_id": record.id,
                        "input": raw_input,
                        "retrieval": outcome,
                        "output": {},
                        "metrics": {},
                    },
                    session=session,
                    storage=storage,
                )
            reports = evaluate_retrieval(metric_records)
            metrics = {name: report.__dict__ for name, report in reports.items()}
            metrics.update(
                {
                    "latency_ms": _aggregate_optional(outcomes, "latency_ms"),
                    "estimated_cost": _aggregate_optional(outcomes, "estimated_cost"),
                    "token_usage": _aggregate_tokens(outcomes),
                }
            )
            availability = _metric_availability(reports)
            for field in ("latency_ms", "estimated_cost", "token_usage"):
                if metrics[field]["value"] is not None:
                    availability[field] = "AVAILABLE"
                elif field == "estimated_cost":
                    reasons = {
                        str(outcome["cost_unavailable_reason"])
                        for outcome in outcomes
                        if outcome.get("cost_unavailable_reason")
                    }
                    reason = next(iter(sorted(reasons)), "no eligible values")
                    availability[field] = f"ABSENT_{reason.upper().replace(' ', '_')}"
                else:
                    availability[field] = "ABSENT_NO_ELIGIBLE_VALUES"
            if provider_failed:
                for name in reports:
                    availability[name] = "ABSENT_PROVIDER_FAILURE"
            run_writer.finish(
                run_id,
                status="FAILED" if provider_failed else "COMPLETED",
                metrics=metrics,
                metric_availability=availability,
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
