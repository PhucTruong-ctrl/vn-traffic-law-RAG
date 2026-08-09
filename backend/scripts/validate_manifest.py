"""CLI validator for corpus document manifests.

Usage (from backend/):

    uv run python -m scripts.validate_manifest ../templates/corpus-manifest.example.json

Validates a manifest JSON file against templates/corpus-manifest.schema.json
(JSON Schema draft-07) plus the cross-field rule ``effective_to > effective_from``,
which draft-07 cannot express natively. Prints PASS/FAIL and exits non-zero on failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

import jsonschema

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "templates" / "corpus-manifest.schema.json"
)


def _build_format_checker() -> jsonschema.FormatChecker:
    """FormatChecker with stdlib-based checkers.

    jsonschema 4.26 only registers a handful of checkers out of the box
    ("date", "time", "email", ...); "date-time" and "uri" require optional
    third-party validators that are not part of the backend dev deps and are
    otherwise silently ignored. Register stdlib equivalents here.
    """
    checker = jsonschema.FormatChecker()

    @checker.checks("date-time", raises=(ValueError,))
    def is_date_time(value: object) -> bool:
        if not isinstance(value, str):
            return True
        # Python 3.11 fromisoformat accepts ISO 8601 date-times, the "Z"
        # suffix, and date-only strings (date-only is allowed for these fields).
        datetime.fromisoformat(value)
        return True

    @checker.checks("uri", raises=(ValueError,))
    def is_uri(value: object) -> bool:
        if not isinstance(value, str):
            return True
        parsed = urllib.parse.urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"{value!r} is not an absolute URI")
        return True

    return checker


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_manifest(manifest: dict) -> list[str]:
    """Return a list of validation errors (empty list means the manifest is valid)."""
    errors: list[str] = []
    schema = load_schema()
    validator = jsonschema.Draft7Validator(schema, format_checker=_build_format_checker())
    for error in sorted(validator.iter_errors(manifest), key=lambda e: list(e.path)):
        errors.append(error.message)

    # Cross-field rule (docs/06 6.2.1.1): effective_to must be strictly after
    # effective_from. JSON Schema draft-07 cannot compare two dates, so the
    # ordering is enforced here after schema validation.
    effective_from = manifest.get("effective_from")
    effective_to = manifest.get("effective_to")
    if isinstance(effective_from, str) and isinstance(effective_to, str):
        try:
            from_date = datetime.fromisoformat(effective_from).date()
            to_date = datetime.fromisoformat(effective_to).date()
        except ValueError:
            pass  # malformed dates are already reported by schema validation
        else:
            if to_date <= from_date:
                errors.append("'effective_to' must be strictly after 'effective_from'")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a corpus document manifest against the schema."
    )
    parser.add_argument("manifest", type=Path, help="Path to the manifest JSON file")
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read or parse manifest: {exc}")
        return 1

    errors = validate_manifest(manifest)
    if errors:
        print("FAIL: manifest is invalid")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("PASS: manifest is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
