from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

RE_HEADER_NOISE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},.*about:blank$", re.I)
RE_FOOTER_NOISE = re.compile(r"about:blank\s+\d+/\d+|Thư viện pháp luật|Mã tra cứu", re.I)
RE_PAGE_NUM = re.compile(r"^(Trang\s+)?\d+(\s*/\s*\d+)?$", re.I)
RE_FORM_DOTS = re.compile(r"(\.{5,}|_{5,})")
RE_CHECKBOX = re.compile(r"([☐☑\uf06f])")
RE_IS_HEADING = re.compile(
    r"^(Điều\s+\d+|Khoản\s+\d+|Chương\s+[IVXLCDM]+|Phần\s+[IVXLCDM]+|\d+\.\s+[A-ZĐÀÁẠẢÃ]|[a-zđ]\)\s+)",
    re.I,
)
RE_MERGE_END = re.compile(r"[a-zA-ZÀ-ỹđĐ,;]$")


def clean_text(raw_text: str, strategy: dict[str, Any] | None = None) -> str:
    if not raw_text:
        return ""
    lines = []
    for raw in unicodedata.normalize("NFC", raw_text).splitlines():
        line = raw.strip()
        if (
            not line
            or RE_HEADER_NOISE.match(line)
            or RE_FOOTER_NOISE.search(line)
            or RE_PAGE_NUM.match(line)
        ):
            continue
        line = RE_FORM_DOTS.sub(" [Cần điền thông tin] ", line)
        line = RE_CHECKBOX.sub(" [Lựa chọn] ", line).strip()
        if line in {"", "[Cần điền thông tin]", "[Lựa chọn]"}:
            continue
        line = re.sub(r"^(Chương\s+[IVXLCDM]+.*|Phần\s+[IVXLCDM]+.*)$", r"# \1", line, flags=re.I)
        line = re.sub(
            r"^(Điều\s+\d+[.:].*)", lambda m: "## " + m.group(0).lstrip("# "), line, flags=re.I
        )
        line = re.sub(
            r"^(Khoản\s+\d+[.:].*)", lambda m: "### " + m.group(0).lstrip("# "), line, flags=re.I
        )
        line = re.sub(
            r"^(Điểm\s+[a-zđ][).:].*)",
            lambda m: "#### " + m.group(0).lstrip("# "),
            line,
            flags=re.I,
        )
        line = re.sub(
            r"(ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})", r"**\1**", line, flags=re.I
        )
        line = re.sub(r"\b(CO2?|HC|NOx|PM2\.5|mg/l)\b", r"$$\1$$", line)
        lines.append(line)
    merged = []
    for line in lines:
        if (
            merged
            and RE_MERGE_END.search(merged[-1][-1:])
            and (
                line[0].islower()
                or line[0] in "áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ"
            )
            and not RE_IS_HEADING.match(line)
        ):
            merged[-1] += " " + line
        else:
            merged.append(line)
    result = "\n".join(merged)
    warning = (strategy or {}).get("prepend_warning")
    return f"> {warning}\n\n{result}" if warning else result


def table_to_markdown(data: list) -> str:
    rows = [r for r in (data or []) if any(c and str(c).strip() for c in r)]
    if not rows:
        return ""
    n = max(map(len, rows))
    rows = [r + [""] * (n - len(r)) for r in rows]
    last = [""] * n
    out = []
    for i, row in enumerate(rows):
        vals = []
        for j, c in enumerate(row):
            v = str(c).replace("\n", " ").strip() if c else ""
            v = v or last[j]
            last[j] = v
            vals.append(v.replace("|", "\\|"))
        out.append("| " + " | ".join(vals) + " |")
        if i == 0:
            out.append("|" + "|".join(["---"] * n) + "|")
    return "\n".join(out)


def should_keep_block(text, strategy):
    if strategy.get("keep_all", True):
        return True
    low = text.lower()
    inc = strategy.get("include_section_keywords", [])
    exc = strategy.get("exclude_section_keywords", [])
    return (not inc or any(k.lower() in low for k in inc)) and not any(
        k.lower() in low for k in exc
    )


def get_table_bboxes(page):
    try:
        return [t.bbox for t in page.find_tables()]
    except Exception:
        return []


def is_inside_table(obj, bboxes, tolerance=2.0):
    x, y = obj.get("x0", 0), obj.get("top", 0)
    return any(
        a - tolerance <= x <= c + tolerance and b - tolerance <= y <= d + tolerance
        for a, b, c, d in bboxes
    )


def load_metadata(path):
    if not path or not path.exists():
        return {}
    p = json.loads(path.read_text(encoding="utf-8"))
    entries = p.get("entries", p if isinstance(p, list) else [])
    return {e["document_id"]: e for e in entries if isinstance(e, dict) and e.get("document_id")}


def identify(path, metadata):
    stem = path.stem.lower()
    for doc, e in metadata.items():
        candidates = [
            doc.lower(),
            str(e.get("source_version", "")).lower().replace("/", "-"),
            Path(str(e.get("source_url", ""))).stem.lower(),
        ]
        if any(c and (stem == c or stem in c or c in stem) for c in candidates):
            return doc, e
    return path.stem, {}


def run_cleaner(input_dir, output_dir, metadata_path, strategies, excluded, logger):
    files = sorted(Path(input_dir).rglob("*.pdf"))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    meta = load_metadata(metadata_path)
    stats = {"total": len(files), "processed": 0, "skipped": 0, "errors": 0, "files": {}}
    if files:
        try:
            import pdfplumber
        except ImportError as e:
            raise SystemExit("pdfplumber is required; install backend dependencies") from e
        for pdf in files:
            if pdf.name in excluded:
                stats["skipped"] += 1
                continue
            doc, manifest = identify(pdf, meta)
            strategy = strategies.get(doc, strategies.get(pdf.name, {"keep_all": True}))
            content = []
            pages = tables = chars = filtered = 0
            try:
                with pdfplumber.open(pdf) as source:
                    pages = len(source.pages)
                    for page in source.pages:
                        boxes = get_table_bboxes(page)
                        text = (
                            page.filter(
                                lambda o, boxes=boxes: not is_inside_table(o, boxes)
                            ).extract_text()
                            if boxes
                            else page.extract_text()
                        )
                        cleaned = clean_text(text, strategy)
                        if cleaned and should_keep_block(cleaned, strategy):
                            content.append(cleaned)
                            chars += len(cleaned)
                        elif cleaned:
                            filtered += 1
                        for table in page.extract_tables(
                            table_settings={
                                "vertical_strategy": "lines",
                                "horizontal_strategy": "lines",
                                "snap_tolerance": 3,
                                "join_tolerance": 3,
                            }
                        ):
                            md = table_to_markdown(table)
                            if md:
                                content.append(md)
                                tables += 1
                out = output_dir / f"{doc}.md"
                out.write_text("\n\n".join(content), encoding="utf-8")
                stats["processed"] += 1
                stats["files"][str(pdf.relative_to(input_dir))] = {
                    "document_id": doc,
                    "manifest": manifest,
                    "pages": pages,
                    "tables": tables,
                    "chars": chars,
                    "filtered_blocks": filtered,
                    "output": str(out),
                    "input_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                }
            except Exception:
                logger.exception("failed to clean %s", pdf)
                stats["errors"] += 1
    (output_dir / "_processing_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def cli(description, strategies, excluded, prefix):
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data/candidate-corpus-manifest.json",
    )
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(
        json.dumps(
            run_cleaner(
                a.input, a.output, a.manifest, strategies, excluded, logging.getLogger(prefix)
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
