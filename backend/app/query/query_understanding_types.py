"""Shared enums for deterministic query understanding."""

from enum import StrEnum


class QueryIntent(StrEnum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"
    COMPARISON = "COMPARISON"
    SOURCE_SEARCH = "SOURCE_SEARCH"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class EvidenceType(StrEnum):
    VIOLATION_DEFINITION = "violation_definition"
    MONETARY_PENALTY = "monetary_penalty"
    LICENSE_POINTS = "license_points"
    LICENSE_SUSPENSION = "license_suspension"
    EXCEPTION = "exception"
    PROCEDURE = "procedure"
    LEGAL_CONDITION = "legal_condition"
