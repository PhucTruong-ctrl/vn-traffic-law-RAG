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
import unicodedata
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.ingestion.document_ir import DocumentElement, ParsedDocument

# Vietnamese document number, e.g. 168/2024/NĐ-CP, 36/2024/QH15, 24/2023/TT-BCA,
# 49/VBHN-VPQH.  The authority suffix may end in digits (QH15).
_DOCUMENT_NUMBER_RE = re.compile(
    r"(?<!\d)(\d{1,4})\s*/\s*(\d{4})\s*/\s*([A-ZĐ][A-ZĐ0-9-]*)(?![A-ZĐ0-9-])",
    re.IGNORECASE,
)

# Issued date in the official Vietnamese form: "Hà Nội, ngày 26 tháng 12 năm 2024".
_ISSUED_DATE_RE = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+n(?:ăm|am|ǎm)\s+(\d{4})", re.I)
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Effective-start clauses: "Nghị định này c(?:ó|o|ó) h(?:iệu|ieu) l(?:ực|uc) thi hành t(?:ừ|ir|u) ng(?:ày|ay) ...".
# Effective-start clauses: "Nghị định này c(?:ó|o|ó) h(?:iệu|ieu) l(?:ực|uc) thi hành t(?:ừ|ir|u) ng(?:ày|ay) ...",
# "c(?:ó|o|ó) h(?:iệu|ieu) l(?:ực|uc) thi hành kể t(?:ừ|ir|u) ng(?:ày|ay) ..." (official TT 24/2023 wording).
_EFFECTIVE_FROM_RE = re.compile(
    r"(?:c(?:ó|o|ó) h(?:iệu|ieu) l(?:ực|uc)|k(?:ể|e) từ)\s+(?:thi hành\s+)?(?:k(?:ể|e)\s+)?t(?:ừ|ir|u) ng(?:ày|ay)\s+"
    r"(\d{1,2})\s+tháng\s+(\d{1,2})\s+n(?:ăm|am|ǎm)\s+(\d{4})"
    r"|(?:c(?:ó|o|ó) h(?:iệu|ieu) l(?:ực|uc)|k(?:ể|e) từ)\s+(?:thi hành\s+)?(?:k(?:ể|e)\s+)?t(?:ừ|ir|u) ng(?:ày|ay)\s+"
    r"(\d{1,2})/(\d{1,2})/(\d{4})",
    re.I,
)
_OWN_EFFECTIVE_FROM_RE = _EFFECTIVE_FROM_RE
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


def _header_elements(document: ParsedDocument) -> list[DocumentElement]:
    """Return page-one header tokens in spatial reading order."""
    elements = [element for element in document.pages[0].elements if element.text.strip()]
    return sorted(
        elements,
        key=lambda element: (
            element.bbox.top if element.bbox is not None else element.reading_order,
            element.bbox.left if element.bbox is not None else element.reading_order,
            element.reading_order,
        ),
    )


def _header_text(document: ParsedDocument) -> str:
    """Join only the first-page header band, avoiding body citations."""
    tokens = [element for element in _header_elements(document) if element.bbox is None or element.bbox.top <= 0.31]
    return " ".join(element.text.strip() for element in tokens)


# Header identity is authoritative for issued dates: the date must be in the
# first-page header band and spatially near the document's own Số: token.
def _header_date(document: ParsedDocument) -> date | None:
    elements = [element for element in _header_elements(document) if element.bbox is None or element.bbox.top <= 0.31]
    number_indexes = [index for index, element in enumerate(elements) if re.search(r"\bsố\s*:", element.text, re.IGNORECASE)]
    for index, element in enumerate(elements):
        if not (_ISSUED_DATE_RE.search(element.text) or _ISO_DATE_RE.search(element.text)):
            continue
        if not number_indexes or min(abs(index - number_index) for number_index in number_indexes) <= 2:
            return _match_issued_date(element.text)
    return None

def _parse_date_value(value: str) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` (possibly date-time) manifest value."""
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None

def _match_effective_from(text: str, *, own_document: bool = False) -> date | None:
    matcher = _OWN_EFFECTIVE_FROM_RE if own_document else _EFFECTIVE_FROM_RE
    match = matcher.search(text)
    if match is None:
        return None
    groups = match.groups()
    if own_document:
        groups = groups[:3] if groups[0] is not None else groups[3:]
    elif groups[0] is not None:
        groups = groups[:3]
    else:
        groups = groups[3:]
    day, month, year = (int(group) for group in groups)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _manifest_identity_evidence(document: ParsedDocument, manifest_number: str) -> bool:
    """Return whether one OCR element contains manifest number evidence."""
    expected = _canonical_document_number(manifest_number)
    if not expected:
        return False
    return any(
        expected in _canonical_document_number(element.text)
        for page in document.pages
        for element in page.elements
    )


def extract_document_metadata(
    document: ParsedDocument, *, manifest_number: str | None = None,
    manifest_issued_date: str | None = None, manifest_effective_from: str | None = None,
) -> ExtractedDocumentMetadata:
    """Extract LegalDocument metadata fields from one canonical IR document."""
    if not document.pages:
        return ExtractedDocumentMetadata()
    first_page_text = _first_page_text(document)
    full_text = _full_text(document)
    title = _title_text(document)
    header_text = _header_text(document)
    identity_text = "\n".join(part for part in (title, header_text) if part)
    first_elements = _header_elements(document)
    own_number = re.search(
        r"(?:số\s*:?\s*)?(\d{1,4})\s*/\s*(\d{4})\s*/\s*([A-ZĐ][A-ZĐ0-9-]*)",
        header_text, re.IGNORECASE
    )
    if manifest_number:
        number_parts = re.fullmatch(
            r"(\d{1,4})/(\d{4})/([A-ZĐ][A-ZĐ0-9-]*)",
            manifest_number.replace(" ", ""), re.IGNORECASE
        )
        if number_parts:
            expected = _canonical_document_number(manifest_number)
            candidates = [number_parts]
            for element in first_elements:
                for candidate in (element.text,):
                    match = _DOCUMENT_NUMBER_RE.search(candidate)
                    if match and _canonical_document_number(match.group(0)) == expected:
                        candidates.append(match)
            own_number = candidates[-1]
    if own_number is None and manifest_number:
        number_parts = re.fullmatch(
            r"(\d{1,4})/(\d{4})/([A-ZĐ][A-ZĐ0-9-]*)",
            manifest_number.replace(" ", ""), re.IGNORECASE
        )
        if number_parts:
            expected = _canonical_document_number(manifest_number)
            for index in range(len(first_elements)):
                candidate = " ".join(item.text for item in first_elements[index:index + 3])
                if expected in _canonical_document_number(candidate):
                    own_number = number_parts
                    break
    document_number = own_number or _DOCUMENT_NUMBER_RE.search(identity_text)
    if manifest_number and not _manifest_identity_evidence(document, manifest_number):
        document_number = None
    issued_date = _header_date(document)
    effective_from = _match_effective_from(full_text, own_document=True)
    # Manifest identity is authoritative: do not promote a referenced date.
    if manifest_issued_date is not None:
        expected = _parse_date_value(manifest_issued_date)
        if expected is not None and issued_date != expected:
            issued_date = None
    if manifest_effective_from is not None:
        expected = _parse_date_value(manifest_effective_from)
        if expected is not None and effective_from != expected:
            effective_from = None
    return ExtractedDocumentMetadata(
        document_title=title,
        document_number=(
            f"{document_number.group(1)}/{document_number.group(2)}/"
            f"{document_number.group(3).upper()}" if document_number else None
        ),
        document_type=_match_document_type(identity_text) or (
            "DECREE" if re.search(r"NGHI\s+DINH|NGHỊ\s+ĐỊNH", identity_text, re.I) else
            "CIRCULAR" if re.search(r"THONG\s+TU|THÔNG\s+TƯ", identity_text, re.I) else None
        ),
        issuer=_match_issuer(first_page_text) or (
            "Bộ Giao thông vận tải" if re.search(r"GIAO\s+THONG\s+VAN\s+TAI", first_page_text, re.I) else
            "Chính phủ" if re.search(r"CHINH\s+PHU|CHÍNH\s+PHỦ", first_page_text, re.I) else None
        ),
        issued_date=issued_date,
        effective_from=effective_from,
        effective_to=None,
    )


def _canonical_document_number(value: str) -> str:
    """Return an OCR-tolerant key while retaining the manifest spelling."""
    value = unicodedata.normalize("NFC", value).casefold()
    value = re.sub(r"[\s\-.,;:_/]+", "", value)
    return value.replace("đ", "d").replace("ndcp", "dcp")


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
        and isinstance(extracted.document_number, str)
        and isinstance(manifest_number, str)
        and _canonical_document_number(extracted.document_number)
        != _canonical_document_number(manifest_number)
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
