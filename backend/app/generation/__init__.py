"""Structured legal answer generation."""

from .context_builder import ContextBuilder, build_context
from .gemini import (
    GenerationConfigurationError,
    OpenRouterStructuredGenerator,
    StructuredGenerationError,
)
from .schemas import Claim, ClaimType, StructuredAnswer

__all__ = [
    "Claim",
    "ClaimType",
    "ContextBuilder",
    "OpenRouterStructuredGenerator",
    "StructuredAnswer",
    "StructuredGenerationError",
    "GenerationConfigurationError",
    "build_context",
]
