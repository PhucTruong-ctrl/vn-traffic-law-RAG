"""Structured legal answer generation."""

from .gemini import GeminiStructuredGenerator, StructuredGenerationError
from .schemas import Claim, ClaimType, StructuredAnswer

__all__ = ["Claim", "ClaimType", "GeminiStructuredGenerator", "StructuredAnswer", "StructuredGenerationError"]
