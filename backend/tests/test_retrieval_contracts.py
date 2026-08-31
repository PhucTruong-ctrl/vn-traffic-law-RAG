from datetime import date

import pytest
from pydantic import ValidationError

from app.config import RetrievalSettings, get_retrieval_settings
from app.retrieval.contracts import CandidateSet, result_from_payload


@pytest.fixture
def payload() -> dict[str, object]:
    return {
        "provision_id": "nd-168-2024__dieu-7__diem-d",
        "provision_version": 1,
        "document_version_id": "version-1",
        "document_id": "nd-168-2024",
        "document_number": "168/2024/NĐ-CP",
        "article": "7",
        "clause": None,
        "point": "đ",
        "text": "Nội dung tìm kiếm",
        "source_text": "Nội dung gốc",
        "parent_context": None,
        "effective_from": "2025-01-01",
        "effective_to": None,
        "page_number": 4,
        "review_status": "ACCEPTED",
    }


def test_payload_maps_to_strict_result(payload: dict[str, object]) -> None:
    result = result_from_payload(payload, rank=2, score=0.75, source="dense")
    assert result.rank == 2
    assert result.fused_score == 0.75
    assert result.retrieval_sources == ["dense"]
    assert result.effective_from == date(2025, 1, 1)
    assert result.point == "đ"


def test_payload_rejects_non_accepted(payload: dict[str, object]) -> None:
    payload["review_status"] = "PENDING"
    with pytest.raises(ValueError, match="ACCEPTED"):
        result_from_payload(payload, rank=1, score=None, source="sparse")


def test_payload_rejects_missing_citation_metadata(payload: dict[str, object]) -> None:
    del payload["document_version_id"]
    with pytest.raises(ValidationError):
        result_from_payload(payload, rank=1, score=None, source="exact")


def test_candidate_set_rejects_extra_fields(payload: dict[str, object]) -> None:
    result = result_from_payload(payload, rank=1, score=None, source="exact")
    with pytest.raises(ValidationError):
        CandidateSet(query="q", results=[result], applied_date=None, extra="nope")


def test_retrieval_settings_defaults_and_singleton() -> None:
    settings = RetrievalSettings(_env_file=None)
    assert settings.exact_lookup_enabled is True
    assert settings.dense_prefetch == 30
    assert settings.sparse_prefetch == 30
    assert settings.rrf_k == 60
    assert settings.dense_weight == settings.sparse_weight == 1.0
    assert settings.fusion_limit == 20
    assert settings.final_top_k == 8
    assert settings.temporal_filter_enabled is True
    get_retrieval_settings.cache_clear()
    assert get_retrieval_settings() is get_retrieval_settings()
