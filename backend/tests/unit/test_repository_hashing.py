"""Unit tests: repository content-hash helpers (VNLRAG-39)."""

from app.persistence.repositories import content_hash, manifest_hash


def test_content_hash_is_deterministic_sha256() -> None:
    # Canonical sha256 over the UTF-8 bytes, precomputed with hashlib.
    expected = "sha256:fe8d4c5b3fb9dc296a0f2ed583b14cfa4a39b6a695e74005855b096349dce73f"
    assert content_hash("Điều 7. Nội dung điều luật.") == expected
    assert content_hash("Điều 7. Nội dung điều luật.") == expected


def test_content_hash_differs_for_different_content() -> None:
    assert content_hash("a") != content_hash("b")


def test_manifest_hash_is_key_order_independent() -> None:
    first = manifest_hash({"a": 1, "b": {"c": [1, 2]}})
    second = manifest_hash({"b": {"c": [1, 2]}, "a": 1})
    assert first == second
    assert first != manifest_hash({"a": 1, "b": {"c": [1, 3]}})
