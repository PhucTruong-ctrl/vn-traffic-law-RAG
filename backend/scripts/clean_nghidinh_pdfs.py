"""Clean decree PDFs into provenance-aware Markdown.

Usage: ``python scripts/clean_nghidinh_pdfs.py --input DIR --output DIR [--manifest FILE]``
"""

from __future__ import annotations

import logging

try:
    from .clean_pdf_common import cli, run_cleaner
except ImportError:  # direct script execution
    from clean_pdf_common import cli, run_cleaner

# The only filtering strategy supported by the current corpus metadata is the
# partial-effectivity legacy decree. Other reference-project strategies refer
# to documents absent from this checkout and are intentionally not applied.
STRATEGIES = {
    "nd-100-2019": {
        "keep_all": False,
        "prepend_warning": (
            "CẢNH BÁO: Mảng đường bộ của NĐ 100/2019 đã được thay thế; "
            "nội dung còn lại chỉ dùng cho tra cứu lịch sử."
        ),
        "include_section_keywords": ["đường sắt", "ray", "tàu hỏa", "ga đường sắt"],
        "exclude_section_keywords": [
            "đường bộ",
            "xe ô tô",
            "xe mô tô",
            "xe máy",
            "người điều khiển phương tiện",
        ],
    }
}
EXCLUDED_FILES: set[str] = set()


def process_pdfs(input_dir, output_dir, manifest=None):
    return run_cleaner(
        input_dir, output_dir, manifest, STRATEGIES, EXCLUDED_FILES, logging.getLogger(__name__)
    )


if __name__ == "__main__":
    cli(__doc__ or "Clean decree PDFs", STRATEGIES, EXCLUDED_FILES, "clean_nghidinh")
