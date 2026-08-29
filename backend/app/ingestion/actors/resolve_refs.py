"""Resolve legal references from persisted provisions and hand off to temporal resolution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import dramatiq
from sqlalchemy import select

from app.config import get_queue_settings
from app.ingestion.reference_resolver import (
    extract_document_relations,
    infer_parent_relations,
    resolve_references,
    review_item_for,
)
from app.persistence.models import DocumentRelation, ProvisionReference
from app.persistence.repositories.relations import RelationRepository
from app.persistence.repositories.review_items import ReviewItemRepository

from ._state import (
    STATUS_PENDING_REVIEW,
    JobNotFoundError,
    finish_terminal,
    latest_document_version,
    list_provisions,
    load_run,
    new_session,
    set_stage,
    stage_done,
)

_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "resolve_refs",
    "time_limit": get_queue_settings().actor_timeouts_seconds["resolve_refs"],
    "max_retries": get_queue_settings().max_retries,
}


def _persist_reference(
    session: Any, source: Any, candidate: Any, targets: Mapping[str, Any]
) -> None:
    """Persist one candidate, keeping retries idempotent."""
    existing = session.scalar(
        select(ProvisionReference).where(
            ProvisionReference.source_legal_provision_id == source.id,
            ProvisionReference.relation_type == candidate.relation_type,
            ProvisionReference.source_text == candidate.source_text,
        )
    )
    if existing is not None:
        return

    target = (
        targets.get(candidate.target_provision_id)
        if candidate.resolution_status in {"RESOLVED", "PENDING_REVIEW"}
        else None
    )
    resolved = candidate.resolution_status in {"RESOLVED", "PENDING_REVIEW"} and target is not None
    target_id = target.id if target is not None else None
    target_provision_id = target.provision_id if target is not None else None
    target_version = target.version if target is not None else None
    session.add(
        ProvisionReference(
            source_legal_provision_id=source.id,
            target_legal_provision_id=target_id,
            source_provision_id=source.provision_id,
            source_provision_version_id=str(source.version),
            target_provision_id=target_provision_id,
            target_provision_version_id=(
                str(target_version) if target_version is not None else None
            ),
            relation_type=candidate.relation_type,
            confidence=candidate.confidence,
            extraction_method=candidate.extraction_method,
            source_text=candidate.source_text,
            resolution_status=(candidate.resolution_status if resolved else "UNRESOLVED"),
            review_status=(
                "PENDING"
                if candidate.resolution_status == "PENDING_REVIEW"
                else "ACCEPTED"
                if resolved
                else "PENDING"
            ),
        )
    )


@dramatiq.actor(**_ACTOR_OPTIONS)
def resolve_refs_actor(job_id: str) -> None:
    """Resolve references using the canonical provisions persisted by extraction."""
    session = new_session()

    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "RESOLVING_REFS"):
            return

        manifest = dict(run.manifest_json or {})
        version = latest_document_version(session, run.document_id)
        persisted = list_provisions(session, version.id) if version is not None else []
        legacy_text = manifest.get("reference_text")
        legacy_provisions = manifest.get("provisions")
        known_documents = manifest.get("known_documents", {})
        malformed_documents = not isinstance(known_documents, Mapping)
        if malformed_documents:
            known_documents = {}

        refs: list[Any] = []
        review_rows: list[dict[str, Any]] = []
        if persisted:
            targets = {key: row for row in persisted for key in (str(row.id), row.provision_id)}
            sources = {row.provision_id: row for row in persisted}
            for source in persisted:
                candidates = resolve_references(
                    source.source_text,
                    source.provision_id,
                    persisted,
                    source_version=source.version,
                )
                refs.extend(candidates)
                for candidate in candidates:
                    _persist_reference(session, source, candidate, targets)
                    if candidate.resolution_status != "RESOLVED":
                        review_rows.append(
                            review_item_for(
                                candidate,
                                document_id=run.document_id,
                                ingestion_run_id=job_id,
                            )
                        )
            for candidate in infer_parent_relations(persisted):
                refs.append(candidate)
                _persist_reference(
                    session, sources[candidate.source_provision_id], candidate, targets
                )
        elif (
            isinstance(legacy_text, str)
            and isinstance(legacy_provisions, list)
            and not malformed_documents
        ):
            refs = resolve_references(legacy_text, run.document_id, legacy_provisions)
            review_rows = [
                review_item_for(r, document_id=run.document_id, ingestion_run_id=job_id)
                for r in refs
                if r.resolution_status != "RESOLVED"
            ]
        elif not persisted:
            review_rows = [{"target_id": run.document_id, "reason_code": "MISSING_REFERENCE_INPUT"}]

        relation_text = (
            "\n".join(row.source_text for row in persisted) if persisted else legacy_text
        )
        docs = (
            extract_document_relations(relation_text, run.document_id, known_documents)
            if isinstance(relation_text, str) and not malformed_documents
            else []
        )
        relation_repo = RelationRepository(session)
        for document_candidate in docs:
            if document_candidate.target_document_id is None:
                review_rows.append(
                    {
                        "target_type": "DOCUMENT_RELATION",
                        "target_id": run.document_id,
                        "reason_code": "TARGET_NOT_FOUND",
                        "description": document_candidate.source_note,
                    }
                )
                continue
            relation_repo.upsert_document_relation(
                DocumentRelation(
                    source_document_id=document_candidate.source_document_id,
                    target_document_id=document_candidate.target_document_id,
                    relation_type=document_candidate.relation_type,
                    source_note=document_candidate.source_note,
                    source="extracted",
                    resolution_status="RESOLVED",
                    review_status="PENDING",
                )
            )
        manifest["reference_resolution"] = {
            "provision_references": [r.__dict__ for r in refs],
            "document_relations": [r.__dict__ for r in docs],
        }
        manifest["review_items"] = review_rows
        for item in review_rows:
            ReviewItemRepository(session).create(
                run.id,
                run.document_id,
                item.get("target_type", "REFERENCE_RESOLUTION"),
                item["target_id"],
                item["reason_code"],
                item.get("description"),
                item.get("evidence"),
            )
        run.manifest_json = {**manifest, "review_items": review_rows}
        if review_rows:
            finish_terminal(run, STATUS_PENDING_REVIEW, stage="RESOLVING_REFS")
            session.commit()
            return
        set_stage(run, "RESOLVING_REFS")
        session.commit()
    finally:
        session.close()

    from .resolve_temporal import resolve_temporal_actor

    resolve_temporal_actor.send(job_id)


__all__ = ["resolve_refs_actor"]
