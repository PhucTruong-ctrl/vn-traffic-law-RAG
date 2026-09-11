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
TERMINOLOGY_VERSION = "1.1.0"

#: Concepts that describe the requested evidence rather than the legal subject.
#: They must not be sufficient to scope a candidate provision by themselves.
GENERIC_CONCEPTS = frozenset(
    {
        "phạt tiền",
        "mức phạt tiền",
        "xử phạt vi phạm hành chính",
        "đăng ký",
        "giao thông đường bộ",
    }
)

#: Canonical term -> variant spellings (canonical term listed first).
#: Sources are the real corpus documents cited per entry.
TERMINOLOGY: dict[str, list[str]] = {
    "xe ô tô": ["xe ô tô", "xe ôtô", "xe otô", "xe oto", "ô tô", "ôtô", "oto"],
    "xe mô tô": ["xe mô tô", "xe môtô", "xe moto", "mô tô", "môtô"],
    "xe gắn máy": ["xe gắn máy", "xe gan may", "gắn máy"],
    "phạt tiền": ["phạt tiền", "phat tien"],
    "xử phạt vi phạm hành chính": [
        "xử phạt vi phạm hành chính",
        "xử phạt VPHC",
        "xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ",
        "vphc",
    ],
    "giấy phép lái xe": ["giấy phép lái xe", "GPLX", "gplx"],
    "nồng độ cồn": [
        "nồng độ cồn",
        "nồng độ cồn trong máu hoặc hơi thở",
        "nồng độ cồn trong máu",
        "nồng độ cồn trong hơi thở",
    ],
    "đăng ký": ["đăng ký", "đăng kí", "dang ky", "dang ki"],
    "vi phạm tốc độ": ["vi phạm tốc độ", "quá tốc độ", "chạy quá tốc độ", "toc do", "tốc độ"],
    "vi phạm làn đường": ["vi phạm làn đường", "sai làn", "đi sai làn", "lấn làn", "lan duong"],
    "giao thông đường bộ": [
        "giao thông đường bộ",
        "giao thông đuờng bộ",
        "giao thông duong bo",
    ],
    # Canonical concepts bridge colloquial questions and statutory wording.
    "không chấp hành hiệu lệnh của đèn tín hiệu giao thông": [
        "không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
        "không chấp hành hiệu lệnh đèn tín hiệu giao thông",
        "vượt đèn đỏ",
        "vượt đèn đỏ",
        "vuot den do",
        "đèn đỏ",
        "den do",
    ],
    "sử dụng điện thoại khi điều khiển xe": [
        "sử dụng điện thoại khi điều khiển xe",
        "dùng điện thoại khi lái xe",
        "sử dụng điện thoại",
        "dùng điện thoại",
        "điện thoại khi điều khiển",
    ],
    "không đội mũ bảo hiểm": [
        "không đội mũ bảo hiểm",
        "không đội mũ bảo hiểm khi đi xe",
        "không đội nón bảo hiểm",
        "mũ bảo hiểm",
        "nón bảo hiểm",
    ],
    "mức phạt tiền": ["mức phạt tiền", "phạt bao nhiêu", "tiền phạt"],
    "điểm giấy phép lái xe": ["điểm giấy phép lái xe", "điểm GPLX", "điểm bị trừ", "trừ điểm"],
    "tước đình chỉ giấy phép lái xe": [
        "tước đình chỉ giấy phép lái xe",
        "tước giấy phép lái xe",
        "đình chỉ giấy phép lái xe",
        "tước quyền sử dụng giấy phép lái xe",
        "thu hồi giấy phép lái xe",
    ],
    "hình thức phạt bổ sung": [
        "hình thức phạt bổ sung",
        "phạt bổ sung",
        "biện pháp bổ sung",
        "kèm theo",
        "ngoài phạt tiền",
    ],
}


def _term_key(term: str) -> str:
    """Build an OCR-tolerant canonical key for terminology matching."""
    text = unicodedata.normalize("NFKD", term.casefold())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("đ", "d")
    # OCR commonly splits/joins Vietnamese words and varies punctuation.
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


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


def terminology_concepts(text: str, version: str | None = None) -> set[str]:
    """Return canonical concepts mentioned in text, tolerating one joined token."""
    if version is not None and version != TERMINOLOGY_VERSION:
        raise ValueError(f"unsupported terminology version {version!r}")
    key = _term_key(text)
    compact = key.replace(" ", "")
    concepts: set[str] = set()
    for canonical, variants in TERMINOLOGY.items():
        for variant in variants:
            variant_key = _term_key(variant)
            if re.search(rf"(?<!\w){re.escape(variant_key)}(?!\w)", key):
                concepts.add(canonical)
                break
            words = variant_key.split()
            if len(words) > 1:
                for index in range(len(words) - 1):
                    joined = "".join(words[index : index + 2])
                    if joined in compact:
                        concepts.add(canonical)
                        break
                if canonical in concepts:
                    break
    return concepts


def concept_variants(concept: str, version: str | None = None) -> tuple[str, ...]:
    """Return all retrieval spellings for a canonical concept."""
    if version is not None and version != TERMINOLOGY_VERSION:
        raise ValueError(f"unsupported terminology version {version!r}")
    return tuple(TERMINOLOGY.get(concept, [concept]))


__all__ = [
    "TERMINOLOGY",
    "TERMINOLOGY_VERSION",
    "GENERIC_CONCEPTS",
    "canonical_term",
    "concept_variants",
    "terminology_concepts",
]
