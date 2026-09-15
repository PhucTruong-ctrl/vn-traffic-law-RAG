from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document

from scripts.run_retrieval_ablation import (
    available_coordinates,
    expand_configs,
    hit_predicate,
    run_ablation,
    write_csv,
    write_json,
    write_markdown,
)


def _case(case_id: str = "c1", category: str = "rule") -> dict:
    return {
        "id": case_id,
        "category": category,
        "question": "q",
        "expected": {"provision_ids": ["law__dieu-1"]},
    }


def test_hit_predicate_is_ancestor_aware() -> None:
    assert hit_predicate(["law__dieu-1__khoan-2"], ["law__dieu-1"])
    assert hit_predicate(["law__dieu-1"], ["law__dieu-1__khoan-2"])
    assert not hit_predicate(["law__dieu-2"], ["law__dieu-1"])


def test_coverage_excludes_cases_without_gold_in_chunks(tmp_path: Path) -> None:
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text(
        json.dumps({"metadata": {"provision_id": "law__dieu-1"}}) + "\n", encoding="utf-8"
    )

    class Stub:
        def retrieve(self, query: str, **kwargs: object) -> list[Document]:
            return [Document("x", metadata={"provision_id": "law__dieu-1"})]

    cases = [
        _case("included"),
        {**_case("excluded"), "expected": {"provision_ids": ["other__dieu-1"]}},
    ]
    result = run_ablation(
        cases, [{"config": "sparse", "top_k": 5}], Stub(), available_coordinates(chunks)
    )
    assert result["excluded_case_ids"] == ["excluded"]
    assert result["included_case_count"] == 1


def test_config_sweep_expands_cartesian_product_deterministically() -> None:
    rows = expand_configs(("sparse", "dense"), expand_queries=(1, 2), rrf_k=(10, 60))
    assert len(rows) == 8
    assert [row["config"] for row in rows[:4]] == ["sparse"] * 4
    assert rows[0]["expand_queries"] == 1


def test_writers_emit_auditable_json_csv_markdown(tmp_path: Path) -> None:
    class Stub:
        def retrieve(self, query: str, **kwargs: object) -> list[Document]:
            return [Document("x", metadata={"provision_id": "law__dieu-1"})]

    result = run_ablation([_case()], [{"config": "sparse", "top_k": 5}], Stub(), {"law__dieu-1"})
    json_path, csv_path, md_path = (
        tmp_path / "run.json",
        tmp_path / "run.csv",
        tmp_path / "run.md",
    )
    write_json(json_path, result)
    write_csv(csv_path, result["rows"])
    write_markdown(md_path, result)
    assert json.loads(json_path.read_text(encoding="utf-8"))["configs"]
    assert "retrieved_coordinates" in csv_path.read_text(encoding="utf-8")
    markdown = md_path.read_text(encoding="utf-8")
    assert "| Config |" in markdown and "**1.0000**" in markdown
