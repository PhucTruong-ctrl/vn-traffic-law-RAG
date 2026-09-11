"""Parse actor — PARSING stage (VNLRAG-133).

Downloads source PDFs, routes searchable files through pdfplumber, and routes
scans through PaddleOCR GPU. Legacy Docling/MinerU runners are optional and
are not part of the base dependency graph.
(status ``QUEUED``) when the queue message is picked up, so :func:`enqueue_parse`
stays a pure queue call (no DB, no FK coupling for VNLRAG-135).

Idempotency (doc 03 §3.13.3): the stage marker and the parsed-document rows
are committed in ONE transaction.  A worker killed mid-parse rolls back both
(nothing persisted), so a re-run re-parses exactly once; a run that already
passed PARSING (``stage_done``) is skipped without re-fetching the PDF.

Test seams (module-level, monkeypatched by unit/integration tests):
``_new_session``, ``_get_storage``, and the parser runners built by
:func:`_route_and_parse` via :data:`_primary_parse` / :data:`_alternate_parse`.
"""

from __future__ import annotations

import hashlib
import tempfile
import uuid
from pathlib import Path
from typing import Any

import dramatiq

from app.config import get_queue_settings
from app.ingestion.adapters.hybrid_ocr_adapter import HybridOCRAdapter
from app.ingestion.adapters.pdfplumber_adapter import PdfPlumberAdapter
from app.ingestion.document_ir import ParsedDocument
from app.ingestion.parser_router import ParserRouter, RoutingInputs
from app.storage.object_storage import ObjectStoragePort, get_object_storage

from ._state import (
    JobBootstrapError,
    bootstrap_run,
    load_run,
    new_session,
    persist_parsed_document,
    set_stage,
    stage_done,
)

#: Source PDFs bucket (doc 03 §3.12.1) — the only bucket the parse actor reads.
SOURCE_PDFS_BUCKET = "source-pdfs"

_QUEUE_SETTINGS = get_queue_settings()
_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "parse",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["parse"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}


class ParseRejectedError(RuntimeError):
    """The router did not accept any parser output for the document."""


def _get_storage() -> ObjectStoragePort:
    """Process-wide object storage (test seam)."""
    return get_object_storage()


def _pdf_page_count(pdf_path: Path) -> int:
    """PDF page count via pypdf; 1 when the bytes are not parseable.

    Mirrors Suite A's helper: ``page_count`` is informational for routing (the
    discriminator is ``has_text_layer``).
    """
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        return 1


def _probe_text_layer(pdf_path: Path) -> bool:
    """True when the PDF carries an extractable text layer (born-digital).

    A scan has no text layer and routes to OCR (doc 03 §3.7.1).  Probing
    failure (unreadable/stub bytes) conservatively reports no text layer —
    the OCR route fails fast on missing tesseract and falls back to MinerU.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        return any((page.extract_text() or "").strip() for page in reader.pages[:3])
    except Exception:
        return False


def _routing_inputs(pdf_path: Path, *, document_id: str, has_text_layer: bool) -> RoutingInputs:
    return RoutingInputs(
        document_id=document_id,
        file_mime="application/pdf",
        has_text_layer=has_text_layer,
        page_count=_pdf_page_count(pdf_path),
        file_size_bytes=pdf_path.stat().st_size,
        layout_complexity=None,
        document_type="OTHER",
    )


def _primary_parse(
    pdf_path: Path, *, inputs: RoutingInputs, object_key: str, parsed_document_id: str
) -> ParsedDocument:
    """Parse searchable text or GPU OCR into canonical IR."""
    if inputs.has_text_layer:
        return PdfPlumberAdapter().parse(
            pdf_path,
            source_object_key=object_key,
            parsed_document_id=parsed_document_id,
            document_id=inputs.document_id,
        )
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="vnlaw-actor-ocr-") as directory:
        checkpoint = Path(directory)
        rendered = subprocess.run(
            ["pdftoppm", "-png", "-r", "144", str(pdf_path), str(checkpoint / "page")],
            check=True,
            capture_output=True,
            text=True,
        )
        del rendered
        pages: list[tuple[int, str | Path]] = [
            (page, path)
            for page, path in sorted(
                (int(path.stem.split("-")[-1]), path) for path in checkpoint.glob("page-*.png")
            )
        ]
        if not pages:
            raise ParseRejectedError("OCR produced no rendered pages")
        return HybridOCRAdapter().parse_document(
            pages,
            document_id=inputs.document_id,
            parsed_document_id=parsed_document_id,
            source_object_key=object_key,
            checkpoint_path=checkpoint / "ocr.json",
        )


def _alternate_parse(
    pdf_path: Path, *, inputs: RoutingInputs, object_key: str, parsed_document_id: str
) -> ParsedDocument:
    """No alternate parser: primary Paddle/pdfplumber route is authoritative."""
    raise ParseRejectedError("alternate parser unavailable")


def route_and_parse(
    pdf_path: Path,
    *,
    document_id: str,
    object_key: str,
    parsed_document_id: str,
) -> tuple[ParsedDocument, dict]:
    """Run the Parser Router on ``pdf_path`` and return the ACCEPTED document.

    Mirrors Suite A's orchestration (doc 03 §3.7): pure routing decision, lazy
    primary/alternate runners, Group A gating with mineru fallback.  Returns
    ``(accepted_ir, routing_record)``; raises :class:`ParseRejectedError` when
    the router's terminal outcome is not ``accepted`` (the job then fails —
    the message is retried/DLQ'd, never silently indexed).
    """
    router = ParserRouter()
    inputs = _routing_inputs(
        pdf_path, document_id=document_id, has_text_layer=_probe_text_layer(pdf_path)
    )
    parsed = _primary_parse(
        pdf_path, inputs=inputs, object_key=object_key, parsed_document_id=parsed_document_id
    )
    parser_name = parsed.parser.casefold()
    decision = router.decide(inputs).model_copy(
        update={
            "route": f"{parser_name}_{'text' if inputs.has_text_layer else 'ocr'}",
            "selected_parser": parser_name,
            "expected_fallback": None,
        }
    )
    outcome = router.execute_and_gate(parsed, parser_name, parser_name, fallback_enabled=False)
    record = router.record_decision(decision, outcome)
    if outcome.terminal_outcome != "accepted":
        raise ParseRejectedError(
            f"router terminal_outcome={outcome.terminal_outcome!r}: {outcome.reason}"
        )
    return parsed, record


@dramatiq.actor(**_ACTOR_OPTIONS)
def parse_actor(job_id: str, object_key: str, document_id: str | None = None) -> None:
    """Parse the PDF at ``object_key`` and persist the accepted IR (PARSING).

    Message payload is intentionally tiny (job_id + object_key + document_id).
    """
    session = new_session()
    try:
        run = load_run(session, job_id)
        if run is None:
            try:
                run = bootstrap_run(
                    session,
                    job_id=job_id,
                    document_id=document_id,
                    object_key=object_key,
                )
                session.commit()
            except JobBootstrapError:
                session.rollback()
                raise
        elif stage_done(run, "PARSING"):
            return
        else:
            session.rollback()
        # Capture plain values BEFORE the session closes (the ORM instance
        # becomes detached and lazy-loads would fail).
        run_document_id = run.document_id
    finally:
        session.close()

    # --- heavy work: fetch + parse (no DB transaction open) ---
    storage = _get_storage()
    pdf_bytes = storage.get(SOURCE_PDFS_BUCKET, object_key)
    parsed_document_id = str(uuid.uuid4())
    with tempfile.NamedTemporaryFile(prefix="vnlaw-parse-", suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        accepted, routing_record = route_and_parse(
            Path(tmp.name),
            document_id=run_document_id,
            object_key=object_key,
            parsed_document_id=parsed_document_id,
        )
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

    session = new_session()
    try:
        run = load_run(session, job_id)
        if run is None or stage_done(run, "PARSING"):
            return  # another attempt already completed this stage
        set_stage(run, "PARSING")
        run.file_hash = pdf_hash
        run.parser_routing = routing_record
        persist_parsed_document(session, accepted, run=run)
        session.commit()
    finally:
        session.close()

    from .normalize import normalize_actor

    normalize_actor.send(job_id)


__all__ = [
    "ParseRejectedError",
    "SOURCE_PDFS_BUCKET",
    "parse_actor",
    "route_and_parse",
]
