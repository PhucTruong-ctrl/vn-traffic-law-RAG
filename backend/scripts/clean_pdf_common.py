from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

RE_HEADER_NOISE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},.*about:blank$", re.I)
RE_FOOTER_NOISE = re.compile(r"about:blank\s+\d+/\d+|Thư viện pháp luật|Mã tra cứu", re.I)
RE_PAGE_NUM = re.compile(r"^(Trang\s+)?\d+(\s*/\s*\d+)?$", re.I)
RE_FORM_DOTS = re.compile(r"(\.{5,}|_{5,})")
RE_CHECKBOX = re.compile(r"([☐☑\uf06f])")
RE_IS_HEADING = re.compile(r"^(CHƯƠNG|MỤC|Điều|Phần)\b", re.I)
RE_MERGE_END = re.compile(r"[a-zA-ZÀ-ỹđĐ,;]$")


def clean_text(raw_text: str, strategy: dict[str, Any] | None = None) -> str:
    if not raw_text:
        return ""
    strategy = strategy or {}
    lines = []
    for raw_line in raw_text.splitlines():
        line = RE_HEADER_NOISE.sub("", raw_line).strip()
        if not line or RE_FOOTER_NOISE.search(line) or RE_PAGE_NUM.fullmatch(line):
            continue
        line = RE_FORM_DOTS.sub(" ", line)
        line = RE_CHECKBOX.sub("", line)
        lines.append(line)
    result = "\n".join(lines)
    warning = strategy.get("prepend_warning")
    return f"> {warning}\n\n{result}" if warning else result


def table_to_markdown(data: list) -> str:
    rows = [r for r in (data or []) if any(c and str(c).strip() for c in r)]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [list(row) + [""] * (width - len(row)) for row in rows]
    out = ["| " + " | ".join(str(cell or "").replace("|", "\\|") for cell in normalized[0]) + " |"]
    out.append("| " + " | ".join("---" for _ in range(width)) + " |")
    out.extend(
        "| " + " | ".join(str(cell or "").replace("|", "\\|") for cell in row) + " |"
        for row in normalized[1:]
    )
    return "\n".join(out)


def should_keep_block(text, strategy):
    if strategy.get("keep_all", True):
        return True
    lowered = text.lower()
    includes = strategy.get("include_section_keywords", [])
    excludes = strategy.get("exclude_section_keywords", [])
    return (not includes or any(k in lowered for k in includes)) and not any(
        k in lowered for k in excludes
    )


def get_table_bboxes(page):
    try:
        return [table.bbox for table in page.find_tables()]
    except Exception:
        return []


def is_inside_table(obj, bboxes, tolerance=2.0):
    x, y = obj.get("x0", 0), obj.get("top", 0)
    return any(
        left - tolerance <= x <= right + tolerance and top - tolerance <= y <= bottom + tolerance
        for left, top, right, bottom in bboxes
    )


def load_metadata(path):
    if not path or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", data) if isinstance(data, dict) else data
    return {e["document_id"]: e for e in entries if isinstance(e, dict) and e.get("document_id")}


def identify(path, metadata):
    stem = path.stem.lower()
    return stem, metadata.get(stem, {})


def _checkpoint_text(checkpoint: Path, page_number: int) -> str:
    if not checkpoint.exists():
        return ""
    try:
        data = json.loads(checkpoint.read_text(encoding="utf-8"))
        page_state = data.get("pages", {}).get(str(page_number), {})
        page = page_state.get("page", page_state)
        return str(page.get("text", "")) if page_state.get("status") == "done" else ""
    except (OSError, json.JSONDecodeError, TypeError):
        return ""


def run_cleaner(input_dir, output_dir, metadata_path, strategies, excluded, logger, ocr_dir=None):
    files = sorted(Path(input_dir).rglob("*.pdf"))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metadata = load_metadata(Path(metadata_path) if metadata_path else None)
    ocr_root = Path(ocr_dir) if ocr_dir else None
    stats = {"processed": 0, "skipped": 0, "errors": []}
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber is required; install backend dependencies")
        return stats
    for path in files:
        if path.name in excluded:
            stats["skipped"] += 1
            continue
        doc, entry = identify(path, metadata)
        strategy = strategies.get(doc, {})
        pages = []
        try:
            with pdfplumber.open(path) as pdf:
                for page_number, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    if not text and ocr_root:
                        text = _checkpoint_text(ocr_root / doc / "checkpoint.json", page_number)
                    if text and should_keep_block(text, strategy):
                        pages.append(f"## Page {page_number}\n\n{clean_text(text, strategy)}")
            target = output / f"{doc}.md"
            target.write_text("\n\n".join(pages), encoding="utf-8")
            stats["processed"] += 1
        except Exception as exc:
            logger.exception("failed to process %s", path)
            stats["errors"].append(f"{path.name}: {type(exc).__name__}: {exc}")
    return stats


def cli(description, strategies, excluded, prefix):
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--manifest", type=Path, default=None)
    p.add_argument(
        "--ocr-dir",
        type=Path,
        default=None,
        help="Optional hybrid-OCR checkpoint root for image-only PDF pages.",
    )
    a = p.parse_args()
    print(
        json.dumps(
            run_cleaner(
                a.input,
                a.output,
                a.manifest,
                strategies,
                excluded,
                logging.getLogger(prefix),
                a.ocr_dir,
            ),
            ensure_ascii=False,
        )
    )
