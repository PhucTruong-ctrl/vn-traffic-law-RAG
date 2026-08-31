from datetime import date
from types import SimpleNamespace

from app.retrieval.context_expansion import LegalContextExpander
from app.retrieval.contracts import RetrievalResult

D = date(2025, 1, 1)


def result(provision_id: str, rank: int) -> RetrievalResult:
    return RetrievalResult(
        rank=rank,
        provision_id=provision_id,
        provision_version=1,
        document_id="doc-1",
        document_version_id="version-1",
        text="seed text",
        source_text="seed text",
        parent_context=None,
        document_number="168/2024/NĐ-CP",
        article="7",
        clause=None,
        point=None,
        effective_from=D,
        effective_to=None,
        page_number=1,
        retrieval_sources=["dense"],
        fused_score=1.0,
        added_by=None,
        source_id=None,
        depth=0,
    )


def row(provision_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        provision_id=provision_id,
        version=1,
        document_version_id="version-1",
        retrieval_text=f"text {provision_id}",
        source_text=f"source {provision_id}",
        parent_context=None,
        article="7",
        clause=None,
        point="đ",
        effective_from=D,
        effective_to=None,
        page_number=1,
        document_version=SimpleNamespace(
            document=SimpleNamespace(document_id="doc-1", document_number="168/2024/NĐ-CP")
        ),
    )


class Temporal:
    def __init__(self, rows):
        self.rows = {item.provision_id: item for item in rows}

    def valid_provisions(self, _date, *, provision_ids=None, document_id=None):
        if document_id is not None:
            return list(self.rows.values())
        return [self.rows[item] for item in provision_ids or () if item in self.rows]


class Relations:
    def __init__(self, edges):
        self.edges = edges
        self.calls = []

    def related_provisions(self, _date, seeds, *, relation_types=None):
        self.calls.append([seed.provision_id for seed in seeds])
        return [self.edges[seed.provision_id] for seed in seeds if seed.provision_id in self.edges]


def relation(target, source="seed", relation_type="REFERS_TO"):
    return SimpleNamespace(
        provision=target,
        relation_type=relation_type,
        source_id=source,
        added_by="CROSS_REFERENCE",
    )


def test_expands_top_three_with_metadata_and_depth_bound():
    seed = row("seed")
    child = row("child")
    grandchild = row("grandchild")
    relations = Relations({"seed": relation(child), "child": relation(grandchild, "child")})
    expander = LegalContextExpander(relations, Temporal([seed, child, grandchild]))

    expanded = expander.expand([result("seed", 1), result("late", 4)], query_date=D)

    assert [item.provision_id for item in expanded] == ["child", "grandchild"]
    assert expanded[0].added_by == "CROSS_REFERENCE"
    assert expanded[0].source_id == "seed"
    assert expanded[0].depth == 1
    assert expanded[1].depth == 2


def test_excludes_duplicate_unresolved_and_limits_breadth():
    seed = row("seed")
    target = row("target")
    edges = {"seed": relation(target)}
    relations = Relations(edges)
    expander = LegalContextExpander(relations, Temporal([seed]))

    assert expander.expand([result("seed", 1)], query_date=D) == []
    assert relations.calls == [["seed"]]


def test_missing_relation_dependency_fails_explicitly() -> None:
    class MissingRelations:
        pass

    expander = LegalContextExpander(MissingRelations(), Temporal([row("seed")]))
    try:
        expander.expand([result("seed", 1)], query_date=D)
    except RuntimeError as error:
        assert "related_provisions" in str(error)
    else:
        raise AssertionError("missing relation method must fail explicitly")


def test_missing_temporal_dependency_fails_explicitly() -> None:
    class MissingTemporal:
        pass

    expander = LegalContextExpander(Relations({}), MissingTemporal())
    try:
        expander.expand([result("seed", 1)], query_date=D)
    except RuntimeError as error:
        assert "valid_provisions" in str(error)
    else:
        raise AssertionError("missing temporal method must fail explicitly")


def test_stale_seed_is_excluded_before_relation_lookup() -> None:
    class StrictRelations:
        def related_provisions(self, _date, seeds, *, relation_types=None):
            assert all(hasattr(seed, "document_version") for seed in seeds)
            return []

    expander = LegalContextExpander(StrictRelations(), Temporal([row("live")]))

    assert expander.expand([result("stale-index-id", 1)], query_date=D) == []
