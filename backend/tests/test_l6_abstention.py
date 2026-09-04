from datetime import date
from types import SimpleNamespace

from app.verification.abstention import AbstentionReason
from app.verification.l6_evidence import L6EvidenceVerifier

verifier = L6EvidenceVerifier()


def claim(text="claim", *provision_ids):
    return SimpleNamespace(claim=text, provision_ids=list(provision_ids))


def evidence(pid="p1", text="support", **dates):
    return SimpleNamespace(provision_id=pid, text=text, **dates)


def test_l6_requires_complete_evidence_for_every_claim():
    result = verifier.verify(
        [claim("first", "p1"), claim("second", "p2")],
        [evidence("p1")],
        query_date=date(2024, 1, 1),
    )

    assert result.passed is False
    assert result.reason is AbstentionReason.INSUFFICIENT_EVIDENCE
    assert result.missing == ["second"]


def test_l6_rejects_evidence_outside_query_date():
    result = verifier.verify(
        [claim("claim", "p1")],
        [evidence("p1", effective_from=date(2025, 1, 1))],
        query_date=date(2024, 1, 1),
    )

    assert result.passed is False
    assert result.reason is AbstentionReason.INSUFFICIENT_EVIDENCE


def test_l6_returns_standardized_abstention_reasons():
    cases = [
        (None, [], {}, AbstentionReason.VERIFICATION_FAILURE),
        ([], [], {"query_date": date(2024, 1, 1)}, AbstentionReason.MISSING_EVIDENCE),
        ([claim("claim", "p1")], [evidence("p1")], {}, AbstentionReason.MISSING_DATE),
        (
            [],
            [],
            {"query_date": date(2024, 1, 1), "in_scope": False},
            AbstentionReason.OUT_OF_SCOPE,
        ),
        (
            [],
            [],
            {"query_date": date(2024, 1, 1), "verification_ok": False},
            AbstentionReason.VERIFICATION_FAILURE,
        ),
    ]

    for claims, records, kwargs, expected in cases:
        result = verifier.verify(claims, records, **kwargs)
        assert result.passed is False
        assert result.reason is expected
        assert result.reason.value in {reason.value for reason in AbstentionReason}
