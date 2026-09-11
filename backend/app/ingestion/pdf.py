"""Small, deterministic PDF-to-legal-chunk ingestion pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class ExtractionDependencyError(RuntimeError):
    """Raised when the optional PDF extraction dependency is unavailable."""


def _preload_cuda_libraries() -> None:
    try:
        import onnxruntime as ort

        ort.preload_dlls(directory="")
    except (ImportError, AttributeError):
        return


def configure_ocr_gpu() -> None:
    """Inject RapidOCR CUDA engine when explicitly enabled."""
    try:
        from pymupdf4llm.ocr import rapidocr_391_backend
        from rapidocr import RapidOCR
    except (ImportError, AttributeError) as exc:
        raise ExtractionDependencyError(
            "CUDA OCR requested but compatible RapidOCR/PyMuPDF4LLM backend is unavailable."
        ) from exc
    params = {
        "EngineConfig.onnxruntime.use_cuda": True,
        "EngineConfig.onnxruntime.cuda_ep_cfg.device_id": int(
            os.environ.get("OCR_CUDA_DEVICE", "0")
        ),
    }
    try:
        _preload_cuda_libraries()
        rapidocr_391_backend.ENGINE = RapidOCR(params=params)
    except (TypeError, ValueError, AttributeError, RuntimeError) as exc:
        raise ExtractionDependencyError(
            "CUDA OCR requested but RapidOCR could not initialize the CUDA engine; "
            "verify ONNX Runtime GPU/CUDA compatibility."
        ) from exc


def _ocr_cuda_enabled() -> bool:
    return os.environ.get("OCR_USE_CUDA", "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class PageRecord:
    doc_id: str
    document_name: str
    page: int
    text: str
    source_file: str


@dataclass(frozen=True, slots=True)
class LegalChunk:
    id: str
    text: str
    doc_id: str
    document_name: str
    page: int
    article: str | None
    clause: str | None
    point: str | None
    source_file: str


_HEADER_RE = re.compile(
    r"(?im)^\s*(?:(Chương)\s+([IVXLCDM\d]+)\b|"
    r"(Điều)\s+([\dA-Za-z]+)\b|"
    r"(Khoản)\s+(\d+)\s*[.)]?|"
    r"(Điểm)\s+([a-zđ])\s*[.)]?)"
)


def _clean_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _native_page_texts(path: Path) -> list[str]:
    try:
        import pymupdf
    except ImportError as exc:
        raise ExtractionDependencyError(
            "PyMuPDF is required for PDF preflight; install it with "
            "`uv pip install pymupdf` and retry."
        ) from exc
    try:
        document = pymupdf.open(str(path))
        try:
            return [_clean_text(page.get_text("text", sort=True)) for page in document]
        finally:
            document.close()
    except Exception as exc:  # pragma: no cover - dependency-specific failures
        raise RuntimeError(f"failed to preflight {path}: {exc}") from exc


def _needs_ocr(text: str) -> bool:
    """Identify pages whose native text is absent or unusably short."""
    compact = re.sub(r"\s+", "", text)
    return len(compact) < 24


def _markdown_pages(
    path: Path,
    *,
    pages: list[int] | None = None,
    force_ocr: bool = False,
) -> dict[int, str]:
    try:
        import pymupdf4llm  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ExtractionDependencyError(
            "PyMuPDF4LLM is required for PDF ingestion; install it with "
            "`uv pip install pymupdf4llm` and retry."
        ) from exc
    options: dict[str, Any] = {
        "page_chunks": True,
        "write_images": False,
        "margins": 0,
        "page_width": 612,
        "page_height": 792,
        "use_ocr": force_ocr,
    }
    if force_ocr:
        options.update(force_ocr=True, ocr_dpi=150)
    if pages:
        options["pages"] = pages
    try:
        result = pymupdf4llm.to_markdown(str(path), **options)
    except Exception as exc:  # pragma: no cover - dependency-specific failures
        raise RuntimeError(f"failed to extract {path}: {exc}") from exc
    items = result if isinstance(result, list) else [result]
    extracted: dict[int, str] = {}
    for index, item in enumerate(items):
        if isinstance(item, dict):
            metadata = item.get("metadata")
            page_number = metadata.get("page") if isinstance(metadata, dict) else None
            page_number = (
                page_number
                if isinstance(page_number, int)
                else (pages[index] if pages and index < len(pages) else index)
            )
            extracted[page_number] = _clean_text(str(item.get("text", "")))
        else:
            page_number = pages[index] if pages and index < len(pages) else index
            extracted[page_number] = _clean_text(str(item))
    return extracted


def extract_pages(
    path: str | Path, *, cache_dir: str | Path | None = None, ocr_use_cuda: bool = False
) -> list[PageRecord]:
    """Extract one deterministic record per PDF page, with optional cache."""
    if ocr_use_cuda or _ocr_cuda_enabled():
        configure_ocr_gpu()
    source = Path(path).resolve()
    repo_root = Path(__file__).resolve().parents[3]
    try:
        source_file = source.relative_to(repo_root).as_posix()
    except ValueError:
        source_file = source.name
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cache_root = Path(cache_dir) if cache_dir else repo_root / "data" / "processed" / "pages"
    cache_path = cache_root / f"{digest}-pymupdf4llm-150.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("source_file") == source_file and cached.get("digest") == digest:
                return [PageRecord(**item) for item in cached["pages"]]
        except (OSError, KeyError, TypeError, ValueError):
            pass
    native = _native_page_texts(source)
    ocr_pages = [index for index, text in enumerate(native) if _needs_ocr(text)]
    normal_pages = [index for index in range(len(native)) if index not in ocr_pages]
    extracted = _markdown_pages(source, pages=normal_pages) if normal_pages else {}
    if ocr_pages:
        extracted.update(_markdown_pages(source, pages=ocr_pages, force_ocr=True))
    pages = [extracted.get(index, native[index]) for index in range(len(native))]
    doc_id = hashlib.sha256(source_file.encode("utf-8") + b"\0" + source.read_bytes()).hexdigest()[
        :16
    ]
    records = [
        PageRecord(doc_id, source.stem, number, text, source_file)
        for number, text in enumerate(pages, 1)
        if text
    ]
    cache_root.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"digest": digest, "source_file": source_file, "pages": [asdict(p) for p in records]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    temporary.replace(cache_path)
    return records


def split_legal_pages(pages: Iterable[PageRecord]) -> list[LegalChunk]:
    """Split pages at Vietnamese legal headings while carrying active metadata."""
    chunks: list[LegalChunk] = []
    for page_record in pages:
        text = page_record.text
        matches = list(_HEADER_RE.finditer(text))
        boundaries = [match.start() for match in matches] + [len(text)]
        active: dict[str, str | None] = {"article": None, "clause": None, "point": None}
        for index, match in enumerate(matches):
            heading = match.group(0).strip()
            if match.group(3):
                active = {"article": match.group(4), "clause": None, "point": None}
            elif match.group(5):
                active["clause"], active["point"] = match.group(6), None
            elif match.group(7):
                active["point"] = match.group(8)
            body = _clean_text(text[boundaries[index] : boundaries[index + 1]])
            if not body:
                continue
            identity = "|".join(
                [page_record.doc_id, str(page_record.page), str(boundaries[index]), body]
            )
            chunks.append(
                LegalChunk(
                    hashlib.sha256(identity.encode()).hexdigest()[:24],
                    f"{heading}\n{body}",
                    page_record.doc_id,
                    page_record.document_name,
                    page_record.page,
                    active["article"],
                    active["clause"],
                    active["point"],
                    page_record.source_file,
                )
            )
    return chunks


def write_jsonl(chunks: Iterable[LegalChunk], output: str | Path) -> int:
    """Write chunks in stable order as UTF-8 JSONL and return the count."""
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(asdict(chunk), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count
