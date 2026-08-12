"""Integration tests for the repository layer (VNLRAG-39).

Exercises CRUD round-trips, the temporal validity query and the relation
queries for context expansion against a real PostgreSQL server, using the
migrated session scratch database (conftest.py). Each test runs in a
transaction that is always rolled back, so the scratch database stays empty
between tests; all constraint enforcement happens at flush time.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.persistence.models import (
    DocumentRelation,
    DocumentVersion,
    LegalDocument,
    LegalProvision,
    ProvisionReference,
    ProvisionVersion,
)
from app.persistence.repositories import (
    DocumentRepository,
    ProvisionRepository,
    RelationRepository,
    TemporalRepository,
    content_hash,
)

try:  # pytest inserts the test dir on sys.path in non-package mode
    from conftest import clean_transaction
except ImportError:  # package mode: tests/__init__.py makes it importable
    from tests.integration.conftest import clean_transaction

pytestmark = pytest.mark.integration

D = date(2025, 6, 1)


@pytest.fixture()
def session(upgraded_engine: Engine) -> Iterator[Session]:
    """A session on the migrated scratch database; always rolled back."""
    with clean_transaction(upgraded_engine) as conn, Session(bind=conn) as session:
        yield session


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _seed_document(session: Session) -> LegalDocument:
    document = LegalDocument(
        document_id=_unique("doc"),
        document_number=_unique("168/2024"),
        document_title="Nghị định 168/2024/NĐ-CP",
        document_type="DECREE",
        file_hash=uuid.uuid4().hex,
        status="EFFECTIVE",
    )
    session.add(document)
    session.flush()
    return document


def _seed_version(
    session: Session,
    document_id: str,
    *,
    version: int = 1,
    review_status: str = "ACCEPTED",
    effective_from: date | None = None,
    effective_to: date | None = None,
) -> DocumentVersion:
    row = DocumentVersion(
        document_id=document_id,
        version=version,
        manifest_json={"manifest": "x"},
        content_hash=uuid.uuid4().hex,
        review_status=review_status,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    session.add(row)
    session.flush()
    return row


def _seed_provision(
    session: Session,
    document_version_id: str,
    *,
    provision_id: str | None = None,
    version: int = 1,
    review_status: str = "ACCEPTED",
    effective_from: date | None = None,
    effective_to: date | None = None,
) -> LegalProvision:
    row = LegalProvision(
        provision_id=provision_id or _unique("nd-168-2024__dieu"),
        document_version_id=document_version_id,
        node_kind="ARTICLE",
        article="7",
        source_text="Điều 7. Nội dung điều luật.",
        retrieval_text="Nội dung điều luật.",
        status="EFFECTIVE",
        page_number=1,
        source_element_ids=["e1"],
        content_hash=uuid.uuid4().hex,
        version=version,
        review_status=review_status,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    session.add(row)
    session.flush()
    return row


def _seed_reference(
    session: Session,
    source: LegalProvision,
    target: LegalProvision,
    *,
    relation_type: str = "REFERS_TO",
    review_status: str = "ACCEPTED",
    resolution_status: str = "RESOLVED",
) -> ProvisionReference:
    reference = ProvisionReference(
        source_legal_provision_id=source.id,
        target_legal_provision_id=target.id,
        source_provision_id=source.provision_id,
        target_provision_id=target.provision_id,
        relation_type=relation_type,
        extraction_method="TEXT_PATTERN",
        source_text="ref",
        review_status=review_status,
        resolution_status=resolution_status,
    )
    session.add(reference)
    session.flush()
    return reference


def _seed_unresolved_reference(session: Session, source: LegalProvision) -> ProvisionReference:
    """UNRESOLVED reference: target must be NULL (DB CHECK)."""
    reference = ProvisionReference(
        source_legal_provision_id=source.id,
        target_legal_provision_id=None,
        source_provision_id=source.provision_id,
        relation_type="REFERS_TO",
        extraction_method="TEXT_PATTERN",
        source_text=_unique("unresolved"),
        review_status="ACCEPTED",
        resolution_status="UNRESOLVED",
    )
    session.add(reference)
    session.flush()
    return reference


# ---------------------------------------------------------------------------
# CRUD round-trips
# ---------------------------------------------------------------------------


def test_document_crud_round_trip(session: Session) -> None:
    repo = DocumentRepository(session)
    document = LegalDocument(
        document_id="nd-168-2024",
        document_number="168/2024/NĐ-CP",
        document_title="Nghị định 168/2024/NĐ-CP",
        document_type="DECREE",
        file_hash="sha256:abcd",
        status="EFFECTIVE",
    )

    created = repo.create_document(document)
    assert created.id is not None

    fetched = repo.get_document("nd-168-2024")
    assert fetched is not None
    assert fetched.document_title == "Nghị định 168/2024/NĐ-CP"
    assert fetched.status == "EFFECTIVE"

    updated = repo.update_document("nd-168-2024", status="EXPIRED")
    assert updated is not None
    assert updated.status == "EXPIRED"
    assert repo.get_document("nd-168-2024") is not None

    assert repo.delete_document("nd-168-2024") is True
    assert repo.get_document("nd-168-2024") is None
    assert repo.delete_document("nd-168-2024") is False


def test_document_version_crud_round_trip(session: Session) -> None:
    document = _seed_document(session)
    repo = DocumentRepository(session)

    v1 = repo.create_version(
        DocumentVersion(
            document_id=document.document_id,
            version=1,
            manifest_json={"source_url": "https://example.gov.vn/x"},
            content_hash=content_hash("v1"),
            review_status="PENDING",
        )
    )
    assert v1.id is not None
    repo.create_version(
        DocumentVersion(
            document_id=document.document_id,
            version=2,
            manifest_json={"source_url": "https://example.gov.vn/x"},
            content_hash=content_hash("v2"),
            review_status="PENDING",
        )
    )

    fetched = repo.get_version(document.document_id, 1)
    assert fetched is not None
    assert fetched.content_hash == content_hash("v1")

    assert [v.version for v in repo.list_versions(document.document_id)] == [1, 2]
    latest = repo.latest_version(document.document_id)
    assert latest is not None and latest.version == 2

    assert repo.delete_version(document.document_id, 1) is True
    assert repo.get_version(document.document_id, 1) is None
    assert repo.get_version(document.document_id, 2) is not None
    assert repo.delete_version(document.document_id, 99) is False


def test_provision_crud_round_trip(session: Session) -> None:
    document = _seed_document(session)
    version = _seed_version(session, document.document_id, effective_from=date(2025, 1, 1))
    repo = ProvisionRepository(session)
    provision = LegalProvision(
        provision_id="nd-168-2024__dieu-7",
        document_version_id=version.id,
        article="7",
        source_text="Điều 7. Nội dung.",
        retrieval_text="Nội dung.",
        status="EFFECTIVE",
        page_number=2,
        source_element_ids=["e1"],
        content_hash=content_hash("p1"),
        version=1,
        review_status="PENDING",
    )

    created = repo.create_provision(provision)
    assert created.id is not None

    fetched = repo.get_provision("nd-168-2024__dieu-7", 1)
    assert fetched is not None
    assert fetched.article == "7"
    assert fetched.review_status == "PENDING"

    updated = repo.update_provision(
        "nd-168-2024__dieu-7",
        1,
        retrieval_text="Nội dung mới.",
        review_status="ACCEPTED",
        effective_from=date(2025, 1, 1),
    )
    assert updated is not None
    assert updated.review_status == "ACCEPTED"
    assert updated.retrieval_text == "Nội dung mới."

    assert repo.delete_provision("nd-168-2024__dieu-7", 1) is True
    assert repo.get_provision("nd-168-2024__dieu-7", 1) is None
    assert repo.delete_provision("nd-168-2024__dieu-7", 1) is False


def test_provision_version_registry_and_next_version(session: Session) -> None:
    document = _seed_document(session)
    version = _seed_version(session, document.document_id, effective_from=date(2025, 1, 1))
    repo = ProvisionRepository(session)
    provision_id = "nd-168-2024__dieu-7"

    _seed_provision(
        session,
        version.id,
        provision_id=provision_id,
        version=1,
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 6, 2),
    )
    assert repo.next_version(provision_id) == 2

    repo.register_version(
        ProvisionVersion(
            provision_id=provision_id,
            version=1,
            document_version_id=version.id,
        )
    )
    registry_v1 = repo.get_registry_entry(provision_id, 1)
    assert registry_v1 is not None
    assert registry_v1.superseded_by_version is None

    _seed_provision(
        session,
        version.id,
        provision_id=provision_id,
        version=2,
        effective_from=date(2025, 6, 2),
        effective_to=None,
    )
    assert repo.next_version(provision_id) == 3

    repo.register_version(
        ProvisionVersion(
            provision_id=provision_id,
            version=2,
            document_version_id=version.id,
            superseded_by_version=3,
        )
    )
    registry = repo.list_registry(provision_id)
    assert [(entry.version, entry.superseded_by_version) for entry in registry] == [
        (1, None),
        (2, 3),
    ]
    assert [p.version for p in repo.list_provision_versions(provision_id)] == [1, 2]


# ---------------------------------------------------------------------------
# Temporal validity query
# ---------------------------------------------------------------------------


def test_temporal_validity_query_on_fixtures(session: Session) -> None:
    document = _seed_document(session)
    version = _seed_version(session, document.document_id, effective_from=date(2024, 1, 1))
    # A: valid throughout.
    _seed_provision(
        session,
        version.id,
        provision_id="p-a",
        effective_from=date(2024, 1, 1),
        effective_to=date(2025, 12, 31),
    )
    # B: expires exactly at d -> invalid (exclusive upper bound).
    _seed_provision(
        session,
        version.id,
        provision_id="p-b",
        effective_from=date(2025, 1, 1),
        effective_to=D,
    )
    # C: starts exactly at d -> valid.
    _seed_provision(
        session,
        version.id,
        provision_id="p-c",
        effective_from=D,
        effective_to=None,
    )
    # D: not ACCEPTED -> invalid despite valid interval.
    _seed_provision(
        session,
        version.id,
        provision_id="p-d",
        review_status="PENDING",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    # E: starts after d -> invalid.
    _seed_provision(
        session,
        version.id,
        provision_id="p-e",
        effective_from=date(2025, 7, 1),
        effective_to=None,
    )

    valid = TemporalRepository(session).valid_provisions(D)
    assert {p.provision_id for p in valid} == {"p-a", "p-c"}


def test_temporal_query_filters_by_ids_document_and_limit(session: Session) -> None:
    document_a = _seed_document(session)
    version_a = _seed_version(session, document_a.document_id, effective_from=date(2024, 1, 1))
    _seed_provision(
        session,
        version_a.id,
        provision_id="p-a",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    _seed_provision(
        session,
        version_a.id,
        provision_id="p-b",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    document_b = _seed_document(session)
    version_b = _seed_version(session, document_b.document_id, effective_from=date(2024, 1, 1))
    _seed_provision(
        session,
        version_b.id,
        provision_id="p-c",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )

    repo = TemporalRepository(session)
    assert {p.provision_id for p in repo.valid_provisions(D, provision_ids=["p-a"])} == {"p-a"}
    assert {
        p.provision_id for p in repo.valid_provisions(D, document_id=document_a.document_id)
    } == {"p-a", "p-b"}
    assert [p.provision_id for p in repo.valid_provisions(D, limit=1)] == ["p-a"]


def test_temporal_document_versions_query(session: Session) -> None:
    document = _seed_document(session)
    # v1 expires exactly at d -> invalid.
    _seed_version(
        session,
        document.document_id,
        version=1,
        effective_from=date(2025, 1, 1),
        effective_to=D,
    )
    # v2 starts exactly at d -> valid.
    _seed_version(
        session,
        document.document_id,
        version=2,
        effective_from=D,
        effective_to=None,
    )
    # v3 not ACCEPTED -> invalid.
    _seed_version(
        session,
        document.document_id,
        version=3,
        review_status="PENDING",
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )

    versions = TemporalRepository(session).valid_document_versions(
        D, document_id=document.document_id
    )
    assert [v.version for v in versions] == [2]


# ---------------------------------------------------------------------------
# Relation queries (temporal + review filter)
# ---------------------------------------------------------------------------


def test_relation_query_filters_by_review_status_and_interval(
    session: Session,
) -> None:
    document = _seed_document(session)
    version = _seed_version(session, document.document_id, effective_from=date(2024, 1, 1))
    seed = _seed_provision(
        session,
        version.id,
        provision_id="p-seed",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    valid_target = _seed_provision(
        session,
        version.id,
        provision_id="p-valid",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    future_target = _seed_provision(
        session,
        version.id,
        provision_id="p-future",
        effective_from=date(2025, 7, 1),
        effective_to=None,
    )
    pending_target = _seed_provision(
        session,
        version.id,
        provision_id="p-pending",
        review_status="PENDING",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    # Expires exactly at d -> invalid at d (exclusive upper bound).
    expired_target = _seed_provision(
        session,
        version.id,
        provision_id="p-expired",
        effective_from=date(2024, 1, 1),
        effective_to=D,
    )

    _seed_reference(session, seed, valid_target)  # expected
    _seed_reference(session, seed, future_target)  # target interval excludes
    _seed_reference(session, seed, expired_target)  # target interval excludes
    _seed_reference(session, seed, pending_target)  # target review excludes
    _seed_reference(  # relation review excludes
        session,
        seed,
        valid_target,
        relation_type="SIBLING_OF",
        review_status="PENDING",
    )
    _seed_reference(  # relation resolution PENDING_REVIEW excludes
        session,
        seed,
        valid_target,
        relation_type="PARENT_OF",
        resolution_status="PENDING_REVIEW",
    )
    _seed_unresolved_reference(session, seed)  # resolution UNRESOLVED excludes

    related = RelationRepository(session).related_provisions(D, [seed])
    assert {r.provision.provision_id for r in related} == {"p-valid"}
    assert all(r.source_id == "p-seed" for r in related)
    assert all(r.depth == 1 for r in related)
    assert related[0].added_by == "CROSS_REFERENCE"
    assert related[0].as_metadata() == {
        "provision_id": "p-valid",
        "added_by": "CROSS_REFERENCE",
        "source_id": "p-seed",
        "depth": 1,
    }


def test_relation_query_filters_by_relation_type(session: Session) -> None:
    document = _seed_document(session)
    version = _seed_version(session, document.document_id, effective_from=date(2024, 1, 1))
    seed = _seed_provision(
        session,
        version.id,
        provision_id="p-seed",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    target_a = _seed_provision(
        session,
        version.id,
        provision_id="p-t1",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    target_b = _seed_provision(
        session,
        version.id,
        provision_id="p-t2",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    _seed_reference(session, seed, target_a, relation_type="REFERS_TO")
    _seed_reference(session, seed, target_b, relation_type="PENALTY_COMPANION")

    repo = RelationRepository(session)
    refs = repo.related_provisions(D, [seed], relation_types=["REFERS_TO"])
    assert {r.provision.provision_id for r in refs} == {"p-t1"}

    refs_all = repo.related_provisions(D, [seed])
    assert {r.provision.provision_id for r in refs_all} == {"p-t1", "p-t2"}
    assert {r.added_by for r in refs_all} == {"CROSS_REFERENCE", "PENALTY_COMPANION"}


def test_relation_query_pins_source_version(session: Session) -> None:
    """Expansion follows only the seed's exact version row.

    A reference owned by another version of the same provision_id must not
    leak into the expansion (doc 03 §3.20.2: relations are pinned to the
    source version in use). ACCEPTED versions of one provision_id cannot
    overlap, so the non-seed version is a PENDING row.
    """
    document = _seed_document(session)
    version = _seed_version(session, document.document_id, effective_from=date(2024, 1, 1))
    seed_v2 = _seed_provision(
        session,
        version.id,
        provision_id="p-seed",
        version=2,
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    seed_v1 = _seed_provision(
        session,
        version.id,
        provision_id="p-seed",
        version=1,
        review_status="PENDING",
        effective_from=None,
        effective_to=None,
    )
    v1_target = _seed_provision(
        session,
        version.id,
        provision_id="p-v1-target",
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    _seed_reference(session, seed_v1, v1_target)

    related = RelationRepository(session).related_provisions(D, [seed_v2])
    assert related == []


def test_document_relations_filter_by_review_status_and_interval(
    session: Session,
) -> None:
    source = _seed_document(session)
    _seed_version(session, source.document_id, effective_from=date(2024, 1, 1))

    target_valid = _seed_document(session)
    _seed_version(session, target_valid.document_id, effective_from=date(2024, 1, 1))
    target_future_relation = _seed_document(session)
    _seed_version(
        session,
        target_future_relation.document_id,
        effective_from=date(2024, 1, 1),
    )
    target_pending_version = _seed_document(session)
    _seed_version(
        session,
        target_pending_version.document_id,
        review_status="PENDING",
        effective_from=date(2024, 1, 1),
    )
    target_valid_for_pending_relation = _seed_document(session)
    _seed_version(
        session,
        target_valid_for_pending_relation.document_id,
        effective_from=date(2024, 1, 1),
    )

    session.add_all(
        [
            # Expected: ACCEPTED relation, effective_from <= d, target valid.
            DocumentRelation(
                source_document_id=source.document_id,
                target_document_id=target_valid.document_id,
                relation_type="SUPERSEDES",
                source="MANIFEST",
                effective_from=date(2025, 1, 1),
                review_status="ACCEPTED",
            ),
            # Relation interval excludes: effective_from after d.
            DocumentRelation(
                source_document_id=source.document_id,
                target_document_id=target_future_relation.document_id,
                relation_type="SUPERSEDES",
                source="MANIFEST",
                effective_from=date(2025, 7, 1),
                review_status="ACCEPTED",
            ),
            # Target review excludes: no ACCEPTED version valid at d.
            DocumentRelation(
                source_document_id=source.document_id,
                target_document_id=target_pending_version.document_id,
                relation_type="GUIDES",
                source="MANIFEST",
                review_status="ACCEPTED",
            ),
            # Relation review excludes.
            DocumentRelation(
                source_document_id=source.document_id,
                target_document_id=target_valid_for_pending_relation.document_id,
                relation_type="GUIDES",
                source="MANIFEST",
                review_status="PENDING",
            ),
            # Relation resolution PENDING_REVIEW excludes.
            DocumentRelation(
                source_document_id=source.document_id,
                target_document_id=target_valid.document_id,
                relation_type="CORRECTS",
                source="MANIFEST",
                review_status="ACCEPTED",
                resolution_status="PENDING_REVIEW",
            ),
        ]
    )
    session.flush()

    related = RelationRepository(session).related_documents(D, source.document_id)
    assert [r.target_document_id for r in related] == [target_valid.document_id]
    assert related[0].relation_type == "SUPERSEDES"
