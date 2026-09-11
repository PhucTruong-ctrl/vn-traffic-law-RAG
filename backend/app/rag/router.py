"""Deterministic route classification for legal assistant requests."""

from __future__ import annotations

from .analyzer import classify_intent

ROUTES = {"legal", "chitchat", "web", "out_of_scope"}


def route_question(question: str) -> str:
    """Return one of the four supported routes without fetching or calling tools."""
    return classify_intent(question)


__all__ = ["ROUTES", "route_question"]
