"""Legal metadata normalization (VNLRAG-27).

Implements the normalization layer defined in
``docs/rulespec/vietnamese-legal-parsing-rules.md`` (VNLRAG-23 v2 rules) that
sits between :class:`ExtractedDocumentMetadata` and persistence
(doc 03 §3.9.3):

- §2 document type is read from the manifest, never inferred from IR text;
  Vietnamese type prefixes are mapped to the ``DocumentType`` enum
  (multi-word-first, reusing the extractor's ``_DOCUMENT_TYPE_PREFIXES``
  table).  The manifest's ``document_type`` is authoritative when present and
  valid.
- §4 d)/đ) handling: ``đ`` is kept distinct from ``d`` in labels and IDs.  A
  bare ``d)`` label is d↔đ OCR-ambiguous and is routed to review
  (``needs_review``) instead of guessed, unless ordinal position in the point
  run (a→b→c→d→đ→e, PRIMARY rule) disambiguates it.  A literal ``đ)`` is
  always kept as ``đ)``.
- §8 temporal: dates are normalized to ``date`` from ISO 8601 / dd/mm/yyyy /
  Vietnamese forms ("ngày 26 tháng 12 năm 2024"); unparseable or ambiguous
  values become ``None`` with a ``needs_review`` flag — never guessed.  The
  manifest remains authoritative for the projected ``DocumentVersion``
  interval, which is applied at the projection boundary in
  :mod:`app.ingestion.projection`; this module only canonicalizes the form of
  the extracted temporal signals.
- §9 OCR variants: glued point labels (``a)Điều``), Unicode Roman numerals
  (Ⅰ/Ⅱ/Ⅲ → I/II/III), d↔đ confusion and header/footer leakage are detected
  and either canonicalized or flagged for review — never silently rewritten.

Manifest authority is applied here for ``document_type`` and ``issuer`` (the
manifest value wins when present and valid); the extracted values are
canonicalized in form and, when unmappable, set to ``None`` with a review
flag.  Text fields get unicode NFC + whitespace collapse + full-width
cleanup.

The module is deterministic, parser-neutral and side-effect free.  Every
public function is idempotent on canonical inputs, so already-normalized
values pass through unchanged and existing extractor/projection behavior is
preserved.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.ingestion.metadata_extractor import (
    _DOCUMENT_TYPE_PREFIXES,
    _VALID_DOCUMENT_TYPES,
    ExtractedDocumentMetadata,
)

#: ISO ``YYYY-MM-DD`` (or full ISO 8601 date-time) parsed via date.fromisoformat.
#: dd/mm/yyyy in the official Vietnamese day-first convention.
_DMY_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")

#: Official Vietnamese long form: "ngày 26 tháng 12 năm 2024".
_VIETNAMESE_DATE_RE = re.compile(
    r"^ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})$", re.IGNORECASE
)

#: Leading point label token: optional "Điểm" prefix, one Vietnamese point
#: letter, then an ASCII or full-width close paren (glued labels allowed:
#: "a)Điều khiển ..." still yields label "a)").
_POINT_LABEL_LEAD_RE = re.compile(r"^\s*(?:điểm\s+)?([a-zđA-ZĐ])[)）]", re.IGNORECASE)

#: Glued point label inside running text: "a)Điều" -> "a) Điều".
_GLUED_POINT_LABEL_RE = re.compile(r"([a-zđ])\)(\S)")

#: Issuer keyword -> canonical issuer name.  Order matters: more specific
#: keywords are matched first (substring match on the casefolded value), and
#: entries whose keyword contains another keyword must come before it.
_ISSUER_CANONICAL: tuple[tuple[str, str], ...] = (
    ("văn phòng quốc hội", "Văn phòng Quốc hội"),
    ("ủy ban thường vụ quốc hội", "Ủy ban Thường vụ Quốc hội"),
    ("bộ nông nghiệp và phát triển nông thôn", "Bộ Nông nghiệp và Phát triển nông thôn"),
    ("bộ giao thông vận tải", "Bộ Giao thông vận tải"),
    ("bộ công an", "Bộ Công an"),
    ("bộ tư pháp", "Bộ Tư pháp"),
    ("bộ y tế", "Bộ Y tế"),
    ("bộ tài chính", "Bộ Tài chính"),
    ("bộ xây dựng", "Bộ Xây dựng"),
    ("bộ nông nghiệp", "Bộ Nông nghiệp và Phát triển nông thôn"),
    ("thủ tướng chính phủ", "Thủ tướng Chính phủ"),
    ("chính phủ", "Chính phủ"),
    ("quốc hội", "Quốc hội"),
    ("tòa án nhân dân tối cao", "Tòa án nhân dân tối cao"),
    ("viện kiểm sát nhân dân tối cao", "Viện kiểm sát nhân dân tối cao"),
)

#: Repeated document chrome that is not legal content (doc 03 §3.7 header /
#: footer boilerplate).  Stripped from the issuer value before keyword
#: matching; a value consisting of only boilerplate becomes ``None`` + review
#: flag (never guessed).  Dash variants cover OCR punctuation drift.
_ISSUER_NOISE: tuple[str, ...] = (
    "cộng hòa xã hội chủ nghĩa việt nam",
    "độc lập - tự do - hạnh phúc",
    "độc lập – tự do – hạnh phúc",
    "độc lập — tự do — hạnh phúc",
)

#: Unicode Roman numeral block (U+2160–U+217F) -> ASCII (OCR variants,
#: rulespec §9: "chữ số La Mã bị lẫn (Chương I/II/III…)").
_ROMAN_NUMERAL_MAP: dict[str, str] = {
    "\u2160": "I",  # Ⅰ
    "\u2161": "II",  # Ⅱ
    "\u2162": "III",  # Ⅲ
    "\u2163": "IV",  # Ⅳ
    "\u2164": "V",  # Ⅴ
    "\u2165": "VI",  # Ⅵ
    "\u2166": "VII",  # Ⅶ
    "\u2167": "VIII",  # Ⅷ
    "\u2168": "IX",  # Ⅸ
    "\u2169": "X",  # Ⅹ
    "\u216a": "XI",  # Ⅺ
    "\u216b": "XII",  # Ⅻ
    "\u216c": "L",  # Ⅼ
    "\u216d": "C",  # Ⅽ
    "\u216e": "D",  # Ⅾ
    "\u216f": "M",  # Ⅿ
    "\u2170": "i",  # ⅰ
    "\u2171": "ii",  # ⅱ
    "\u2172": "iii",  # ⅲ
    "\u2173": "iv",  # ⅳ
    "\u2174": "v",  # ⅴ
    "\u2175": "vi",  # ⅵ
    "\u2176": "vii",  # ⅶ
    "\u2177": "viii",  # ⅷ
    "\u2178": "ix",  # ⅸ
    "\u2179": "x",  # ⅹ
    "\u217a": "xi",  # ⅺ
    "\u217b": "xii",  # ⅻ
    "\u217c": "l",  # ⅼ
    "\u217d": "c",  # ⅽ
    "\u217e": "d",  # ⅾ
    "\u217f": "m",  # ⅿ
}
_ROMAN_NUMERAL_TRANS = str.maketrans(_ROMAN_NUMERAL_MAP)

#: Vietnamese point-run alphabet with ordinal positions (rulespec §4.1:
#: d = position 4, đ = position 5).
_POINT_RUN_ALPHABET = "abcdđe"


class NormalizationResult(BaseModel):
    """Canonical metadata plus the review flags raised during normalization.

    ``needs_review`` entries describe the *original* extraction quality (they
    are input-derived): a value that was ambiguous or unmappable and was set
    to ``None`` (never guessed) is recorded here so the caller can route the
    document to review.  Re-normalizing the output metadata produces no new
    flags (the metadata is a fixpoint).
    """

    model_config = ConfigDict(extra="forbid")

    metadata: ExtractedDocumentMetadata
    needs_review: list[str]


def _clean_text(value: str | None) -> str | None:
    """Unicode NFC + whitespace collapse + full-width cleanup on a text value.

    ``NFKC`` maps full-width ASCII/space variants and Unicode Roman numerals
    to their canonical half-width forms; ``NFC`` then composes Vietnamese
    diacritics.  Runs of whitespace (including newlines and full-width
    spaces) collapse to a single space.
    """

    if value is None:
        return None
    text = unicodedata.normalize("NFKC", value)
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_document_type(value: str | None, needs_review: list[str]) -> str | None:
    """Map a Vietnamese type prefix to the ``DocumentType`` enum.

    Multi-word prefixes are matched first (reusing the extractor's
    ``_DOCUMENT_TYPE_PREFIXES`` table, rulespec §2).  An already-valid enum
    value passes through.  An unrecognized value becomes ``None`` with a
    review flag — never guessed.  The manifest value, when present and valid,
    is authoritative and wins over the extracted mapping.
    """

    mapped: str | None = None
    if value is not None:
        cleaned = _clean_text(value)
        upper = cleaned.upper() if cleaned else ""
        if upper in _VALID_DOCUMENT_TYPES:
            mapped = upper
        else:
            for prefix, document_type in _DOCUMENT_TYPE_PREFIXES:
                if upper == prefix or upper.startswith(prefix + " "):
                    mapped = document_type
                    break
            if mapped is None:
                needs_review.append(
                    f"document_type: {value!r} is not a known Vietnamese type prefix; "
                    "set to None (never guess)"
                )
    return mapped


def _normalize_issuer(value: str | None, needs_review: list[str]) -> str | None:
    """Canonicalize an issuer via the keyword map and strip boilerplate noise.

    A value that is only repeated document chrome (republic header / motto)
    becomes ``None`` with a review flag.  An unrecognized real name is kept
    as-is (cleaned) — the normalizer never invents issuers.
    """

    if value is None:
        return None
    cleaned = _clean_text(value)
    lowered = cleaned.casefold() if cleaned else ""
    for noise in _ISSUER_NOISE:
        lowered = lowered.replace(noise, " ")
    lowered = re.sub(r"\s+", " ", lowered).strip()
    if not lowered:
        needs_review.append(
            f"issuer: {value!r} is only document boilerplate; set to None (never guess)"
        )
        return None
    for keyword, canonical in _ISSUER_CANONICAL:
        if keyword in lowered:
            return canonical
    return cleaned


def _normalize_date(value: object, needs_review: list[str], field: str) -> date | None:
    """Normalize a date value to ``date`` without ever guessing.

    Accepts ``date`` / ``datetime`` objects and ISO 8601, dd/mm/yyyy
    (Vietnamese day-first convention) or official Vietnamese long-form
    strings.  Unparseable, impossible or ambiguous values (e.g. two-digit
    years, month 13) become ``None`` with a review flag (rulespec §8:
    "KHÔNG đoán").
    """

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = _clean_text(value)
        if not cleaned:
            needs_review.append(f"{field}: empty date value → None (never guess)")
            return None
        # ISO 8601 date or full date-time (strict — no silent truncation).
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(cleaned).date()
        except ValueError:
            pass
        # dd/mm/yyyy (day-first) and "ngày D tháng M năm Y" (Vietnamese).
        for pattern in (_DMY_DATE_RE, _VIETNAMESE_DATE_RE):
            match = pattern.match(cleaned)
            if match is not None:
                day, month, year = (int(group) for group in match.groups())
                try:
                    return date(year, month, day)
                except ValueError:
                    needs_review.append(f"{field}: invalid date {value!r} → None (never guess)")
                    return None
        needs_review.append(f"{field}: unparseable date {value!r} → None (never guess)")
        return None
    needs_review.append(f"{field}: unexpected date value {value!r} → None (never guess)")
    return None


def normalize_metadata(
    metadata: ExtractedDocumentMetadata, manifest: dict[str, object]
) -> NormalizationResult:
    """Canonicalize extracted metadata per the VNLRAG-23 v2 rules.

    Returns :class:`NormalizationResult` — ``.metadata`` carries the
    canonicalized :class:`ExtractedDocumentMetadata` (a fixpoint of this
    function), ``.needs_review`` lists the review flags raised for ambiguous
    or unmappable values.  The manifest is authoritative for
    ``document_type`` and ``issuer`` (its value wins when present and valid);
    dates and text fields are normalized in form only.  Idempotent on
    canonical inputs.
    """

    needs_review: list[str] = []

    manifest_type = manifest.get("document_type")
    mapped_type = _normalize_document_type(metadata.document_type, needs_review)
    document_type: str | None
    if isinstance(manifest_type, str) and manifest_type in _VALID_DOCUMENT_TYPES:
        document_type = manifest_type  # manifest is authoritative (§2)
    else:
        document_type = mapped_type

    manifest_issuer = manifest.get("issuer")
    issuer_source = (
        manifest_issuer
        if isinstance(manifest_issuer, str) and manifest_issuer.strip()
        else metadata.issuer
    )
    issuer = _normalize_issuer(issuer_source, needs_review)

    normalized = ExtractedDocumentMetadata(
        document_title=_clean_text(metadata.document_title),
        document_number=_clean_text(metadata.document_number),
        document_type=document_type,
        issuer=issuer,
        issued_date=_normalize_date(metadata.issued_date, needs_review, "issued_date"),
        effective_from=_normalize_date(metadata.effective_from, needs_review, "effective_from"),
        effective_to=_normalize_date(metadata.effective_to, needs_review, "effective_to"),
    )
    return NormalizationResult(metadata=normalized, needs_review=needs_review)


def normalize_roman_numeral(token: str) -> str:
    """Normalize Unicode Roman numerals (Ⅰ/Ⅱ/Ⅲ …) to ASCII (I/II/III …).

    OCR variants of chapter numbers ("Chương Ⅱ") collapse to the canonical
    ASCII forms.  Already-ASCII input (and any other text in ``token``) is
    passed through unchanged — idempotent.
    """

    return token.translate(_ROMAN_NUMERAL_TRANS)


def normalize_provision_text(text: str) -> str:
    """Retrieval-side text normalization (rulespec §9 OCR variants).

    Applies unicode NFC + whitespace collapse + full-width cleanup and fixes
    glued point labels (``a)Điều`` → ``a) Điều``).  This is the canonical
    point-label spacing form; d/đ letter decisions are never made here (see
    :func:`canonical_point_label`).  Idempotent on canonical text and never
    mutates ``source_text`` — callers apply it to ``retrieval_text`` only.
    """

    text = unicodedata.normalize("NFKC", text)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _GLUED_POINT_LABEL_RE.sub(r"\1) \2", text)


def canonical_point_label(label: str, *, ordinal: int | None = None) -> str | None:
    """Canonical point label form (``"a)"`` … ``"đ)"``) or ``None``.

    Handles OCR variants: optional ``Điểm`` prefix, case-folded letters,
    full-width parens and glued labels (``a)Điều khiển …`` still yields
    ``"a)"``).

    d↔đ handling (rulespec §4, PRIMARY rule ``a→b→c→d→đ→e``):
    - a literal ``đ)`` is self-identifying and always kept as ``đ)`` (the đ
      character is preserved, distinct from d);
    - a bare ``d)`` is d↔đ OCR-ambiguous: with ``ordinal`` 4 or 5 (1-based
      position in the point run, d = 4, đ = 5) it resolves to ``"d)"`` or
      ``"đ)"`` respectively; without ordinal context it returns ``None`` —
      the caller must flag ``needs_review`` (never a silent wrong guess).
    - a d/đ label at any other ordinal is structurally inconsistent →
      ``None`` (review).
    """

    if not isinstance(label, str) or not label.strip():
        return None
    match = _POINT_LABEL_LEAD_RE.match(label)
    if match is None:
        return None
    char = match.group(1).casefold()
    if char == "đ":
        return "đ)"
    if char == "d":
        if ordinal == 4:
            return "d)"
        if ordinal == 5:
            return "đ)"
        return None  # d↔đ ambiguous without ordinal context → needs_review
    return f"{char})"


def is_header_footer_leakage(text: str) -> bool:
    """Conservative detector for repeated document header/footer chrome.

    Returns ``True`` only when the (cleaned) text contains the full republic
    header block — the official "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM / Độc
    lập - Tự do - Hạnh phúc" boilerplate (rulespec §9: header/footer leakage
    removal with needs_review flags, never guess).  Detected leakage is
    routed to review by the caller; text normalization never deletes content.
    """

    cleaned = _clean_text(text)
    if not cleaned:
        return False
    lowered = cleaned.casefold()
    if _ISSUER_NOISE[0] not in lowered:
        return False
    return any(motto in lowered for motto in _ISSUER_NOISE[1:])


__all__ = [
    "NormalizationResult",
    "canonical_point_label",
    "is_header_footer_leakage",
    "normalize_metadata",
    "normalize_provision_text",
    "normalize_roman_numeral",
]
