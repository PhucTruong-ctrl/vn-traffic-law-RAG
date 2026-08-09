import json
from pathlib import Path

import jsonschema
from jsonschema import Draft7Validator, FormatChecker
from jsonschema.validators import extend

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "templates" / "legal-document.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _effective_interval(validator, _keyword, instance, _schema):
    """Custom keyword `x-effective-interval`: effective_to > effective_from (docs/03:2488).

    JSON Schema draft-07 cannot compare two sibling properties, so the ordering
    rule is enforced via a custom keyword; the DB layer adds the same CHECK.
    """
    if not validator.is_type(instance, "object"):
        return
    effective_from = instance.get("effective_from")
    effective_to = instance.get("effective_to")
    if (
        isinstance(effective_from, str)
        and isinstance(effective_to, str)
        and effective_to <= effective_from
    ):
        yield jsonschema.ValidationError(
            f"effective_to ({effective_to}) must be greater than effective_from ({effective_from})"
        )


VALIDATOR = extend(Draft7Validator, {"x-effective-interval": _effective_interval})


def _validate(instance: dict) -> list[jsonschema.ValidationError]:
    return list(VALIDATOR(SCHEMA, format_checker=FormatChecker()).iter_errors(instance))


def _messages(errors: list[jsonschema.ValidationError]) -> list[str]:
    """Flatten top-level messages plus the nested context of `oneOf` failures."""
    flattened = []
    for error in errors:
        flattened.append(error.message)
        flattened.extend(context.message for context in error.context)
    return flattened


def make_document(**overrides: object) -> dict:
    doc = {
        "document_id": "law-2024-01",
        "document_number": "01/2024/QH15",
        "document_title": "Luật ban hành văn bản quy phạm pháp luật",
        "document_type": "LAW",
        "issuer": "Quốc hội",
        "issued_date": "2024-01-15",
        "source_url": "https://example.com/law-2024-01",
        "file_hash": "a" * 64,
        "status": "EFFECTIVE",
        "version": 1,
        "created_at": "2024-01-20T00:00:00Z",
        "updated_at": "2024-01-20T00:00:00Z",
    }
    doc.update(overrides)
    return doc


def make_version(**overrides: object) -> dict:
    version = {
        "id": "ver-law-2024-01-1",
        "document_id": "law-2024-01",
        "version": 1,
        "manifest_json": {"parser": "docling", "parser_version": "2.118.1"},
        "content_hash": "b" * 64,
        "effective_from": "2024-01-20",
        "effective_to": None,
        "review_status": "ACCEPTED",
        "created_at": "2024-01-20T00:00:00Z",
    }
    version.update(overrides)
    return version


def test_valid_legal_document_passes() -> None:
    assert _validate(make_document()) == []


def test_valid_document_version_passes() -> None:
    assert _validate(make_version()) == []


def test_missing_status_enum_value_fails() -> None:
    errors = _validate(make_document(status="ACTIVE"))
    assert errors
    assert any("ACTIVE" in message for message in _messages(errors))


def test_version_without_effective_interval_keys_fails() -> None:
    instance = make_version()
    del instance["effective_from"]
    del instance["effective_to"]
    errors = _validate(instance)
    assert errors
    messages = _messages(errors)
    assert any("effective_from" in message and "required" in message for message in messages)
    assert any("effective_to" in message and "required" in message for message in messages)


def test_extra_field_fails() -> None:
    errors = _validate(make_document(extra_field="nope"))
    assert errors
    assert any("Additional properties are not allowed" in message for message in _messages(errors))


def test_invalid_interval_fails() -> None:
    errors = _validate(make_version(effective_from="2024-01-20", effective_to="2024-01-19"))
    assert errors
    assert any("greater than effective_from" in message for message in _messages(errors))


def test_malformed_single_sided_date_fails() -> None:
    """effective_from is a string that is not a valid date (effective_to null)."""
    errors = _validate(make_version(effective_from="not-a-date", effective_to=None))
    assert errors
    assert any("not-a-date" in message or "date" in message for message in _messages(errors))


def test_accepted_version_requires_non_null_effective_from() -> None:
    """review_status ACCEPTED requires a determinate effective_from (docs/03:2491-2500)."""
    errors = _validate(make_version(effective_from=None, review_status="ACCEPTED"))
    assert errors
    messages = _messages(errors)
    assert any("effective_from" in message for message in messages)


def test_accepted_version_requires_valid_effective_from_date() -> None:
    """ACCEPTED + malformed effective_from must fail, not just non-null."""
    errors = _validate(make_version(effective_from="2024/01/20", review_status="ACCEPTED"))
    assert errors
    assert any("effective_from" in message for message in _messages(errors))


def test_nullable_effective_dates_pass_when_not_accepted() -> None:
    """PENDING version may have both effective dates null (docs/03:1234)."""
    assert (
        _validate(make_version(effective_from=None, effective_to=None, review_status="PENDING"))
        == []
    )
