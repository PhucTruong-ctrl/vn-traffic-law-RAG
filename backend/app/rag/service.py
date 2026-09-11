"""Retrieval and grounded answer orchestration."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

from langchain_core.documents import Document

from .analyzer import analyze_question, detect_vehicle_types, vehicle_label
from .evidence import assess_evidence
from .generator import generate_answer
from .retrieval import Retriever
from .router import route_question

logger = logging.getLogger(__name__)
_GENERIC_VEHICLE_CATEGORIES = ("ô tô", "xe mô tô, xe gắn máy", "xe thô sơ")


def _is_vehicle_penalty_question(question: str) -> bool:
    lowered = question.casefold()
    return bool(
        any(token in lowered for token in ("phạt", "xử phạt", "mức phạt", "tước", "trừ điểm"))
        and any(
            token in lowered
            for token in ("vượt đèn đỏ", "không đội mũ", "đi ngược chiều", "nồng độ cồn")
        )
    )


def _document_key(document: Document) -> tuple[str, ...]:
    """Stable identity shared with cross-reference expansion."""
    metadata = document.metadata or {}
    chunk_id = metadata.get("chunk_id")
    if chunk_id:
        return ("chunk_id", str(chunk_id))
    source = metadata.get("source_file") or metadata.get("source") or ""
    return ("source_content", str(source), document.page_content)


def _citation(document: Document) -> dict[str, Any]:
    metadata = document.metadata
    source_file = metadata.get("source_file") or metadata.get("source")
    return {
        "document": metadata.get("document_name")
        or metadata.get("document_number")
        or "Văn bản pháp luật",
        "article": metadata.get("article"),
        "clause": metadata.get("clause"),
        "point": metadata.get("point"),
        "page": metadata.get("page") or metadata.get("page_number") or 1,
        "source_file": source_file or "unknown",
        "excerpt": document.page_content,
        "pdf_url": metadata.get("pdf_url"),
    }


def _intent_groups(
    question: str,
    documents: list[Document],
    *,
    analysis: Any | None = None,
) -> tuple[dict[str, list[Document]], list[Document]]:
    analysis = analysis or analyze_question(question)
    intents = [intent for intent in analysis.intents if intent.kind == "legal"]
    if not intents:
        return {}, documents
    groups: dict[str, list[Document]] = {intent.text: [] for intent in intents}
    for document in documents:
        metadata = document.metadata or {}
        labels = metadata.get("intent") or metadata.get("intent_text")
        if isinstance(labels, str):
            labels = (labels,)
        if isinstance(labels, (list, tuple, set)):
            for label in labels:
                if isinstance(label, str) and label in groups:
                    groups[label].append(document)
    if not any(groups.values()) and len(intents) == 1:
        groups[intents[0].text] = documents
    return groups, documents


class RAGService:
    """Retrieval and grounded answer orchestration."""

    def __init__(self, retriever: Retriever | None = None) -> None:
        self.retriever = retriever or Retriever()

    def retrieve(
        self,
        question: str,
        *,
        top_k: int = 5,
        effective_date: date | None = None,
        analysis: Any | None = None,
    ) -> list[Document]:
        analysis = analysis or analyze_question(question)
        intent_queries = [intent.text for intent in analysis.intents if intent.kind == "legal"] or [
            question
        ]
        queries = [(query, query) for query in intent_queries]
        vehicle_types = detect_vehicle_types(question)
        if _is_vehicle_penalty_question(question):
            if len(vehicle_types) > 1:
                queries = [
                    (f"{query} đối với {vehicle_label(vehicle_type)}", label)
                    for query, label in queries
                    for vehicle_type in vehicle_types
                ]
            elif not vehicle_types:
                queries = [
                    (f"{query} đối với {category}", label)
                    for query, label in queries
                    for category in _GENERIC_VEHICLE_CATEGORIES
                ]
        per_query_k = max(1, top_k)
        ranked_lists: list[list[Document]] = [[] for _ in queries]

        def retrieve_query(index_query: tuple[int, tuple[str, str]]) -> tuple[int, list[Document]]:
            index, (query, label) = index_query
            retrieved = self.retriever.retrieve(
                query, top_k=per_query_k, effective_date=effective_date
            )
            return index, [
                Document(
                    page_content=document.page_content,
                    metadata={**(document.metadata or {}), "intent": label},
                )
                for document in retrieved
            ]

        worker_count = min(4, len(queries))
        if worker_count:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                for index, documents_for_query in executor.map(retrieve_query, enumerate(queries)):
                    ranked_lists[index] = documents_for_query

        scores: dict[tuple[str, ...], float] = {}
        first_seen: dict[tuple[str, ...], tuple[int, int]] = {}
        representatives: dict[tuple[str, ...], Document] = {}
        intent_labels: dict[tuple[str, ...], set[str]] = {}
        for list_index, ranked_documents in enumerate(ranked_lists):
            query = queries[list_index][1]
            for rank, document in enumerate(ranked_documents, start=1):
                key = _document_key(document)
                scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
                first_seen.setdefault(key, (list_index, rank))
                representatives.setdefault(key, document)
                intent_labels.setdefault(key, set()).add(query)

        ordered_keys = sorted(
            scores,
            key=lambda key: (-scores[key], first_seen[key][0], first_seen[key][1]),
        )
        bucket_counts: dict[tuple[Any, ...], int] = {}
        documents: list[Document] = []
        for key in ordered_keys:
            document = representatives[key]
            metadata = document.metadata or {}
            bucket = (
                metadata.get("document_id")
                or metadata.get("document_name")
                or metadata.get("document_number")
                or metadata.get("source_file")
                or metadata.get("source"),
                metadata.get("article"),
                metadata.get("clause"),
            )
            if bucket_counts.get(bucket, 0) >= 3:
                continue
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
            documents.append(
                Document(
                    page_content=document.page_content,
                    metadata={**metadata, "intent": sorted(intent_labels[key])},
                )
            )
        return documents

    def answer(
        self,
        question: str,
        *,
        chunks: Iterable[Document] | None = None,
        top_k: int = 5,
        effective_date: date | None = None,
        history: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        analysis = analyze_question(question)
        route = route_question(question)
        if route == "chitchat":
            return dict(CHITCHAT_RESPONSE)
        if route in {"web", "out_of_scope"} and not any(
            intent.kind == "legal" for intent in analysis.intents
        ):
            return {
                "answer": "Tôi chỉ có thể hỗ trợ các câu hỏi về pháp luật giao thông.",
                "citations": [],
                "status": "insufficient_evidence",
            }
        documents = (
            list(chunks)
            if chunks is not None
            else self.retrieve(
                question,
                top_k=top_k,
                effective_date=effective_date,
                analysis=analysis,
            )
        )
        evidence_groups, documents = _intent_groups(
            question,
            documents,
            analysis=analysis,
        )
        supported_groups = {key: value for key, value in evidence_groups.items() if value}
        if not supported_groups:
            return {
                "answer": "Chưa tìm thấy đủ căn cứ pháp lý cho câu hỏi này.",
                "citations": [],
                "status": "insufficient_evidence",
            }
        decision = assess_evidence(documents)
        if not decision.allowed:
            return {
                "answer": decision.message or "",
                "citations": [],
                "status": "insufficient_evidence",
            }
        answer = generate_answer(question, documents, evidence_groups=evidence_groups or None)
        unique_citations: list[dict[str, Any]] = []
        cited: set[tuple[str, ...]] = set()
        for document in documents:
            key = _document_key(document)
            if key not in cited:
                cited.add(key)
                unique_citations.append(_citation(document))
        return {
            "answer": answer,
            "citations": unique_citations,
            "status": "complete",
        }


CHITCHAT_RESPONSE = {
    "answer": "Xin chào! Tôi có thể giúp bạn tra cứu quy định pháp luật giao thông.",
    "citations": [],
    "status": "chitchat",
}


__all__ = ["RAGService"]
