"""Clean circular PDFs into provenance-aware Markdown.

Usage: ``python scripts/clean_thongtu_pdfs.py --input DIR --output DIR [--manifest FILE]``
"""

from __future__ import annotations

import logging

try:
    from .clean_pdf_common import cli, run_cleaner
except ImportError:  # direct script execution
    from clean_pdf_common import cli, run_cleaner

# No current manifest field authorizes the reference project's form-removal or
# TT51->TT79 merge strategies, so current documents retain their full text.
STRATEGIES = {
    "tt-24-2023": {"keep_all": True},
    "tt-79-2024": {"keep_all": True},
    "tt-51-2025": {"keep_all": True},
}
EXCLUDED_FILES: set[str] = set()


def process_pdfs(input_dir, output_dir, manifest=None):
    return run_cleaner(
        input_dir, output_dir, manifest, STRATEGIES, EXCLUDED_FILES, logging.getLogger(__name__)
    )


if __name__ == "__main__":
    cli(__doc__ or "Clean circular PDFs", STRATEGIES, EXCLUDED_FILES, "clean_thongtu")
