"""Projection layer: Canonical IR + extractor output -> persistence objects.

Implements VNLRAG-32: the mapping from :class:`ParsedDocument` (plus the
corpus manifest and :class:`ExtractedDocumentMetadata`) into SQLAlchemy
``LegalDocument`` / ``DocumentVersion`` rows, and from the Legal Structure
Extractor output into ``LegalProvision`` rows carrying the full 20-field
contract (doc 00 §8.3, doc 03 §3.9.4).

Rules enforced here (never deferred to the DB):

- ``status`` (legal lifecycle) and ``review_status`` (corpus gate) are
  independent: only ``review_status = ACCEPTED`` gates query/index eligibility
  (doc 00 §8.6); ``status`` is carried through untouched.
- The manifest is authoritative (doc 03 §3.7.5): a manifest that contradicts
  the extracted IR metadata is rejected at this boundary — it must be routed
  to review, never auto-accepted as ``ACCEPTED``.
- Temporal CHECK constraints (doc 03 §3.10.4) are enforced before row
  construction: ``effective_to > effective_from`` when both present and
  ``ACCEPTED`` requires a parseable ``effective_from``.
- ``content_hash`` is a deterministic plain ``sha256`` hex digest — the frozen
  JSON templates require ``^[a-f0-9]{64}$`` (``templates/legal-*.schema.json``),
  which is why the ``sha256:``-prefixed persistence helper is not used here.
- Validation before persistence (:func:`validate_provisions`) rejects
  incomplete provisions (missing source_text, empty source_element_ids,
  invalid interval, ACCEPTED without effective_from, ...).

This module is a pure mapping layer: it never touches a session or a
transaction — the repository layer (VNLRAG-39) owns persistence.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any
from uuid import UUID

from app.ingestion.document_ir import ParsedDocument
from app.ingestion.metadata_extractor import (
    ExtractedDocumentMetadata,
    validate_against_manifest,
)
from app.ingestion.structure_extractor import ExtractedLegalProvision
from app.persistence.models import DocumentVersion, LegalDocument, LegalProvision

#: node_kind values that legitimately live outside the Điều tree (doc 03 §3.9.4):
#: their ``article`` may be null.
_NON_ARTICLE_KINDS = frozenset({"APPENDIX", "TABLE", "HEADING", "TRANSITIONAL", "OTHER"})

_VALID_STATUSES = frozenset(
    {"NOT_YET_EFFECTIVE", "EFFECTIVE", "PARTIALLY_EFFECTIVE", "EXPIRED", "UNKNOWN"}
)
_VALID_REVIEW_STATUSES = frozenset({"PENDING", "ACCEPTED", "REJECTED", "DROPPED"})
_VALID_NODE_KINDS = frozenset(
    {"ARTICLE", "CLAUSE", "POINT", "APPENDIX", "TABLE", "TRANSITIONAL", "HEADING", "OTHER"}
)
_VALID_DOCUMENT_TYPES = frozenset({"LAW", "DECREE", "CIRCULAR", "RESOLUTION", "DECISION", "OTHER"})

#: Frozen provision_id grammar — mirrors templates/legal-provision.schema.json.
_PROVISION_ID_RE = re.compile(
    r"^[a-zđ]+-[0-9]+-[0-9]{4}"
    r"(?:__dieu-[0-9]+(?:__khoan-[0-9]+(?:__diem-[a-zđ])?)?"
    r"|__dieu-[0-9]+__bang-[0-9]+"
    r"|__dieu-[0-9]+__khoan-chuyen-tiep"
    r"|__phu-luc-[0-9]+(?:__bang-[0-9]+)?"
    r"|__chuyen-tiep-[0-9]+"
    r"|__tieu-de-[0-9]+)?$"
)

_BBOX_KEYS = ("left", "top", "right", "bottom")


def _sha256_hex(content: str) -> str:
    """Plain ``sha256`` hex digest (no prefix) — matches the frozen templates."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _manifest_content_hash(manifest: dict[str, Any]) -> str:
    """Deterministic digest over the canonical JSON form of a manifest."""
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return _sha256_hex(canonical)


def _parse_iso_date(value: object) -> date | None:
    """Parse ``YYYY-MM-DD`` or a full ISO 8601 date-time into a ``date``.

    Malformed values (trailing garbage, impossible dates) return ``None`` —
    never a silently truncated prefix.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _require_str_field(manifest: dict[str, Any], field: str) -> str:
    value = manifest.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"manifest {field} must be a non-empty string")
    return value


def project_document(
    ir: ParsedDocument,
    manifest: dict[str, Any],
    metadata: ExtractedDocumentMetadata,
    *,
    version: int = 1,
) -> tuple[LegalDocument, DocumentVersion]:
    """Project one canonical IR + manifest into LegalDocument/DocumentVersion.

    The manifest is the authoritative source for identity fields
    (document_number, document_type, issuer, issued_date, source_url,
    file_hash, status — doc 03 §3.7.5); the IR contributes the document title
    when the manifest does not carry one.  Enums and temporal intervals are
    validated here so no row that violates the frozen contracts or DB CHECK
    constraints is ever constructed.  A manifest that contradicts the
    extracted IR metadata raises ``ValueError`` — the caller must route the
    document to review instead of accepting it.

    Returns ``(document, document_version)`` — neither is persisted here.
    """

    document_id = _require_str_field(manifest, "document_id")
    document_number = _require_str_field(manifest, "document_number")
    document_type = _require_str_field(manifest, "document_type")
    file_hash = _require_str_field(manifest, "file_hash")
    status = _require_str_field(manifest, "status")
    review_status = _require_str_field(manifest, "review_status")

    if document_type not in _VALID_DOCUMENT_TYPES:
        raise ValueError(f"manifest document_type {document_type!r} is not a valid DocumentType")
    if status not in _VALID_STATUSES:
        raise ValueError(f"manifest status {status!r} is not a valid DocumentStatus")
    if review_status not in _VALID_REVIEW_STATUSES:
        raise ValueError(f"manifest review_status {review_status!r} is not a valid ReviewStatus")

    effective_from = _parse_iso_date(manifest.get("effective_from"))
    effective_to = _parse_iso_date(manifest.get("effective_to"))
    if effective_from is not None and effective_to is not None and effective_to <= effective_from:
        raise ValueError("manifest effective_to must be > effective_from when both are present")
    if review_status == "ACCEPTED" and effective_from is None:
        raise ValueError("ACCEPTED manifest requires a parseable effective_from")

    conflicts = validate_against_manifest(metadata, manifest)
    if conflicts:
        joined = "; ".join(conflicts)
        raise ValueError(f"manifest conflicts with extracted IR metadata: {joined}")

    document_title = metadata.document_title or document_number

    document = LegalDocument(
        document_id=document_id,
        document_number=document_number,
        document_title=document_title,
        document_type=document_type,
        issuer=_optional_str(manifest.get("issuer")),
        issued_date=_parse_iso_date(manifest.get("issued_date")),
        source_url=_optional_str(manifest.get("source_url")),
        downloaded_at=None,
        file_hash=file_hash,
        status=status,
    )

    document_version = DocumentVersion(
        document_id=document_id,
        version=version,
        manifest_json=manifest,
        content_hash=_manifest_content_hash(manifest),
        effective_from=effective_from,
        effective_to=effective_to,
        review_status=review_status,
    )
    return document, document_version


def project_provisions(
    extracted: list[ExtractedLegalProvision],
    *,
    document_version_id: UUID,
    status: str | None = None,
    effective_from: date | None = None,
    effective_to: date | None = None,
    review_status: str | None = None,
) -> list[LegalProvision]:
    """Map extractor output into ``LegalProvision`` persistence rows.

    Every projected row keeps the extractor's own ``effective_from`` /
    ``effective_to`` / ``status`` / ``review_status`` values unless an explicit
    projection-level override is supplied (document-level defaults).  The
    fields remain independent (doc 00 §8.3): ``status`` is legal lifecycle,
    ``review_status`` is the corpus gate.  ``effective_from``/``effective_to``
    stay nullable until temporal resolution (doc 03 §3.15.6).  The
    ``content_hash`` is recomputed deterministically from ``source_text`` and
    must equal the extractor's value.
    """

    provisions: list[LegalProvision] = []
    for item in extracted:
        content_hash = _sha256_hex(item.source_text)
        if content_hash != item.content_hash:
            raise ValueError(
                f"content_hash mismatch for {item.provision_id}: "
                f"projected {content_hash} != extractor {item.content_hash}"
            )
        provisions.append(
            LegalProvision(
                provision_id=item.provision_id,
                document_version_id=document_version_id,
                node_kind=item.node_kind,
                chapter=item.chapter,
                section=item.section,
                article=item.article,
                clause=item.clause,
                point=item.point,
                heading=item.heading,
                source_text=item.source_text,
                retrieval_text=item.retrieval_text,
                parent_context=item.parent_context,
                effective_from=(
                    effective_from
                    if effective_from is not None
                    else _parse_iso_date(item.effective_from)
                ),
                effective_to=(
                    effective_to if effective_to is not None else _parse_iso_date(item.effective_to)
                ),
                status=status if status is not None else item.status,
                page_number=item.page_number,
                bbox=item.bbox,
                source_element_ids=item.source_element_ids,
                content_hash=content_hash,
                version=item.version,
                review_status=review_status if review_status is not None else item.review_status,
            )
        )
    return provisions


def validate_provisions(provisions: list[LegalProvision]) -> list[str]:
    """Return validation errors for incomplete/invalid provisions (empty = valid).

    Mirrors the DB CHECK constraints (doc 03 §3.10.4) and the frozen JSON
    template so invalid rows are rejected before persistence, not at flush
    time.
    """

    errors: list[str] = []
    for index, provision in enumerate(provisions):
        where = f"provision[{index}] {provision.provision_id!r}"
        if not provision.provision_id:
            errors.append(f"{where}: provision_id must not be empty")
        elif _PROVISION_ID_RE.fullmatch(provision.provision_id) is None:
            errors.append(f"{where}: provision_id violates the frozen ID grammar")
        if not provision.source_text.strip():
            errors.append(f"{where}: source_text must not be empty")
        if not provision.retrieval_text.strip():
            errors.append(f"{where}: retrieval_text must not be empty")
        if not provision.source_element_ids:
            errors.append(f"{where}: source_element_ids must not be empty")
        elif len(set(provision.source_element_ids)) != len(provision.source_element_ids):
            errors.append(f"{where}: source_element_ids must be unique")
        if provision.page_number < 1:
            errors.append(f"{where}: page_number must be >= 1")
        if provision.version < 1:
            errors.append(f"{where}: version must be >= 1")
        if provision.status not in _VALID_STATUSES:
            errors.append(f"{where}: invalid status {provision.status!r}")
        if provision.review_status not in _VALID_REVIEW_STATUSES:
            errors.append(f"{where}: invalid review_status {provision.review_status!r}")
        if provision.node_kind not in _VALID_NODE_KINDS:
            errors.append(f"{where}: invalid node_kind {provision.node_kind!r}")
        if provision.article is None and provision.node_kind not in _NON_ARTICLE_KINDS:
            errors.append(f"{where}: article required for node_kind {provision.node_kind}")
        if (
            provision.effective_from is not None
            and provision.effective_to is not None
            and provision.effective_to <= provision.effective_from
        ):
            errors.append(f"{where}: effective_to must be > effective_from")
        if provision.review_status == "ACCEPTED" and provision.effective_from is None:
            errors.append(f"{where}: ACCEPTED requires effective_from")
        if re.fullmatch(r"[a-f0-9]{64}", provision.content_hash) is None:
            errors.append(f"{where}: content_hash must be a 64-char lowercase sha256 hex digest")
        elif provision.content_hash != _sha256_hex(provision.source_text):
            errors.append(f"{where}: content_hash does not match sha256(source_text)")
        if provision.bbox is not None:
            extra = sorted(set(provision.bbox) - set(_BBOX_KEYS) - {"page_height", "page_width"})
            if extra:
                errors.append(f"{where}: bbox has unsupported keys {extra}")
                continue
            missing = [key for key in _BBOX_KEYS if key not in provision.bbox]
            if missing:
                errors.append(f"{where}: bbox missing required keys {missing}")
            else:
                non_numeric = [
                    key
                    for key in _BBOX_KEYS
                    if not isinstance(provision.bbox.get(key), (int, float))
                    or isinstance(provision.bbox.get(key), bool)
                ]
                if non_numeric:
                    errors.append(f"{where}: bbox keys {non_numeric} must be numeric")

    return errors


__all__ = [
    "project_document",
    "project_provisions",
    "validate_provisions",
]
