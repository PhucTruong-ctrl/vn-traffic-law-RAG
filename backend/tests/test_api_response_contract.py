from __future__ import annotations

from app.rag.api import _frontend_response


def test_verified_response_forwards_explicit_claims_unchanged() -> None:
    citation = {"source_id": "chunk-1", "excerpt": "Supported"}
    claims = [{"claim": citation["excerpt"], "provision_ids": [citation["source_id"]]}]
    result = {
        "answer": "Answer",
        "citations": [citation],
        "claims": claims,
        "status": "verified",
    }

    response = _frontend_response(result)

    assert response["status"] == "VERIFIED"
    assert response["claims"] is claims
    assert response["claims"] == claims
    assert response["citations"] == result["citations"]


def test_legacy_complete_is_not_upgraded_to_public_verified() -> None:
    result = {
        "answer": "Answer",
        "citations": [{"source_id": "chunk-1", "excerpt": "Supported"}],
        "status": "complete",
    }

    response = _frontend_response(result)

    assert response["status"] == "complete"
    assert response["status"] != "VERIFIED"
    assert "claims" not in response


def test_out_of_scope_maps_internal_reason_to_public_status() -> None:
    result = {
        "answer": "This is outside scope.",
        "citations": [],
        "reason_code": "out_of_scope",
        "status": "insufficient_evidence",
    }

    response = _frontend_response(result)

    assert response["status"] == "OUT_OF_SCOPE"
    assert response["claims"] == []
    assert response["abstention"] == {"reason_code": "out_of_scope"}


def test_explicit_out_of_scope_status_preserves_reason() -> None:
    result = {
        "answer": "This is outside scope.",
        "citations": [],
        "reason_code": "out_of_scope",
        "status": "out_of_scope",
    }

    response = _frontend_response(result)

    assert response["status"] == "OUT_OF_SCOPE"
    assert response["claims"] == []
    assert response["abstention"] == {"reason_code": "out_of_scope"}


def test_insufficient_evidence_preserves_reason() -> None:
    result = {
        "answer": "Insufficient evidence.",
        "citations": [],
        "reason_code": "reference_not_found",
        "status": "insufficient_evidence",
    }

    response = _frontend_response(result)

    assert response["status"] == "INSUFFICIENT_EVIDENCE"
    assert response["claims"] == []
    assert response["abstention"] == {"reason_code": "reference_not_found"}
