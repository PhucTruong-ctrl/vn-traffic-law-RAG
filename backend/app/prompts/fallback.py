"""Safe prompt fallback contract."""
from __future__ import annotations

from pathlib import Path

from app.observability.langfuse_client import FallbackPrompt, build_prompt


def load_fallback(name: str, directory: str | Path) -> FallbackPrompt:
    """Load a named, hash-verified release fallback prompt."""
    path = Path(directory) / (name if name.endswith(".yaml") else f"{name}.yaml")
    return build_prompt(name.removesuffix(".yaml"), path)
