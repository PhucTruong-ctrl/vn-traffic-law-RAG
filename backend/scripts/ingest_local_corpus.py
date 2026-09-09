"""Persist the accepted local legal corpus and build the production retrieval index."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.api.db import get_engine  # noqa: E402
from app.config import get_embedding_settings  # noqa: E402
from app.ingestion.adapters.pdfplumber_adapter import (  # noqa: E402
    PdfPlumberAdapter,
    SearchableTextRequiredError,
)
from app.ingestion.context_enricher import enrich_provision  # noqa: E402
from app.ingestion.document_ir import ParsedDocument  # noqa: E402
from app.ingestion.metadata_extractor import (  # noqa: E402
    extract_document_metadata,
    validate_against_manifest,
)
from app.ingestion.projection import (  # noqa: E402
    project_document,
    project_provenance,
    project_provisions,
    validate_provisions,
)
from app.ingestion.quality_gates import evaluate_group_a, evaluate_group_b  # noqa: E402
from app.ingestion.structure_extractor import extract_legal_provisions  # noqa: E402
from app.persistence.models import (  # noqa: E402
    DocumentVersion,
    LegalDocument,
    LegalProvision,
    ProvisionProvenance,
    ProvisionVersion,
)
from app.retrieval.embedding import get_embedding_provider  # noqa: E402
from app.retrieval.indexing import index_accepted_provisions  # noqa: E402
from app.retrieval.qdrant_store import ensure_qdrant_collection  # noqa: E402

CORPUS = _ROOT / "data" / "corpus" / "task1-pdfs"
MANIFESTS = _ROOT / "data" / "manifests"
OCR_CHECKPOINTS = (
    Path(os.environ.get("OCR_CHECKPOINT_DIR", tempfile.gettempdir())) / "vnlaw-ocr-checkpoints"
)
DEFAULT_DOCUMENTS = (
    "nd-44-2024",
    "nd-67-2023",
    "nd-119-2024",
    "nd-158-2024",
    "nd-160-2024",
    "nd-161-2024",
    "nd-165-2024",
    "nd-166-2024",
    "nd-168-2024",
    "tt-05-2024",
    "tt-16-2024",
    "tt-18-2024",
    "tt-39-2024",
    "tt-51-2024",
)


def _approved_targets() -> tuple[str, ...]:
    """Return the immutable approved snapshot identities, deduplicated."""
    candidates: list[str] = []
    for manifest_path in sorted(MANIFESTS.rglob("*.manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        document_id = manifest.get("document_id")
        if manifest.get("review_status") == "ACCEPTED" and isinstance(document_id, str):
            candidates.append(document_id)
    approved = tuple(dict.fromkeys(candidates))
    configured = tuple(item for item in DEFAULT_DOCUMENTS if item in approved)
    return configured or approved


def _manifest(document_id: str) -> dict[str, Any]:
    matches = list(MANIFESTS.rglob(f"{document_id}.manifest.json"))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one manifest for {document_id}, found {len(matches)}")
    manifest = json.loads(matches[0].read_text(encoding="utf-8"))
    if manifest.get("document_id") != document_id:
        raise RuntimeError(
            f"manifest document_id {manifest.get('document_id')!r} does not match {document_id!r}"
        )
    if manifest.get("review_status") != "ACCEPTED":
        raise RuntimeError(f"manifest {matches[0]} is not ACCEPTED")
    return manifest


def _render_scanned_pdf(path: Path, checkpoint: Path) -> list[tuple[int, Path]]:
    import subprocess

    checkpoint.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-r",
                "144",
                str(path),
                str(checkpoint / "page"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("scanned PDF requires the pdftoppm command") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"pdftoppm failed for {path}: {detail}") from exc
    rendered = sorted(
        checkpoint.glob("page-*.png"),
        key=lambda item: int(item.stem.rsplit("-", 1)[1]),
    )
    if not rendered:
        raise RuntimeError(f"pdftoppm produced no page images for {path}")
    return [(int(item.stem.rsplit("-", 1)[1]), item) for item in rendered]


def _source_object_key(path: Path) -> str:
    try:
        return str(path.relative_to(_ROOT))
    except ValueError:
        return path.name


def _parse_searchable(path: Path) -> ParsedDocument:
    key = _source_object_key(path)
    return PdfPlumberAdapter().parse(
        path,
        source_object_key=key,
        parsed_document_id=path.stem,
        document_id=path.stem,
    )


def _parse_scanned_in_worker(path: Path, checkpoint: Path) -> ParsedDocument:
    import subprocess

    output = checkpoint / "ocr-worker.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--ocr-worker",
        "--ocr-input",
        str(path),
        "--ocr-output",
        str(output),
        "--ocr-checkpoint",
        str(checkpoint),
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise RuntimeError(f"OCR worker could not start: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"OCR worker failed ({completed.returncode}): {detail}")
    try:
        return ParsedDocument.model_validate_json(output.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"OCR worker produced invalid output: {exc}") from exc


def _parse(path: Path, *, ocr_adapter: list[Any] | None = None) -> ParsedDocument:
    del ocr_adapter
    try:
        return _parse_searchable(path)
    except SearchableTextRequiredError:
        checkpoint = OCR_CHECKPOINTS / path.stem / hashlib.sha256(path.read_bytes()).hexdigest()
        checkpoint.mkdir(parents=True, exist_ok=True)
        return _parse_scanned_in_worker(path, checkpoint)


def _run_ocr_worker(path: Path, output: Path, checkpoint: Path) -> None:
    from app.ingestion.adapters.hybrid_ocr_adapter import HybridOCRAdapter

    key = _source_object_key(path)
    checkpoint.mkdir(parents=True, exist_ok=True)
    images = _render_scanned_pdf(path, checkpoint)
    adapter = HybridOCRAdapter(
        device="gpu:0", recognition_mode=os.environ.get("OCR_RECOGNITION_MODE", "paddle")
    )
    parsed = adapter.parse_document(
        images,
        document_id=path.stem,
        parsed_document_id=path.stem,
        source_object_key=key,
        checkpoint_path=checkpoint / "ocr.json",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(parsed.model_dump(mode="json"), stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _uniquify_ocr_provisions(provisions: list[Any]) -> list[Any]:
    """Keep first canonical provision for each duplicate OCR identity.

    Repeated OCR nodes cannot be represented under frozen provision-ID grammar.
    They remain visible through ingestion diagnostics and are excluded from the
    accepted projection rather than assigned fabricated legal identities.
    """

    seen: set[str] = set()
    unique: list[Any] = []
    for provision in provisions:
        provision_id = getattr(provision, "provision_id", None)
        if not isinstance(provision_id, str) or provision_id not in seen:
            unique.append(provision)
            if isinstance(provision_id, str):
                seen.add(provision_id)
    return unique


def _prepare_document(
    path: Path, manifest: dict[str, Any], ir: Any, provisions: list[Any]
) -> dict[str, Any]:
    """Validate and project document without touching persistence."""

    provisions = _uniquify_ocr_provisions(provisions)
    metadata = extract_document_metadata(ir, manifest_number=manifest.get("document_number"))
    issues = validate_against_manifest(metadata, manifest)
    if issues:
        raise RuntimeError("metadata validation failed: " + "; ".join(issues))
    group_a = evaluate_group_a(ir)
    if group_a.verdict != "passed":
        raise RuntimeError(f"Group A quality gate failed: {group_a.model_dump(mode='json')}")
    group_b = evaluate_group_b(provisions)
    if not group_b.passed:
        raise RuntimeError(f"Group B quality gate failed: {group_b.model_dump(mode='json')}")
    document, version = project_document(ir, manifest, metadata, version=1)
    rows = project_provisions(
        provisions,
        document_version_id=version.id,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        review_status=version.review_status,
    )
    errors = validate_provisions(rows)
    if errors:
        raise RuntimeError("provision validation failed: " + "; ".join(errors))
    return {"metadata": metadata, "document": document, "version": version, "rows": rows}


def _persist(
    session: Any, path: Path, manifest: dict[str, Any], ir: Any, provisions: list[Any]
) -> dict[str, Any]:
    provisions = _uniquify_ocr_provisions(provisions)
    prepared = _prepare_document(path, manifest, ir, provisions)
    document = prepared["document"]
    version = prepared["version"]
    existing = session.scalar(
        select(LegalDocument).where(LegalDocument.document_id == document.document_id)
    )
    if existing is None:
        session.add(document)
        session.flush()
    elif existing.file_hash != document.file_hash:
        raise RuntimeError(f"document ownership/content conflict for {document.document_id}")
    else:
        document = existing
    versions = list(
        session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.document_id)
            .order_by(DocumentVersion.version)
        )
    )
    existing_version = next(
        (item for item in versions if item.content_hash == version.content_hash),
        None,
    )
    if existing_version is None:
        version.version = versions[-1].version + 1 if versions else 1
        version.document_id = document.document_id
        session.add(version)
        session.flush()
    else:
        version = existing_version
    rows = project_provisions(
        provisions,
        document_version_id=version.id,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        review_status=version.review_status,
    )
    errors = validate_provisions(rows)
    if errors:
        raise RuntimeError("provision validation failed: " + "; ".join(errors))
    for extracted, row in zip(provisions, rows, strict=True):
        found = session.scalar(
            select(LegalProvision).where(
                LegalProvision.provision_id == row.provision_id,
                LegalProvision.version == row.version,
            )
        )
        if found is None:
            session.add(row)
            session.flush()
            found = row
        elif (
            found.document_version_id != version.id
            or found.content_hash != row.content_hash
            or found.source_text != row.source_text
        ):
            raise RuntimeError(
                f"conflicting provision ownership/content for {row.provision_id} v{row.version}"
            )
        else:
            found.effective_from = row.effective_from
            found.effective_to = row.effective_to
            found.review_status = row.review_status
        registry = session.scalar(
            select(ProvisionVersion).where(
                ProvisionVersion.provision_id == row.provision_id,
                ProvisionVersion.version == row.version,
            )
        )
        if registry is None:
            session.add(
                ProvisionVersion(
                    provision_id=row.provision_id,
                    version=row.version,
                    document_version_id=version.id,
                )
            )
        elif registry.document_version_id != version.id:
            raise RuntimeError(
                f"conflicting provision registry ownership for {row.provision_id} v{row.version}"
            )
        for provenance in project_provenance(
            extracted,
            provision_version_row_id=found.id,
            source_document_version_id=version.id,
        ):
            key = (
                ProvisionProvenance.provision_version_row_id == provenance.provision_version_row_id,
                ProvisionProvenance.source_document_version_id
                == provenance.source_document_version_id,
                ProvisionProvenance.source_element_id == provenance.source_element_id,
                ProvisionProvenance.role == provenance.role,
            )
            if session.scalar(select(ProvisionProvenance).where(*key)) is None:
                session.add(ProvisionProvenance(**provenance.model_dump()))
    session.commit()
    return {
        "document_id": path.stem,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "pages": len(ir.pages),
        "provisions": len(rows),
        "parser": ir.parser,
    }


def _failure(path: Path, error: str, *, stages: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "document_id": path.stem,
        "pdf": str(path),
        "status": "REJECTED",
        "error": error,
        "stages": stages
        or {
            stage: {"status": "FAILED" if stage == "parse" else "NOT_RUN"}
            for stage in ("parse", "structure", "relations", "temporal", "quality")
        },
        "retained_artifact": {
            "artifact_type": "REJECTED_SOURCE",
            "object_key": _source_object_key(path),
            "file_hash": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        },
    }


def _stage_outcomes(ir: Any, provisions: list[Any], manifest: dict[str, Any]) -> dict[str, Any]:
    group_a = evaluate_group_a(ir)
    group_b = evaluate_group_b(provisions)
    return {
        "parse": {"status": "PASSED", "parser": ir.parser, "pages": len(ir.pages)},
        "structure": {"status": "PASSED", "provisions": len(provisions)},
        "relations": {"status": "RECORDED", "source": "manifest.relation_notes"},
        "temporal": {
            "status": "PASSED"
            if all(getattr(item, "effective_from", None) is not None for item in provisions)
            else "FAILED",
            "effective_from": manifest.get("effective_from"),
            "effective_to": manifest.get("effective_to"),
        },
        "quality": {
            "status": "PASSED" if group_a.verdict == "passed" and group_b.passed else "FAILED",
            "group_a": group_a.model_dump(mode="json"),
            "group_b": group_b.model_dump(mode="json"),
        },
    }


def ingest(paths: list[Path], *, dry_run: bool, batch_size: int = 32) -> dict[str, Any]:
    paths = list(dict.fromkeys(paths))
    documents: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    parsed: list[tuple[Path, dict[str, Any], Any, list[Any]]] = []
    for path in paths:
        try:
            manifest = _manifest(path.stem)
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            expected = manifest.get("file_hash") or manifest.get("sha256")
            if expected and expected != actual:
                raise RuntimeError(f"hash mismatch: manifest={expected}, actual={actual}")
            ir = _parse(path)
            try:
                extracted_items = extract_legal_provisions(ir, document_slug=path.stem)
            except TypeError as exc:
                if "document_slug" not in str(exc):
                    raise
                extracted_items = extract_legal_provisions(ir)
            extracted = [enrich_provision(item) for item in extracted_items]
            if not extracted:
                raise RuntimeError("no legal provisions extracted")
            stages = _stage_outcomes(ir, extracted, manifest)
            if stages["temporal"]["status"] != "PASSED":
                raise RuntimeError(
                    "temporal resolution failed: accepted provisions require effective_from"
                )
            if stages["quality"]["status"] != "PASSED":
                raise RuntimeError("quality gates failed")
            parsed.append((path, manifest, ir, extracted))
            documents.append(
                {
                    "document_id": path.stem,
                    "pdf": str(path),
                    "sha256": actual,
                    "pages": len(ir.pages),
                    "parser": ir.parser,
                    "provisions": len(extracted),
                    "status": "ACCEPTED",
                    "stages": stages,
                }
            )
        except Exception as exc:
            failures.append(_failure(path, f"{type(exc).__name__}: {exc}"))
    if not dry_run and parsed:
        session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
        with session_factory() as session:
            for path, manifest, ir, provisions in parsed:
                try:
                    result = _persist(session, path, manifest, ir, provisions)
                    next(item for item in documents if item["document_id"] == path.stem).update(
                        reconciliation={
                            "postgresql_accepted_rows": result["provisions"],
                            "snapshot_hash": result["sha256"],
                        }
                    )
                except Exception as exc:
                    session.rollback()
                    failures.append(_failure(path, f"{type(exc).__name__}: {exc}"))
            index_accepted_provisions(
                ensure_qdrant_collection(),
                session=session,
                embedder=get_embedding_provider(get_embedding_settings()),
                batch_size=batch_size,
            )
    return {
        "documents": documents,
        "failures": failures,
        "dry_run": dry_run,
        "expected_documents": len(paths),
        "reconciliation": {
            "target_count": len(paths),
            "accepted_count": len(documents),
            "rejected_count": len(failures),
            "complete": len(documents) + len(failures) == len(paths),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ocr-input", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--ocr-output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--ocr-checkpoint", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--document", action="append", dest="documents")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args(argv)
    if args.ocr_worker:
        if not args.ocr_input or not args.ocr_output or not args.ocr_checkpoint:
            parser.error("--ocr-worker requires --ocr-input, --ocr-output, and --ocr-checkpoint")
        try:
            _run_ocr_worker(args.ocr_input, args.ocr_output, args.ocr_checkpoint)
        except Exception as exc:
            print(f"OCR worker error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    names = args.documents or list(_approved_targets())
    paths = [args.corpus / (name if name.endswith(".pdf") else f"{name}.pdf") for name in names]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        report = {
            "documents": [],
            "failures": [
                {
                    "pdf": path,
                    "error": "FileNotFoundError: requested PDF does not exist",
                }
                for path in missing
            ],
            "dry_run": args.dry_run,
            "expected_documents": len(paths),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 1
    report = ingest(paths, dry_run=args.dry_run, batch_size=args.batch_size)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
