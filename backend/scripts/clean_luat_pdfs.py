"""Clean law PDFs into provenance-aware Markdown.

Usage: ``python scripts/clean_luat_pdfs.py --input DIR --output DIR [--manifest FILE]``
"""

from __future__ import annotations

import logging

try:
    from .clean_pdf_common import cli, run_cleaner
except ImportError:  # direct script execution
    from clean_pdf_common import cli, run_cleaner

STRATEGIES = {"luat-35-2024-qh15": {"keep_all": True}, "luat-36-2024-qh15": {"keep_all": True}}
EXCLUDED_FILES: set[str] = set()


def process_law_pdfs(input_dir, output_dir, manifest=None):
    return run_cleaner(
        input_dir, output_dir, manifest, STRATEGIES, EXCLUDED_FILES, logging.getLogger(__name__)
    )


if __name__ == "__main__":
    cli(__doc__ or "Clean law PDFs", STRATEGIES, EXCLUDED_FILES, "clean_luat")
