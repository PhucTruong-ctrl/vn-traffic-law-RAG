from app.verification.l4_numeric import L4NumericVerifier, normalize_number
from app.verification.l5_claim import L5ClaimVerifier


def test_l4_normalizes_vietnamese_number_formats():
    assert normalize_number("1.234.567 đồng") == "1234567"
    assert normalize_number("1.234.567,50 VNĐ") == "1234567.50"
    result = L4NumericVerifier().verify(
        {"claims": [{"numbers": ["1.234.567 đồng"]}]},
        [{"text": "Mức phạt là 1.234.567 đồng."}],
    )
    assert result.passed


def test_l4_rejects_ungrounded_number():
    result = L4NumericVerifier().verify(
        {"claims": [{"numbers": ["42"]}]},
        [{"text": "Mức phạt là 41 đồng."}],
    )
    assert not result.passed
    assert result.issues[0].code == "L4_NUMERIC_MISMATCH"


def test_l5_accepts_deterministically_supported_claim_without_judge():
    result = L5ClaimVerifier(judge=None, judge_enabled=False).verify(
        {"claims": [{"claim": "Mức phạt tiền", "provision_ids": ["p1"]}]},
        [{"provision_id": "p1", "text": "Mức phạt tiền áp dụng."}],
    )
    assert result.passed
    assert result.checked_provision_ids == ["0"]


def test_l5_fails_closed_when_judge_rejects_or_is_unavailable():
    draft = {"claims": [{"claim": "xe cơ giới bị tạm giữ", "provision_ids": ["p1"]}]}
    context = [
        {"provision_id": "p1", "text": "người điều khiển phải xuất trình giấy phép."}
    ]
    rejected = L5ClaimVerifier(judge=lambda *_: False).verify(draft, context)
    assert not rejected.passed
    assert rejected.issues[0].code == "L5_CLAIM_NOT_SUPPORTED"
    unavailable = L5ClaimVerifier(judge=lambda *_: (_ for _ in ()).throw(RuntimeError())).verify(draft, context)
    assert not unavailable.passed
    assert unavailable.issues[0].code == "L5_JUDGE_UNAVAILABLE"


def test_l5_rejects_claim_without_citation():
    result = L5ClaimVerifier(judge_enabled=False).verify(
        {"claims": [{"claim": "Có hiệu lực"}]}
    )
    assert not result.passed
    assert result.issues[0].code == "L5_CLAIM_WITHOUT_CITATION"
