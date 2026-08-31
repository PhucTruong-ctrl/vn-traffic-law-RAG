"""Bounded query variants for retrieval."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ingestion.terminology import TERMINOLOGY, TERMINOLOGY_VERSION

from .query_understanding import QueryPlan
from .query_understanding_types import EvidenceType


class QueryVariant(BaseModel):
    """One retrieval query; HyDE variants are dense-channel-only."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    source: Literal["original", "normalized", "rewrite", "hyde"]

    @property
    def dense_only(self) -> bool:
        return self.source == "hyde"


RewriteProvider = Callable[[str], Iterable[str]]


def normalize_query(text: str) -> str:
    """Normalize Unicode and known legal terminology without stripping accents."""
    normalized = unicodedata.normalize("NFKC", text)
    for canonical, variants in sorted(TERMINOLOGY.items(), key=lambda pair: -len(pair[0])):
        for variant in sorted(variants, key=len, reverse=True):
            normalized = re.sub(
                rf"(?<!\w){re.escape(variant)}(?!\w)",
                canonical,
                normalized,
                flags=re.IGNORECASE,
            )
    return " ".join(normalized.split())


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
        """Return original, normalized, bounded rewrites, then bounded HyDE.

        Providers only receive the original/normalized query.  Rewrite output is
        never fed back into the provider, preventing recursive expansion.
        """
        original = plan.normalized_query.strip() or "query"
        variants = [QueryVariant(text=original, source="original")]
        normalized = normalize_query(original)
        if normalized != original:
            variants.append(QueryVariant(text=normalized, source="normalized"))

        if self._rewrite_provider and self._max_rewrites:
            for text in self._rewrite_provider(normalized):
                candidate = " ".join(str(text).split())
                if candidate and candidate not in {variant.text for variant in variants}:
                    variants.append(QueryVariant(text=candidate, source="rewrite"))
                if sum(variant.source == "rewrite" for variant in variants) >= self._max_rewrites:
                    break

        attempted = {variant.text for variant in existing_variants if variant.source == "hyde"}
        if (
            self._hyde_provider
            and repair_attempts < self._max_repair_attempts
            and evidence_gaps
        ):
            for gap in dict.fromkeys(evidence_gaps):
                provider = self._hyde_provider
                if not callable(provider):
                    text = provider.generate(normalized, gap)
                else:
                    text = provider(normalized, gap)
                candidate = " ".join(str(text or "").split())
                if candidate and candidate not in attempted:
                    variants.append(QueryVariant(text=candidate, source="hyde"))
                    attempted.add(candidate)
        return variants


__all__ = ["QueryExpander", "QueryVariant", "normalize_query"]
