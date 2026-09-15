#!/usr/bin/env python3
"""Deterministically remove LuatVietnam page chrome from Markdown corpus files."""
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path

ARTICLE_RE = re.compile(r"^\s*(?:#{1,6}\s*)?Điều\s+\d+[A-Za-z]?\s*[.:]", re.I)
FRONT_RE = re.compile(r"\A---\s*\n.*?\n---\s*(?:\n|\Z)", re.S)
# These are page UI/marketing strings and metadata chrome, never legal provision text.
BOILERPLATE_MARKERS = (
    "Mục lục", "Tổng quan", "VB gốc", "So sánh VB", "VB song ngữ",
    "Tính năng này", "chỉ có tại LuatVietnam.vn", "Xem hướng dẫn chi tiết",
    "Đây là tiện ích dành cho tài khoản", "Vui lòng", "Đăng nhập",
    "Theo dõi VB", "Ghi chú", "Báo lỗi", "Để tải văn bản",
    "Nếu chưa có tài khoản", "Đăng ký", "Đã biết", "Tiêu chuẩn",
    "Cơ quan ban hành:", "Số công báo:", "Số hiệu:", "Ngày đăng công báo:",
    "Loại văn bản:", "Người ký:", "Trích yếu:", "Ngày cập nhật:",
    "Ngày ban hành là ngày", "Ngày hết hiệu lực là ngày",
    "Ngày áp dụng là ngày", "Tình trạng hiệu lực:",
)
METADATA_VALUE_RE = re.compile(
    r"^(?:Chính phủ|Bộ Giao thông Vận tải|Nghị định|Thông tư|"
    r"Số công báo là mã số .*quản lý\.|Đang cập nhật|"
    r"Tiện ích dành cho tài khoản|hoặc|Nâng cao|tài khoản để xem chi tiết\.|"
    r"\.)\s*$",
    re.I,
)
SUMMARY_RE = re.compile(r"^\s*(?:TÓM TẮT|Tóm tắt|Nội dung đáng chú ý|Một số nội dung đáng chú ý)", re.I)
UI_EXACT_RE = re.compile(
    r"^(?:Tiện ích dành cho tài khoản|tài khoản để xem chi tiết\.|"
    r"hoặc|Nâng cao|\.)\s*$",
    re.I,
)

@dataclass(frozen=True)
class CleanStats:
    before_lines: int
    after_lines: int
    articles_before: int
    articles_after: int
    removed_lines: int

def _is_chrome(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    return bool(
        UI_EXACT_RE.match(text)
        or METADATA_VALUE_RE.match(text)
        or any(marker.casefold() in text.casefold() for marker in BOILERPLATE_MARKERS)
    )


def clean_markdown(source: str) -> tuple[str, CleanStats]:
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    front = FRONT_RE.match(source)
    prefix = front.group(0) if front else ""
    body = source[front.end():] if front else source
    lines = body.splitlines()
    before_articles = sum(bool(ARTICLE_RE.match(line)) for line in lines)

    # Start at the first actual provision heading; this drops navigation and
    # summaries but retains the legal preamble when it contains no article.
    first_article = next((i for i, line in enumerate(lines) if ARTICLE_RE.match(line)), None)
    if first_article is None:
        raise ValueError("no legal Điều heading found")
    kept = [line for line in lines[:first_article] if not _is_chrome(line)]
    in_summary = False
    for line in lines[first_article:]:
        if SUMMARY_RE.match(line):
            in_summary = True
            continue
        if in_summary:
            if ARTICLE_RE.match(line):
                in_summary = False
            else:
                continue
        if _is_chrome(line):
            continue
        kept.append(line)

    # Remove exact duplicate publisher blocks/lines while preserving first legal occurrence.
    deduped: list[str] = []
    seen_nonlegal: set[str] = set()
    for line in kept:
        normalized = re.sub(r"\s+", " ", line.strip()).casefold()
        if normalized and not ARTICLE_RE.match(line) and _is_chrome(line):
            if normalized in seen_nonlegal:
                continue
            seen_nonlegal.add(normalized)
        deduped.append(line)
    while deduped and not deduped[-1].strip():
        deduped.pop()
    output_body = "\n".join(deduped).strip() + "\n"
    after_articles = sum(bool(ARTICLE_RE.match(line)) for line in deduped)
    if after_articles < 2:
        raise ValueError(f"cleanup would leave only {after_articles} legal articles")
    output = prefix + output_body
    return output, CleanStats(len(source.splitlines()), len(output.splitlines()), before_articles, after_articles, len(source.splitlines()) - len(output.splitlines()))


def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def process_directory(directory: Path, dry_run: bool = False) -> int:
    paths = sorted(path for path in directory.glob("*.md") if path.name.casefold() != "readme.md")
    if not paths:
        raise SystemExit(f"No Markdown corpus files found in {directory}")
    failures = 0
    for path in paths:
        original = path.read_text(encoding="utf-8", errors="replace")
        try:
            cleaned, stats = clean_markdown(original)
            if not cleaned.strip() or not FRONT_RE.match(cleaned):
                raise ValueError("refusing to produce empty file or lose front matter")
            if not dry_run and cleaned != original:
                atomic_write(path, cleaned)
            action = "DRY-RUN" if dry_run else "CLEAN"
            print(f"{action} {path.name}: removed {stats.removed_lines} lines; articles {stats.articles_before}->{stats.articles_after}")
        except ValueError as exc:
            failures += 1
            print(f"ERROR {path.name}: {exc}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path("data/corpus/mds"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return process_directory(args.dir.expanduser().resolve(), args.dry_run)

if __name__ == "__main__":
    raise SystemExit(main())
