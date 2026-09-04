"""Claim-level structured legal answer schema."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ClaimType(StrEnum):
    VIOLATION_DEFINITION = "VIOLATION_DEFINITION"
    MONETARY_PENALTY = "MONETARY_PENALTY"
    LICENSE_POINTS = "LICENSE_POINTS"
    LICENSE_SUSPENSION = "LICENSE_SUSPENSION"
    EXCEPTION = "EXCEPTION"
    PROCEDURE = "PROCEDURE"
    LEGAL_CONDITION = "LEGAL_CONDITION"
    OTHER = "OTHER"


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    claim_type: ClaimType
    provision_ids: list[str] = Field(min_length=1)
    numbers: list[str] = Field(default_factory=list)

    @field_validator("provision_ids")
    @classmethod
    def no_empty_ids(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("provision_ids must not contain empty strings")
        return value


class StructuredAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_summary: str
    claims: list[Claim] = Field(min_length=1)
    missing_information: list[str] = Field(default_factory=list)
    should_abstain: bool = False

    @model_validator(mode="after")
    def answer_rules(self) -> "StructuredAnswer":
        if not self.should_abstain:
            if not self.answer_summary.strip():
                raise ValueError("answer_summary must be non-empty when should_abstain=false")
            if not self.claims:
                raise ValueError("claims must be non-empty when should_abstain=false")
        return self


__all__ = ["Claim", "ClaimType", "StructuredAnswer"]
