"""Dramatiq worker bootstrap for durable ingestion relays."""

from __future__ import annotations

from app.ingestion.actors import bootstrap_outbox_relay


def main() -> None:
    """Seed the outbox relay before handing control to Dramatiq."""
    bootstrap_outbox_relay()


if __name__ == "__main__":
    main()
