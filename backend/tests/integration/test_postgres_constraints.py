"""Integration tests for the temporal / review / reference constraints
(VNLRAG-38).

Exercises the exclusion constraint, the acceptance CHECKs and the
unresolved-reference normalization uniqueness against a real PostgreSQL
server, using the migrated session scratch database (conftest.py). Each test
runs in a transaction that is always rolled back, so the scratch database
stays empty between tests; statements expected to fail run inside savepoints.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

try:  # pytest inserts the test dir on sys.path in non-package mode
    from conftest import clean_transaction, sqlstate
except ImportError:  # package mode: tests/__init__.py makes it importable
    from tests.integration.conftest import clean_transaction, sqlstate

pytestmark = pytest.mark.integration

# PostgreSQL SQLSTATEs (psycopg errors).
SQLSTATE_EXCLUSION = "23P01"
SQLSTATE_UNIQUE = "23505"
SQLSTATE_CHECK = "23514"
SQLSTATE_FK = "23503"

REFERS_TO = "REFERS_TO"


def _seed_source(conn: Connection) -> str:
    """Insert a minimal legal_sources row; return its id."""
    return conn.execute(
        text(
            "INSERT INTO legal_sources (source_id, source_name, source_type) "
            "VALUES (:sid, :name, :stype) RETURNING id"
        ),
        {
            "sid": f"src-{uuid.uuid4().hex[:10]}",
            "name": "Test legal source",
            "stype": "OFFICIAL",
        },
    ).scalar_one()


def _seed_document(conn: Connection) -> str:
    """Insert legal_sources + legal_documents; return the document_id."""
    _seed_source(conn)
    document_id = f"doc-{uuid.uuid4().hex[:10]}"
    conn.execute(
        text(
            "INSERT INTO legal_documents "
            "(document_id, document_number, document_title, document_type, "
            " status, file_hash) "
            "VALUES (:did, :num, :title, :dtype, :status, :hash)"
        ),
        {
            "did": document_id,
            "num": f"168/2024/NĐ-CP-{uuid.uuid4().hex[:4]}",
            "title": "Test document",
            "dtype": "DECREE",
            "status": "PUBLISHED",
            "hash": uuid.uuid4().hex,
        },
    )
    return document_id


def _seed_document_version(
    conn: Connection,
    *,
    review_status: str = "PENDING",
    effective_from: date | None = None,
    effective_to: date | None = None,
) -> str:
    """Insert a minimal document_versions row; return its id (uuid)."""
    return conn.execute(
        text(
            "INSERT INTO document_versions "
            "(document_id, version, manifest_json, content_hash, "
            " effective_from, effective_to, review_status) "
            "VALUES (:did, 1, '{}'::jsonb, :hash, :ef, :et, :rs) RETURNING id"
        ),
        {
            "did": _seed_document(conn),
            "hash": uuid.uuid4().hex,
            "ef": effective_from,
            "et": effective_to,
            "rs": review_status,
        },
    ).scalar_one()


def _seed_provision(
    conn: Connection,
    *,
    document_version_id: str,
    provision_id: str | None = None,
    version: int = 1,
    node_kind: str = "ARTICLE",
    article: str | None = "1",
    source_text: str = "Điều 7. Nội dung điều luật.",
    review_status: str = "PENDING",
    effective_from: date | None = None,
    effective_to: date | None = None,
) -> str:
    """Insert a minimal legal_provisions row; return its id (uuid)."""
    return conn.execute(
        text(
            "INSERT INTO legal_provisions "
            "(provision_id, document_version_id, node_kind, article, "
            " source_text, retrieval_text, status, page_number, "
            " source_element_ids, content_hash, version, review_status, "
            " effective_from, effective_to) "
            "VALUES (:pid, :dvid, :nk, :article, :stext, :stext, 'published', "
            " 1, '[]'::jsonb, :hash, :ver, :rs, :ef, :et) RETURNING id"
        ),
        {
            "pid": provision_id or f"prov-{uuid.uuid4().hex[:10]}",
            "dvid": document_version_id,
            "nk": node_kind,
            "article": article,
            "stext": source_text,
            "hash": uuid.uuid4().hex,
            "ver": version,
            "rs": review_status,
            "ef": effective_from,
            "et": effective_to,
        },
    ).scalar_one()


def _insert_unresolved_reference(
    conn: Connection,
    *,
    source_provision_id: str,
    source_text: str,
    relation_type: str = REFERS_TO,
    resolution_status: str = "UNRESOLVED",
    target_provision_id: str | None = None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO provision_references "
            "(source_legal_provision_id, target_legal_provision_id, "
            " source_provision_id, target_provision_id, relation_type, "
            " extraction_method, source_text, resolution_status) "
            "VALUES (:spid, :tpid, :sp, :tp, :rt, 'regex', :stext, :rs)"
        ),
        {
            "spid": source_provision_id,
            "tpid": target_provision_id,
            "sp": f"sp-{uuid.uuid4().hex[:8]}",
            "tp": None,
            "rt": relation_type,
            "stext": source_text,
            "rs": resolution_status,
        },
    )


# ---------------------------------------------------------------------------
# Temporal exclusion constraint (doc 03 §3.10.4)
# ---------------------------------------------------------------------------


def test_exclusion_rejects_overlapping_accepted_versions(
    upgraded_engine: Engine,
) -> None:
    """Two ACCEPTED versions of one provision with overlapping [) intervals."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        provision_id = "prov-overlap"
        _seed_provision(
            conn,
            document_version_id=dv,
            provision_id=provision_id,
            version=1,
            review_status="ACCEPTED",
            effective_from=date(2024, 1, 1),
            effective_to=date(2024, 12, 31),
        )
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            _seed_provision(
                conn,
                document_version_id=dv,
                provision_id=provision_id,
                version=2,
                review_status="ACCEPTED",
                effective_from=date(2024, 6, 1),
                effective_to=date(2025, 6, 1),
            )
    assert sqlstate(exc.value) == SQLSTATE_EXCLUSION


def test_exclusion_allows_adjacent_accepted_intervals(
    upgraded_engine: Engine,
) -> None:
    """Half-open [from, to): a version may start exactly when the old ends."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        provision_id = "prov-adjacent"
        _seed_provision(
            conn,
            document_version_id=dv,
            provision_id=provision_id,
            version=1,
            review_status="ACCEPTED",
            effective_from=date(2024, 1, 1),
            effective_to=date(2024, 6, 30),
        )
        _seed_provision(
            conn,
            document_version_id=dv,
            provision_id=provision_id,
            version=2,
            review_status="ACCEPTED",
            effective_from=date(2024, 6, 30),
            effective_to=date(2024, 12, 31),
        )


def test_exclusion_allows_pending_overlap(upgraded_engine: Engine) -> None:
    """The predicate only guards ACCEPTED rows (doc 03 §3.10.4)."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        provision_id = "prov-pending"
        _seed_provision(
            conn,
            document_version_id=dv,
            provision_id=provision_id,
            version=1,
            review_status="PENDING",
            effective_from=date(2024, 1, 1),
            effective_to=date(2024, 12, 31),
        )
        _seed_provision(
            conn,
            document_version_id=dv,
            provision_id=provision_id,
            version=2,
            review_status="PENDING",
            effective_from=date(2024, 6, 1),
            effective_to=date(2025, 6, 1),
        )


def test_exclusion_allows_accepted_with_distinct_provision(
    upgraded_engine: Engine,
) -> None:
    """Overlap between different provisions is not restricted."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        _seed_provision(
            conn,
            document_version_id=dv,
            provision_id="prov-a",
            version=1,
            review_status="ACCEPTED",
            effective_from=date(2024, 1, 1),
            effective_to=date(2024, 12, 31),
        )
        _seed_provision(
            conn,
            document_version_id=dv,
            provision_id="prov-b",
            version=1,
            review_status="ACCEPTED",
            effective_from=date(2024, 6, 1),
            effective_to=date(2025, 6, 1),
        )


# ---------------------------------------------------------------------------
# Acceptance CHECKs (doc 03 §3.10.2/§3.10.4)
# ---------------------------------------------------------------------------


def test_interval_check_rejects_invalid_ranges(upgraded_engine: Engine) -> None:
    """effective_to <= effective_from is rejected; NULL upper bound is fine."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            _seed_provision(
                conn,
                document_version_id=dv,
                review_status="PENDING",
                effective_from=date(2024, 12, 31),
                effective_to=date(2024, 12, 31),
            )
        assert sqlstate(exc.value) == SQLSTATE_CHECK
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            _seed_provision(
                conn,
                document_version_id=dv,
                review_status="PENDING",
                effective_from=date(2024, 6, 1),
                effective_to=date(2024, 1, 1),
            )
        assert sqlstate(exc.value) == SQLSTATE_CHECK
        _seed_provision(
            conn,
            document_version_id=dv,
            review_status="PENDING",
            effective_from=date(2024, 1, 1),
            effective_to=None,
        )


def test_effective_from_required_for_accepted(upgraded_engine: Engine) -> None:
    """ACCEPTED rows must have effective_from; non-ACCEPTED rows may not."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            _seed_provision(
                conn,
                document_version_id=dv,
                review_status="ACCEPTED",
                effective_from=None,
                effective_to=None,
            )
        assert sqlstate(exc.value) == SQLSTATE_CHECK
        # PENDING row without an interval is allowed (unreviewed row)
        _seed_provision(
            conn,
            document_version_id=dv,
            review_status="PENDING",
            effective_from=None,
            effective_to=None,
        )


def test_review_status_check(upgraded_engine: Engine) -> None:
    """review_status only accepts the documented lifecycle values."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            _seed_provision(
                conn,
                document_version_id=dv,
                review_status="BOGUS",
            )
        assert sqlstate(exc.value) == SQLSTATE_CHECK
        for valid in ("PENDING", "ACCEPTED", "REJECTED", "DROPPED"):
            _seed_provision(
                conn,
                document_version_id=dv,
                review_status=valid,
                effective_from=date(2024, 1, 1),
                effective_to=date(2024, 12, 31),
            )


def test_article_required_check(upgraded_engine: Engine) -> None:
    """article is required for tree nodes, optional for the listed kinds."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            _seed_provision(
                conn,
                document_version_id=dv,
                node_kind="ARTICLE",
                article=None,
            )
        assert sqlstate(exc.value) == SQLSTATE_CHECK
        _seed_provision(
            conn,
            document_version_id=dv,
            node_kind="APPENDIX",
            article=None,
        )
        _seed_provision(
            conn,
            document_version_id=dv,
            node_kind="TRANSITIONAL",
            article=None,
        )


def test_document_versions_effective_from_required_for_accepted(
    upgraded_engine: Engine,
) -> None:
    """document_versions carries the same ACCEPTED-gated CHECK."""
    with clean_transaction(upgraded_engine) as conn:
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            _seed_document_version(
                conn,
                review_status="ACCEPTED",
                effective_from=None,
            )
        assert sqlstate(exc.value) == SQLSTATE_CHECK
        _seed_document_version(
            conn,
            review_status="ACCEPTED",
            effective_from=date(2024, 1, 1),
        )


# ---------------------------------------------------------------------------
# Uniqueness / FK integrity
# ---------------------------------------------------------------------------


def test_provision_version_unique(upgraded_engine: Engine) -> None:
    """UNIQUE (provision_id, version) on legal_provisions."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        _seed_provision(conn, document_version_id=dv, provision_id="prov-uq", version=3)
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            _seed_provision(
                conn,
                document_version_id=dv,
                provision_id="prov-uq",
                version=3,
            )
    assert sqlstate(exc.value) == SQLSTATE_UNIQUE


def test_unresolved_reference_normalized_uniqueness(upgraded_engine: Engine) -> None:
    """md5(normalize_ref_text(source_text)) makes equivalent texts collide."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        source = _seed_provision(conn, document_version_id=dv)
        _insert_unresolved_reference(
            conn,
            source_provision_id=source,
            source_text="Điều 7, Khoản 4 Nghị định 168/2024/NĐ-CP",
        )
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            _insert_unresolved_reference(
                conn,
                source_provision_id=source,
                source_text="  điều 7 ,  khoản 4 nghị định 168/2024/NĐ-CP ",
            )
    assert sqlstate(exc.value) == SQLSTATE_UNIQUE


def test_unresolved_reference_distinct_text_allowed(upgraded_engine: Engine) -> None:
    """Different normalized reference texts do not collide."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        source = _seed_provision(conn, document_version_id=dv)
        _insert_unresolved_reference(
            conn,
            source_provision_id=source,
            source_text="Điều 7, Khoản 4",
        )
        _insert_unresolved_reference(
            conn,
            source_provision_id=source,
            source_text="Điều 7, Khoản 5",
        )


def test_unresolved_reference_index_ignores_resolved_rows(
    upgraded_engine: Engine,
) -> None:
    """The partial unique index only guards UNRESOLVED rows with NULL target."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        source = _seed_provision(conn, document_version_id=dv)
        resolved_target = _seed_provision(conn, document_version_id=dv)
        pending_target = _seed_provision(conn, document_version_id=dv)
        _insert_unresolved_reference(
            conn,
            source_provision_id=source,
            source_text="Điều 7, Khoản 4",
        )
        _insert_unresolved_reference(
            conn,
            source_provision_id=source,
            target_provision_id=resolved_target,
            source_text="Điều 7, Khoản 4",
            resolution_status="RESOLVED",
        )
        _insert_unresolved_reference(
            conn,
            source_provision_id=source,
            target_provision_id=pending_target,
            source_text="Điều 7, Khoản 4",
            resolution_status="PENDING_REVIEW",
        )


def test_reference_resolution_status_requires_target(
    upgraded_engine: Engine,
) -> None:
    """RESOLVED and PENDING_REVIEW references must identify a target row."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        source = _seed_provision(conn, document_version_id=dv)
        for resolution_status in ("RESOLVED", "PENDING_REVIEW"):
            with pytest.raises(IntegrityError) as exc, conn.begin_nested():
                _insert_unresolved_reference(
                    conn,
                    source_provision_id=source,
                    source_text="Điều 7",
                    resolution_status=resolution_status,
                )
            assert sqlstate(exc.value) == SQLSTATE_CHECK


def test_resolved_reference_triple_unique(upgraded_engine: Engine) -> None:
    """UNIQUE (source, target, relation_type) for resolved references."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        source = _seed_provision(conn, document_version_id=dv)
        target = _seed_provision(conn, document_version_id=dv)
        _insert_unresolved_reference(
            conn,
            source_provision_id=source,
            target_provision_id=target,
            source_text="Điều 7",
            resolution_status="RESOLVED",
        )
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            _insert_unresolved_reference(
                conn,
                source_provision_id=source,
                target_provision_id=target,
                source_text="Điều 7",
                resolution_status="RESOLVED",
            )
    assert sqlstate(exc.value) == SQLSTATE_UNIQUE


def test_document_version_fk(upgraded_engine: Engine) -> None:
    """legal_provisions.document_version_id must reference an existing row."""
    with (
        clean_transaction(upgraded_engine) as conn,
        pytest.raises(IntegrityError) as exc,
        conn.begin_nested(),
    ):
        _seed_provision(
            conn,
            document_version_id=str(uuid.uuid4()),
        )
    assert sqlstate(exc.value) == SQLSTATE_FK


def test_provision_versions_registry_fk(upgraded_engine: Engine) -> None:
    """provision_versions (provision_id, version) must exist in legal_provisions."""
    with clean_transaction(upgraded_engine) as conn:
        dv = _seed_document_version(conn)
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO provision_versions "
                    "(provision_id, version, document_version_id) "
                    "VALUES ('prov-missing', 1, :dvid)"
                ),
                {"dvid": dv},
            )
    assert sqlstate(exc.value) == SQLSTATE_FK


def test_document_relations_unique(upgraded_engine: Engine) -> None:
    """UNIQUE (source_document_id, target_document_id, relation_type)."""
    with clean_transaction(upgraded_engine) as conn:
        row: dict[str, Any] = {
            "source_document_id": "doc-src",
            "target_document_id": "doc-tgt",
            "relation_type": "AMENDS",
            "source": "test",
        }
        conn.execute(
            text(
                "INSERT INTO document_relations "
                "(source_document_id, target_document_id, relation_type, source) "
                "VALUES (:source_document_id, :target_document_id, :relation_type, :source)"
            ),
            row,
        )
        with pytest.raises(IntegrityError) as exc, conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO document_relations "
                    "(source_document_id, target_document_id, relation_type, source) "
                    "VALUES (:source_document_id, :target_document_id, :relation_type, :source)"
                ),
                row,
            )
    assert sqlstate(exc.value) == SQLSTATE_UNIQUE
