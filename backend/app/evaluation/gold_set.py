"""Gold-set records and deterministic validation utilities."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GoldCategory(StrEnum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"
    COMPARISON = "COMPARISON"
    EXACT_REFERENCE = "EXACT_REFERENCE"
    PENALTY = "PENALTY"
    LICENSE_POINTS = "LICENSE_POINTS"
    CONDITION = "CONDITION"
    EXCEPTION = "EXCEPTION"
    PROCEDURE = "PROCEDURE"
    CROSS_REFERENCE = "CROSS_REFERENCE"
    MULTI_PROVISION = "MULTI_PROVISION"
    MULTI_DOCUMENT = "MULTI_DOCUMENT"
    COLLOQUIAL_QUERY = "COLLOQUIAL_QUERY"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    ADVERSARIAL_CITATION = "ADVERSARIAL_CITATION"


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"


class DatasetSplit(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION = "VALIDATION"
    FINAL_TEST = "FINAL_TEST"


class GoldRecord(BaseModel):
    """One reviewed question in the evaluation gold set."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    REQUIRED_FIELDS: ClassVar[tuple[str, ...]] = (
        "id",
        "question",
        "category",
        "query_date",
        "expected_provision_ids",
        "acceptable_provision_ids",
        "required_evidence",
        "must_include_facts",
        "must_not_include_facts",
        "temporal_metadata",
        "review_status",
        "reviewed_by",
        "gold_version",
        "hash",
    )

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    category: GoldCategory
    query_date: date | None
    expected_provision_ids: list[str]
    acceptable_provision_ids: list[str]
    required_evidence: list[str]
    must_include_facts: list[str]
    must_not_include_facts: list[str]
    temporal_metadata: dict[str, Any]
    review_status: ReviewStatus
    reviewed_by: str = Field(min_length=1)
    gold_version: str = Field(min_length=1)
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "expected_provision_ids",
        "acceptable_provision_ids",
        "required_evidence",
        "must_include_facts",
        "must_not_include_facts",
    )
    @classmethod
    def validate_string_lists(cls, value: list[str]) -> list[str]:
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("list entries must be non-empty strings")
        return value

    @model_validator(mode="after")
    def validate_cross_field_invariants(self) -> GoldRecord:
        expected = set(self.expected_provision_ids)
        acceptable = set(self.acceptable_provision_ids)
        if not expected <= acceptable:
            raise ValueError("expected_provision_ids must be a subset of acceptable_provision_ids")
        if not self.required_evidence and self.category is not GoldCategory.OUT_OF_SCOPE:
            raise ValueError("required_evidence must not be empty")
        if not set(self.required_evidence) <= acceptable:
            raise ValueError("required_evidence must reference acceptable provision ids")
        referenced_facts = {
            fact for fact in self.must_include_facts if fact in expected or fact.startswith("p-")
        }
        if not referenced_facts <= acceptable:
            raise ValueError("must_include_facts must reference acceptable provision ids")
        if self.category is GoldCategory.OUT_OF_SCOPE and (
            self.expected_provision_ids or self.acceptable_provision_ids or self.required_evidence
        ):
            raise ValueError("OUT_OF_SCOPE records cannot require corpus provisions")
        if "basis" not in self.temporal_metadata:
            raise ValueError("temporal_metadata must include basis")
        if self.query_date is not None and self.temporal_metadata.get("basis") == "query_date":
            self.temporal_metadata.setdefault("query_date", self.query_date.isoformat())
        return self

    @field_validator("temporal_metadata")
    @classmethod
    def validate_temporal_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("temporal_metadata must not be empty")
        return value

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude={"hash"})
        return payload

    def computed_hash(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def validate_hash(self) -> GoldRecord:
        expected = self.computed_hash()
        if self.hash != expected:
            raise ValueError(f"hash mismatch: expected {expected}, got {self.hash}")
        return self


def assign_split(record_id: str) -> DatasetSplit:
    """Assign a stable 40/40/120-style split (20/20/60 percent) from an id."""
    if not isinstance(record_id, str) or not record_id.strip():
        raise ValueError("record_id must be a non-empty string")
    bucket = int(hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:8], 16) % 10
    if bucket < 2:
        return DatasetSplit.DEVELOPMENT
    if bucket < 4:
        return DatasetSplit.VALIDATION
    return DatasetSplit.FINAL_TEST


def validate_record(payload: dict[str, Any], *, verify_hash: bool = True) -> GoldRecord:
    """Parse one record strictly and optionally verify its canonical hash."""
    record = GoldRecord.model_validate(payload)
    if verify_hash:
        record.validate_hash()
    return record


__all__ = [
    "DatasetSplit",
    "GoldCategory",
    "GoldRecord",
    "ReviewStatus",
    "assign_split",
    "validate_record",
]
