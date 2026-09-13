from __future__ import annotations

from app.rag.api import _frontend_response


def test_complete_response_forwards_service_claims_unchanged() -> None:
    claims = [
        {"claim": "Claim one", "provision_ids": ["chunk-1", "chunk-2"]},
        {"claim": "Claim two", "provision_ids": ["chunk-3"]},
    ]
    result = {
        "answer": "Answer",
        "citations": [{"source_id": "irrelevant", "excerpt": "Unrelated"}],
        "claims": claims,
        "status": "complete",
    }

    response = _frontend_response(result)

    assert response["status"] == "VERIFIED"
    assert response["claims"] is claims
    assert response["claims"] == claims
    assert response["citations"] == result["citations"]


def test_legacy_complete_derives_only_identity_backed_claims() -> None:
    result = {
        "answer": "Answer",
        "citations": [
            {"source_id": "chunk-1", "excerpt": "Supported"},
            {"excerpt": "No source identity"},
            {"source_id": "", "excerpt": "Empty source identity"},
        ],
        "status": "complete",
    }

    response = _frontend_response(result)

    assert response["claims"] == [{"claim": "Supported", "provision_ids": ["chunk-1"]}]


def test_out_of_scope_maps_to_distinct_status_and_preserves_reason() -> None:
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
