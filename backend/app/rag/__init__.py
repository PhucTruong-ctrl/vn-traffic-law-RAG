"""RAG chat contracts."""

from contextlib import suppress

with suppress(ModuleNotFoundError):
    from .schemas import ChatRequest, ChatResponse, Citation, RetrievedChunk

__all__ = ["Citation", "ChatRequest", "ChatResponse", "RetrievedChunk"]
