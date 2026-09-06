"""Resumable OCR batch with atomic page checkpoints and provenance."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("/tmp/vnlrag-task1-pdfs")
DEFAULT_OUTPUT = Path("/tmp/vnlrag-task1-ocr-result")


def atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"documents": {}}


def render_page(pdf: Path, output: Path, page: int) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"page-{page:04d}.jpg"
    if not target.exists():
        subprocess.run(
            [
                "pdftoppm",
                "-f",
                str(page),
                "-l",
                str(page),
                "-r",
                "300",
                "-jpeg",
                "-singlefile",
                str(pdf),
                str(target.with_suffix("")),
            ],
            check=True,
        )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--document", action="append")
    parser.add_argument(
        "--recognition-mode",
        choices=("paddle", "vietocr"),
        default="paddle",
        help="Use PaddleOCR recognition by default; VietOCR requires the optional extra.",
    )
    args = parser.parse_args()
    state_path = args.output / "state.json"
    state = load_state(state_path)
    selected = set(args.document or [pdf.stem for pdf in sorted(args.input.glob("*.pdf"))])
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        PdfReader = None
    from app.ingestion.adapters.hybrid_ocr_adapter import HybridOCRAdapter

    adapter = HybridOCRAdapter(
        device=os.environ.get("OCR_DEVICE", "cpu"), recognition_mode=args.recognition_mode
    )
    for pdf in sorted(args.input.glob("*.pdf")):
        if pdf.stem not in selected:
            continue
        document = state["documents"].setdefault(pdf.stem, {"status": "pending", "pages": {}})
        document.update(
            {
                "status": "running",
                "started_at": document.get("started_at", datetime.now(UTC).isoformat()),
                "provenance": {
                    "source_pdf": str(pdf),
                    "parser": "PADDLEOCR"
                    if args.recognition_mode == "paddle"
                    else "PADDLEOCR_VIETOCR",
                    "parser_version": "paddleocr-3.3.0"
                    if args.recognition_mode == "paddle"
                    else "paddleocr-3.3.0+vietocr-0.3.13",
                },
            }
        )
        atomic_write(state_path, state)
        try:
            page_dir = args.output / pdf.stem / "pages"
            checkpoint = args.output / pdf.stem / "checkpoint.json"
            if PdfReader is not None:
                page_count = len(PdfReader(str(pdf)).pages)
            else:
                import fitz

                with fitz.open(pdf) as document_pdf:
                    page_count = document_pdf.page_count
            for page_number in range(1, page_count + 1):
                key = str(page_number)
                if document["pages"].get(key, {}).get("status") == "done":
                    continue
                try:
                    image = render_page(pdf, page_dir, page_number)
                    parsed = adapter.parse_document(
                        [(page_number, image)],
                        document_id=pdf.stem,
                        parsed_document_id=pdf.stem,
                        source_object_key=str(pdf),
                        checkpoint_path=checkpoint,
                    )
                    document["pages"][key] = {
                        "status": "done",
                        "image": str(image),
                        "elements": sum(len(p.elements) for p in parsed.pages),
                        "completed_at": datetime.now(UTC).isoformat(),
                    }
                except Exception as exc:
                    document["pages"][key] = {
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                atomic_write(state_path, state)
            document["status"] = (
                "done"
                if all(
                    document["pages"].get(str(page), {}).get("status") == "done"
                    for page in range(1, page_count + 1)
                )
                else "partial"
            )
        except Exception as exc:
            document["status"] = "failed"
            document["error"] = f"{type(exc).__name__}: {exc}"
        document["finished_at"] = datetime.now(UTC).isoformat()
        atomic_write(state_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
