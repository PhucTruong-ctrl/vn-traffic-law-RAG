from __future__ import annotations

from app.security import admin_token_is_valid, safe_upload_name


def test_admin_token_comparison_requires_strong_token_and_matches() -> None:
    expected = "a" * 32
    assert admin_token_is_valid({"x-admin-token": expected}, expected)
    assert not admin_token_is_valid({"x-admin-token": "b" * 32}, expected)
    assert not admin_token_is_valid({"x-admin-token": "short"}, expected)


def test_upload_name_rejects_traversal_and_non_pdf() -> None:
    assert safe_upload_name("document.PDF")
    assert not safe_upload_name("../document.pdf")
    assert not safe_upload_name("dir/document.pdf")
    assert not safe_upload_name("document.pdf.exe")
