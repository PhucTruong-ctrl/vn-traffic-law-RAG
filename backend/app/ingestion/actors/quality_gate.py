"""Quality gate actor — QUALITY_CHECK stage (VNLRAG-133).

Runs Group A (parser-level, re-evaluated on the persisted IR) + Group B
(structural) gates and routes every extracted provision via
``review_routing.evaluate_and_route`` (doc 03 §3.4.2, §3.7.5).  Decisions are
persisted per the review-status contract:

* ACCEPTED  -> ``review_status=ACCEPTED`` ONLY when the provision carries an
  ``effective_from`` (the DB check
  ``legal_provisions_effective_from_accepted_check`` forbids interval-less
  ACCEPTED rows).  Without an interval (temporal resolution is STAGED until
  W4) the row stays PENDING and the routing decision is recorded on the run
  so W4 can flip it.
* NEEDS_REVIEW -> a ReviewItem row (status PENDING, the review queue) and
  ``review_status=PENDING``.
* DROPPED     -> a ReviewItem audit row (status DROPPED) and
  ``review_status=DROPPED`` — never indexed.

Job outcome (doc 03 §3.13.3): any NEEDS_REVIEW -> ``PENDING_REVIEW``
(embed/index never run); any DROPPED (and no NEEDS_REVIEW) -> ``DROPPED``
(fatal stop); every decision ACCEPTED -> the chain continues to embed/index.

Idempotency: gates + review items + the stage marker commit in one
transaction, and a run that already has review items (resume path) is treated
as gated — review items are never duplicated.
"""

from __future__ import annotations

from typing import Any

import dramatiq

from app.config import get_queue_settings
from app.ingestion.quality_gates import evaluate_group_a
from app.ingestion.review_routing import evaluate_and_route
from app.persistence.repositories.review_items import ReviewItemRepository

from ._state import (
    STATUS_DROPPED,
    STATUS_PENDING_REVIEW,
    JobNotFoundError,
    JobStateError,
    finish_terminal,
    latest_document_version,
    list_provisions,
    list_review_items,
    load_parsed_document,
    load_run,
    new_session,
    provision_row_to_extracted,
    rebuild_ir,
    set_stage,
    stage_done,
)

_QUEUE_SETTINGS = get_queue_settings()
_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "quality_gate",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["quality_gate"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}

#: ``review_items.target_type`` value for provision-level gate decisions.
TARGET_TYPE_PROVISION = "provision"


@dramatiq.actor(**_ACTOR_OPTIONS)
def quality_gate_actor(job_id: str) -> None:
    """Gate + route the extracted provisions (QUALITY_CHECK)."""
    session = new_session()
    continue_to_embed = False
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "QUALITY_CHECK"):
            return
        if list_review_items(session, run.id):
            # Already gated (resume path) — never duplicate review items.
            set_stage(run, "QUALITY_CHECK")
            session.commit()
            return

        version = latest_document_version(session, run.document_id)
        if version is None:
            raise JobStateError(
                f"no document version for run {job_id!r}; extract must run first"
            )
        rows = list_provisions(session, version.id)
        if not rows:
            raise JobStateError(f"no provisions extracted for run {job_id!r}")

        parsed_row, elements = load_parsed_document(session, run.document_id)
        if parsed_row is None:
            raise JobStateError(
                f"no parsed document persisted for run {job_id!r}; parse must run first"
            )
        group_a = evaluate_group_a(rebuild_ir(parsed_row, elements))

        decisions = evaluate_and_route(
            [provision_row_to_extracted(row) for row in rows], group_a=group_a
        )
        decision_by_id = {decision.provision_id: decision for decision in decisions}

        repo = ReviewItemRepository(session)
        routing: dict[str, dict[str, Any]] = {}
        has_needs_review = False
        has_dropped = False
        for row in rows:
            decision = decision_by_id.get(row.provision_id)
            if decision is None:
                continue
            routing[row.provision_id] = decision.model_dump(mode="json")
            if decision.status == "ACCEPTED":
                if row.effective_from is not None:
                    row.review_status = "ACCEPTED"
                else:
                    # Interval-less: temporal resolution is STAGED until W4
                    # (VNLRAG-136); the routing record lets W4 flip this row.
                    row.review_status = "PENDING"
            elif decision.status == "NEEDS_REVIEW":
                has_needs_review = True
                repo.create(
                    ingestion_run_id=run.id,
                    document_id=run.document_id,
                    target_type=TARGET_TYPE_PROVISION,
                    target_id=row.provision_id,
                    reason_code=";".join(decision.reason_codes),
                    description=(
                        f"Quality gate routed {row.provision_id} to review: "
                        f"{', '.join(decision.reason_codes)}"
                    ),
                    evidence={"routing": decision.model_dump(mode="json")},
                )
                row.review_status = "PENDING"
            elif decision.status == "DROPPED":
                has_dropped = True
                item = repo.create(
                    ingestion_run_id=run.id,
                    document_id=run.document_id,
                    target_type=TARGET_TYPE_PROVISION,
                    target_id=row.provision_id,
                    reason_code=";".join(decision.reason_codes),
                    description=(
                        f"Quality gate dropped {row.provision_id}: "
                        f"{', '.join(decision.reason_codes)}"
                    ),
                    evidence={"routing": decision.model_dump(mode="json")},
                )
                item.status = "DROPPED"  # audit record; dropped provisions never index
                row.review_status = "DROPPED"

        manifest = dict(run.manifest_json or {})
        manifest["routing"] = routing
        run.manifest_json = manifest

        if has_needs_review:
            finish_terminal(run, STATUS_PENDING_REVIEW, stage="QUALITY_CHECK")
        elif has_dropped:
            finish_terminal(run, STATUS_DROPPED, stage="QUALITY_CHECK")
        else:
            set_stage(run, "QUALITY_CHECK")
            continue_to_embed = True
        session.commit()
    finally:
        session.close()

    if continue_to_embed:
        from .embed import embed_actor

        embed_actor.send(job_id)


__all__ = ["TARGET_TYPE_PROVISION", "quality_gate_actor"]
