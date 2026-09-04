from types import SimpleNamespace
from app.verification.l2_citation import L2CitationVerifier

def record(pid="p1", **kw):
    values = {"provision_id": pid, "review_status": "ACCEPTED", "article": "1"}
    values.update(kw)
    return SimpleNamespace(**values)
def draft(*citations):
    return SimpleNamespace(claims=[SimpleNamespace(citations=list(citations))])
def test_l2_accepts_retrieved_accepted_provision():
    result = L2CitationVerifier([record()]).verify(draft("p1"), [record()])
    assert result.passed and result.checked_provision_ids == ["p1"]
def test_l2_rejects_unknown_and_unwhitelisted_ids():
    verifier = L2CitationVerifier([record()])
    assert verifier.verify(draft("fake"), [record()]).issues[0].code == "L2_UNKNOWN_PROVISION"
    assert verifier.verify(draft("p1"), []).issues[0].code == "L2_INVALID_CITATION"
def test_l2_rejects_unaccepted_and_mismatched_metadata():
    verifier = L2CitationVerifier([record(review_status="PENDING")])
    assert verifier.verify(draft("p1"), [record(review_status="PENDING")]).passed is False
    verifier = L2CitationVerifier([record()])
    assert verifier.verify(draft(SimpleNamespace(provision_id="p1", article="9")), [record()]).passed is False
