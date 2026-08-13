"""Versioned terminology normalization for Vietnamese legal text (VNLRAG-27).

Provides a deterministic, documented mapping of canonical legal terms to
their spelling / OCR variants, sourced from the real corpus documents under
``data/`` (nd-168-2024, tt-24-2023, tt-79-2024, luat-36-2024).  Query-time
expansion itself is out of scope for this ticket — this module is the shared,
versioned vocabulary that expansion (and retrieval-side normalization) will
reuse.

Each ``TERMINOLOGY`` entry lists the canonical term first, then its variant
spellings (OCR diacritic loss, y/i variants, spacing variants, common
abbreviations).  Matching is exact on the whole (casefolded, NFC, whitespace-
collapsed) term; unknown terms pass through unchanged.  ``canonical_term`` is
pinned to ``TERMINOLOGY_VERSION`` so consumers can assert they are using the
vocabulary they expect.
"""

from __future__ import annotations

import re
import unicodedata

#: Current terminology vocabulary version.  Bump on any incompatible change
#: to :data:`TERMINOLOGY` (added/removed/renamed canonical terms or variants).
TERMINOLOGY_VERSION = "1.0.0"

#: Canonical term -> variant spellings (canonical term listed first).
#: Sources are the real corpus documents cited per entry.
TERMINOLOGY: dict[str, list[str]] = {
    # nd-168-2024 Điều 5: "xe ô tô và các loại xe tương tự xe ô tô".
    "xe ô tô": [
        "xe ô tô",
        "xe ôtô",
        "xe otô",
        "xe oto",
        "ô tô",
        "ôtô",
        "oto",
    ],
    # nd-168-2024 Điều 7: "xe mô tô, xe gắn máy".
    "xe mô tô": [
        "xe mô tô",
        "xe môtô",
        "xe moto",
        "mô tô",
        "môtô",
    ],
    "xe gắn máy": [
        "xe gắn máy",
        "xe gan may",
        "gắn máy",
    ],
    # nd-168-2024 Điều 5 Khoản 1: "Phạt tiền từ 800.000 đồng ...".
    "phạt tiền": [
        "phạt tiền",
        "phat tien",
    ],
    # nd-168-2024 title: "XỬ PHẠT VI PHẠM HÀNH CHÍNH TRONG LĨNH VỰC ...".
    "xử phạt vi phạm hành chính": [
        "xử phạt vi phạm hành chính",
        "xử phạt VPHC",
        "xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ",
        "vphc",
    ],
    # nd-168-2024 Điều 7 Khoản 1: "giấy phép lái xe".
    "giấy phép lái xe": [
        "giấy phép lái xe",
        "GPLX",
        "gplx",
    ],
    # nd-168-2024 Khoản 3/4: "nồng độ cồn vượt quá mức quy định".
    "nồng độ cồn": [
        "nồng độ cồn",
        "nồng độ cồn trong máu hoặc hơi thở",
        "nồng độ cồn trong máu",
        "nồng độ cồn trong hơi thở",
    ],
    # tt-24-2023 Điều 5: "Hồ sơ đăng ký học lái xe" (y/i variant + OCR loss).
    "đăng ký": [
        "đăng ký",
        "đăng kí",
        "dang ky",
        "dang ki",
    ],
    # nd-168-2024 / tt-24-2023 titles; OCR misplaced-mark variant included.
    "giao thông đường bộ": [
        "giao thông đường bộ",
        "giao thông đuờng bộ",
        "giao thông duong bo",
    ],
}


def _term_key(term: str) -> str:
    """Deterministic lookup key: NFC + casefold + whitespace collapse."""
    text = unicodedata.normalize("NFC", term)
    return re.sub(r"\s+", " ", text).strip().casefold()


#: variant key (casefolded) -> canonical term.  Variants are listed with the
#: canonical term first, so the canonical form is always part of its own
#: entry; duplicate keys (e.g. "GPLX"/"gplx") collapse deterministically.
_VARIANT_TO_CANONICAL: dict[str, str] = {}
for _canonical, _variants in TERMINOLOGY.items():
    for _variant in _variants:
        _VARIANT_TO_CANONICAL[_term_key(_variant)] = _canonical


def canonical_term(term: str, version: str | None = None) -> str:
    """Map a variant spelling to its canonical term.

    ``version`` pins the expected terminology vocabulary: passing a version
    other than :data:`TERMINOLOGY_VERSION` raises ``ValueError`` so callers
    never silently use an unexpected vocabulary.  Unknown terms pass through
    unchanged (deterministic, no guessing).
    """

    if version is not None and version != TERMINOLOGY_VERSION:
        raise ValueError(
            f"unsupported terminology version {version!r}; "
            f"current version is {TERMINOLOGY_VERSION!r}"
        )
    return _VARIANT_TO_CANONICAL.get(_term_key(term), term)


__all__ = ["TERMINOLOGY", "TERMINOLOGY_VERSION", "canonical_term"]
