"""Bounded query variants for retrieval."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.ingestion.terminology import TERMINOLOGY, TERMINOLOGY_VERSION, concept_variants

from .query_understanding import QueryPlan
from .query_understanding_types import EvidenceType


class RewriteProvider(Protocol):
    def __call__(self, query: str, evidence_type: EvidenceType | None = None) -> str | None: ...


class QueryVariant(BaseModel):
    """One retrieval query; HyDE variants are dense-channel-only."""

    model_config = ConfigDict(extra="forbid", strict=True)

    text: str = Field(min_length=1)
    source: Literal["original", "normalized", "rewrite", "ocr"]
    evidence_type: EvidenceType | None = None

    @property
    def dense_only(self) -> bool:
        return self.source == "hyde"


_STATUTORY_REWRITES: tuple[tuple[str, str], ...] = (
    ("vượt đèn đỏ", "không chấp hành hiệu lệnh của đèn tín hiệu giao thông"),
    ("dùng điện thoại", "sử dụng thiết bị điện thoại khi điều khiển phương tiện"),
    ("không đội mũ bảo hiểm", "không đội mũ bảo hiểm theo quy định"),
)


def normalize_query(text: str) -> str:
    """Normalize Unicode, punctuation, and known legal terminology."""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"[^\w\sÀ-ỹĐđ]", " ", normalized, flags=re.UNICODE)
    for canonical, variants in sorted(TERMINOLOGY.items(), key=lambda pair: -len(pair[0])):
        for variant in sorted(variants, key=len, reverse=True):
            normalized = re.sub(
                rf"(?<!\w){re.escape(variant)}(?!\w)",
                canonical,
                normalized,
                flags=re.IGNORECASE,
            )
    return " ".join(normalized.split())


def fold_ocr(text: str) -> str:
    """Fold accents and Vietnamese đ for OCR text while retaining word boundaries."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return re.sub(r"[^\w\s]", " ", folded.replace("đ", "d"), flags=re.UNICODE)


def _fold_query(text: str) -> str:
    return fold_ocr(text)


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(_fold_query(term))}(?!\w)", _fold_query(text)))


def ocr_query_variants(text: str, *, max_variants: int = 4) -> list[str]:
    """Return bounded folded/phrase-repaired forms for OCR-corrupted payloads."""
    normalized = " ".join(re.sub(r"[^\w\sÀ-ỹĐđ]", " ", text).split())
    folded = " ".join(fold_ocr(normalized).split())
    variants: list[str] = []
    for candidate in (
        folded,
        normalized.replace("lenh cua", "lenhcua"),
        normalized.replace("lenhcua", "lenh cua"),
    ):
        if candidate and candidate not in variants:
            variants.append(candidate)
        if len(variants) >= max_variants:
            break
    return variants


class QueryExpander:
    """Produce a finite, non-recursive set of retrieval variants."""

    def __init__(
        self,
        rewrite_provider: RewriteProvider | None = None,
        hyde_provider: Callable[[str, EvidenceType], str | None] | None = None,
        *,
        max_rewrites: int = 3,
        max_repair_attempts: int = 3,
        terminology_version: str = TERMINOLOGY_VERSION,
    ) -> None:
        if max_rewrites < 0 or max_repair_attempts < 0:
            raise ValueError("variant and repair bounds must be non-negative")
        if terminology_version != TERMINOLOGY_VERSION:
            raise ValueError(f"unsupported terminology version {terminology_version!r}")
        self._rewrite_provider = rewrite_provider
        self._hyde_provider = hyde_provider
        self._max_rewrites = max_rewrites
        self._max_repair_attempts = max_repair_attempts

    def expand(
        self,
        plan: QueryPlan,
        *,
        repair_attempts: int = 0,
        evidence_gaps: Sequence[EvidenceType] = (),
        existing_variants: Sequence[QueryVariant] = (),
    ) -> list[QueryVariant]:
        original = (plan.original_query or plan.normalized_query).strip() or "query"
        variants = [QueryVariant(text=original, source="original")]
        normalized = normalize_query(plan.normalized_query)
        if normalized != original:
            canonical_statutory = {statutory for _, statutory in _STATUTORY_REWRITES}
            if not any(statutory in normalized for statutory in canonical_statutory):
                variants.append(QueryVariant(text=normalized, source="normalized"))
        for candidate in ocr_query_variants(normalized):
            if candidate not in {variant.text for variant in variants}:
                variants.append(QueryVariant(text=candidate, source="ocr"))
        rewrite_count = 0
        for colloquial, statutory in _STATUTORY_REWRITES:
            colloquial = colloquial.rstrip("?!.,;:")
            if rewrite_count >= self._max_rewrites:
                break
            trigger = original if _contains_term(original, colloquial) else normalized
            if not _contains_term(trigger, colloquial):
                continue
            candidate = re.sub(
                rf"(?<!\w){re.escape(colloquial)}(?!\w)", statutory, normalized, flags=re.I
            )
            candidate = " ".join(candidate.split())
            if candidate and candidate not in {variant.text for variant in variants}:
                variants.append(QueryVariant(text=candidate, source="rewrite"))
                rewrite_count += 1
        if self._rewrite_provider and self._max_rewrites:
            rewrite_output = self._rewrite_provider(normalized)
            for text in rewrite_output or ():
                if not isinstance(text, str):
                    continue
                candidate = " ".join(text.split())
                if candidate and candidate not in {variant.text for variant in variants}:
                    variants.append(QueryVariant(text=candidate, source="rewrite"))
                if sum(variant.source == "rewrite" for variant in variants) >= self._max_rewrites:
                    break
        attempted = {
            variant.evidence_type
            for variant in existing_variants
            if variant.source == "hyde" and variant.evidence_type is not None
        }
        existing_text = {variant.text for variant in existing_variants if variant.source == "hyde"}
        if self._hyde_provider and repair_attempts < self._max_repair_attempts and evidence_gaps:
            for gap in dict.fromkeys(evidence_gaps):
                if gap in attempted:
                    continue
                hyde_text = self._hyde_provider(normalized, gap)
                if not isinstance(hyde_text, str):
                    continue
                candidate = " ".join(hyde_text.split())
                if candidate and candidate not in existing_text:
                    variants.append(QueryVariant(text=candidate, source="hyde", evidence_type=gap))
                    existing_text.add(candidate)
                attempted.add(gap)
        return variants


__all__ = ["QueryExpander", "QueryVariant", "fold_ocr", "normalize_query", "ocr_query_variants"]
