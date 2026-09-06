"""Structured legal answer generation."""

from .context_builder import ContextBuilder, build_context
from .gemini import (
    GeminiStructuredGenerator,
    GenerationConfigurationError,
    StructuredGenerationError,
)
from .schemas import Claim, ClaimType, StructuredAnswer

__all__ = [
    "Claim",
    "ClaimType",
    "ContextBuilder",
    "GeminiStructuredGenerator",
    "StructuredAnswer",
    "StructuredGenerationError",
    "GenerationConfigurationError",
    "build_context",
]
