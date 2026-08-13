"""Legal metadata extraction from the Canonical Document IR (VNLRAG-25).

v2: UDEF is gone; the extractor reads only the canonical
:mod:`app.ingestion.document_ir` models and produces the LegalDocument /
DocumentVersion metadata fields defined in doc 03 §3.9.3.  The corpus
manifest (VNLRAG-16) is the authoritative source for document identity;
extraction is a deterministic cross-check that flags mismatches for review
(doc 03 §3.7.5 auto-accept policy: manifest metadata that contradicts the
official source is routed to review, never auto-accepted).

This module is intentionally parser-neutral and side-effect free: no Docling /
MinerU objects, no persistence sessions.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.ingestion.document_ir import DocumentElement, ParsedDocument

# Vietnamese document number, e.g. 168/2024/NĐ-CP, 36/2024/QH15, 24/2023/TT-BCA,
# 49/VBHN-VPQH.  The authority suffix may end in digits (QH15).
_DOCUMENT_NUMBER_RE = re.compile(r"\b(\d{1,4}/\d{4}/[A-ZĐ][A-ZĐ0-9-]*)\b")

# Issued date in the official Vietnamese form: "Hà Nội, ngày 26 tháng 12 năm 2024".
_ISSUED_DATE_RE = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.I)
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Effective-start clauses: "Nghị định này có hiệu lực thi hành từ ngày ...".
# Effective-start clauses: "Nghị định này có hiệu lực thi hành từ ngày ...",
# "có hiệu lực thi hành kể từ ngày ..." (official TT 24/2023 wording).
_EFFECTIVE_FROM_RE = re.compile(
    r"(?:có hiệu lực|kể từ)\s+(?:thi hành\s+)?(?:kể\s+)?từ\s+ngày\s+"
    r"(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})"
    r"|(?:có hiệu lực|kể từ)\s+(?:thi hành\s+)?(?:kể\s+)?từ\s+ngày\s+"
    r"(\d{1,2})/(\d{1,2})/(\d{4})",
    re.I,
)

#: Type prefix -> canonical DocumentType value (doc 03 §3.9.1).  Order matters:
#: multi-word prefixes are matched first.
_DOCUMENT_TYPE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("VĂN BẢN HỢP NHẤT", "OTHER"),
    ("THÔNG TƯ LIÊN TỊCH", "CIRCULAR"),
    ("NGHỊ ĐỊNH", "DECREE"),
    ("THÔNG TƯ", "CIRCULAR"),
    ("QUYẾT ĐỊNH", "DECISION"),
    ("NGHỊ QUYẾT", "RESOLUTION"),
    ("LUẬT", "LAW"),
)

#: Known issuer keywords matched against the first-page text (best effort).
_ISSUER_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("văn phòng quốc hội", "Văn phòng Quốc hội"),
    ("quốc hội", "Quốc hội"),
    ("bộ giao thông vận tải", "Bộ Giao thông vận tải"),
    ("bộ công an", "Bộ Công an"),
    ("chính phủ", "Chính phủ"),
)

_VALID_STATUSES = {
    "NOT_YET_EFFECTIVE",
    "EFFECTIVE",
    "PARTIALLY_EFFECTIVE",
    "EXPIRED",
    "UNKNOWN",
}
_VALID_REVIEW_STATUSES = {"PENDING", "ACCEPTED", "REJECTED", "DROPPED"}
_VALID_DOCUMENT_TYPES = {"LAW", "DECREE", "CIRCULAR", "RESOLUTION", "DECISION", "OTHER"}


class ExtractedDocumentMetadata(BaseModel):
    """Metadata read from IR elements; every field is optional (best effort).

    ``document_number`` / ``document_type`` / ``issued_date`` / ``issuer`` map
    directly to ``LegalDocument`` fields (doc 03 §3.9.3); ``effective_from`` /
    ``effective_to`` feed the Temporal Resolver (doc 03 §3.15).  ``None`` means
    the IR did not yield a confident value.
    """

    model_config = ConfigDict(extra="forbid")

    document_title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issuer: str | None = None
    issued_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None


def _element_text(element: DocumentElement) -> str:
    return element.text.strip()


def _first_page_text(document: ParsedDocument) -> str:
    """Join all first-page element texts in reading order."""
    first_page = document.pages[0]
    ordered = sorted(first_page.elements, key=lambda element: element.reading_order)
    return "\n".join(text for text in (_element_text(element) for element in ordered) if text)


def _title_text(document: ParsedDocument) -> str | None:
    """First explicit ``title`` element text; fall back to the first heading.

    Parser label mapping (docling ``title`` -> IR ``title``) is lossy for
    scan/OCR routes (doc 03 §3.7), so the first ``heading`` element is an
    acceptable fallback for ``LegalDocument.document_title``.
    """

    def _reading_key(element: DocumentElement) -> tuple[int, int]:
        return element.page_number, element.reading_order

    elements = [element for page in document.pages for element in page.elements]
    for element in sorted(elements, key=_reading_key):
        if element.element_type == "title":
            text = _element_text(element)
            if text:
                return text
    for element in sorted(elements, key=_reading_key):
        if element.element_type in {"heading", "heading1"}:
            text = _element_text(element)
            if text:
                return text
    return None


def _full_text(document: ParsedDocument) -> str:
    """Join every element text in reading order across all pages."""
    elements = [element for page in document.pages for element in page.elements]
    ordered = sorted(elements, key=lambda element: (element.page_number, element.reading_order))
    return "\n".join(text for text in (_element_text(element) for element in ordered) if text)


def _match_document_type(text: str) -> str | None:
    """Match a known type prefix at the start of any first-page line.

    Header/issuer lines (``CHÍNH PHỦ``, ``CỘNG HÒA ...``) precede the title in
    reading order, so the prefix is searched per line, not only at the very
    start of the joined text.
    """

    for line in text.splitlines():
        upper = line.strip().upper()
        for prefix, document_type in _DOCUMENT_TYPE_PREFIXES:
            if upper.startswith(prefix):
                return document_type
    return None


def _match_issuer(text: str) -> str | None:
    lowered = text.casefold()
    for keyword, issuer in _ISSUER_KEYWORDS:
        if keyword in lowered:
            return issuer
    return None


def _match_issued_date(text: str) -> date | None:
    # Vietnamese form: "ngày 26 tháng 12 năm 2024" -> (day, month, year).
    match = _ISSUED_DATE_RE.search(text)
    if match is not None:
        day, month, year = (int(group) for group in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    # ISO form: "2024-12-26" -> (year, month, day).
    match = _ISO_DATE_RE.search(text)
    if match is not None:
        year, month, day = (int(group) for group in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _parse_date_value(value: str) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` (possibly date-time) manifest value."""
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _match_effective_from(text: str) -> date | None:
    match = _EFFECTIVE_FROM_RE.search(text)
    if match is None:
        return None
    groups = match.groups()
    if groups[0] is not None:
        # Vietnamese form: (day, month, year).
        day, month, year = (int(group) for group in groups[:3])
    else:
        # Slash form: (day, month, year).
        day, month, year = (int(group) for group in groups[3:])
    try:
        return date(year, month, day)
    except ValueError:
        return None


def extract_document_metadata(document: ParsedDocument) -> ExtractedDocumentMetadata:
    """Extract LegalDocument metadata fields from one canonical IR document.

    Document number and type are read from the title element (first title /
    heading on page 1); issuer, issued date and effective start are searched
    across the full text.  Every value is deterministic: same IR in, same
    metadata out.
    """

    if not document.pages:
        return ExtractedDocumentMetadata()

    first_page_text = _first_page_text(document)
    full_text = _full_text(document)

    document_number = _DOCUMENT_NUMBER_RE.search(first_page_text)
    document_type = _match_document_type(first_page_text)
    issuer = _match_issuer(first_page_text)

    return ExtractedDocumentMetadata(
        document_title=_title_text(document),
        document_number=document_number.group(1) if document_number else None,
        document_type=document_type,
        issuer=issuer,
        issued_date=_match_issued_date(first_page_text),
        effective_from=_match_effective_from(full_text),
        effective_to=None,
    )


def validate_against_manifest(
    extracted: ExtractedDocumentMetadata, manifest: dict[str, object]
) -> list[str]:
    """Cross-check extracted metadata against the authoritative manifest.

    Returns a list of issues (empty = consistent).  Any mismatch means the
    auto-accept policy (doc 03 §3.7.5) does not apply and the document must be
    routed to review.  ``status`` / ``review_status`` enums are validated
    against the documented values (doc 03 §3.9.1).
    """

    issues: list[str] = []

    manifest_number = manifest.get("document_number")
    if (
        extracted.document_number is not None
        and manifest_number is not None
        and extracted.document_number != manifest_number
    ):
        issues.append(
            f"document_number mismatch: IR {extracted.document_number!r} "
            f"!= manifest {manifest_number!r}"
        )

    manifest_type = manifest.get("document_type")
    if (
        extracted.document_type is not None
        and manifest_type is not None
        and extracted.document_type != manifest_type
    ):
        issues.append(
            f"document_type mismatch: IR {extracted.document_type!r} != manifest {manifest_type!r}"
        )

    manifest_issued = manifest.get("issued_date")
    if extracted.issued_date is not None and isinstance(manifest_issued, str):
        try:
            manifest_issued_date = date.fromisoformat(manifest_issued[:10])
        except ValueError:
            manifest_issued_date = None
        if manifest_issued_date is not None and extracted.issued_date != manifest_issued_date:
            issues.append(
                f"issued_date mismatch: IR {extracted.issued_date.isoformat()} "
                f"!= manifest {manifest_issued_date.isoformat()}"
            )

    manifest_issuer = manifest.get("issuer")
    if (
        extracted.issuer is not None
        and isinstance(manifest_issuer, str)
        and extracted.issuer != manifest_issuer
    ):
        issues.append(f"issuer mismatch: IR {extracted.issuer!r} != manifest {manifest_issuer!r}")

    manifest_effective_from = manifest.get("effective_from")
    if extracted.effective_from is not None and isinstance(manifest_effective_from, str):
        manifest_effective = _parse_date_value(manifest_effective_from)
        if manifest_effective is not None and extracted.effective_from != manifest_effective:
            issues.append(
                f"effective_from mismatch: IR {extracted.effective_from.isoformat()} "
                f"!= manifest {manifest_effective.isoformat()}"
            )

    manifest_effective_to = manifest.get("effective_to")
    if extracted.effective_to is not None and isinstance(manifest_effective_to, str):
        manifest_effective = _parse_date_value(manifest_effective_to)
        if manifest_effective is not None and extracted.effective_to != manifest_effective:
            issues.append(
                f"effective_to mismatch: IR {extracted.effective_to.isoformat()} "
                f"!= manifest {manifest_effective.isoformat()}"
            )

    status = manifest.get("status")
    if status is not None and status not in _VALID_STATUSES:
        issues.append(f"manifest status {status!r} is not a valid DocumentStatus")

    review_status = manifest.get("review_status")
    if review_status is not None and review_status not in _VALID_REVIEW_STATUSES:
        issues.append(f"manifest review_status {review_status!r} is not a valid ReviewStatus")

    document_type = manifest.get("document_type")
    if document_type is not None and document_type not in _VALID_DOCUMENT_TYPES:
        issues.append(f"manifest document_type {document_type!r} is not a valid DocumentType")

    return issues


__all__ = [
    "ExtractedDocumentMetadata",
    "extract_document_metadata",
    "validate_against_manifest",
]
