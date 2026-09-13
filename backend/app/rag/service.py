"""Retrieval and grounded answer orchestration."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

from langchain_core.documents import Document

from .analyzer import VEHICLE_LABELS, analyze_question, classify_intent, detect_vehicle_types
from .evidence import ABSTENTION_MESSAGE, assess_evidence
from .references import extract_references, metadata_matches
from .retrieval import Retriever

logger = logging.getLogger(__name__)
_GENERIC_VEHICLE_CATEGORIES = ("ô tô", "xe mô tô, xe gắn máy", "xe thô sơ")
_QUESTION_STOPWORDS = frozenset(
    "bao nhiêu là mức phạt đối với cho của và các xe phương tiện khi trong".split()
)
_RAILWAY_TERMS = frozenset(("đường sắt", "đường ngang", "rào chắn", "tàu hỏa", "cầu chung"))
_PENALTY_TERMS = frozenset(("phạt", "xử phạt", "mức phạt", "tước", "trừ điểm"))


def _normalized_query(question: str) -> str:
    return " ".join(question.casefold().split())


def _question_tokens(question: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W\d_]+", _normalized_query(question), flags=re.UNICODE)
        if token not in _QUESTION_STOPWORDS and len(token) > 1
    }


def _is_railway_question(question: str) -> bool:
    lowered = _normalized_query(question)
    return any(token in lowered for token in _RAILWAY_TERMS)


def _is_penalty_or_permission_question(question: str) -> bool:
    lowered = _normalized_query(question)
    return any(term in lowered for term in _PENALTY_TERMS) or any(
        term in lowered for term in ("được phép", "có được", "được không", "cấm")
    )


def _document_matches_filters(
    document: Document, *, question: str, references: list[Any], effective_date: date | None
) -> bool:
    metadata = document.metadata or {}
    if references and not any(metadata_matches(metadata, reference) for reference in references):
        return False
    context = " ".join(
        str(metadata.get(key, ""))
        for key in (
            "intent",
            "intent_text",
            "violation",
            "action",
            "question",
            "provision_family",
            "context",
        )
    )
    haystack = f"{context} {document.page_content}".casefold()
    question_tokens = _question_tokens(question)
    if question_tokens and not any(token in haystack for token in question_tokens):
        return False
    if not _is_railway_question(question) and any(token in haystack for token in _RAILWAY_TERMS):
        return False
    vehicles = detect_vehicle_types(question)
    if vehicles:
        labels = tuple(VEHICLE_LABELS[v].casefold() for v in vehicles)
        if not any(label in haystack for label in labels):
            return False
    if effective_date and metadata.get("effective_date"):
        try:
            if date.fromisoformat(str(metadata["effective_date"])) > effective_date:
                return False
        except ValueError:
            pass
    return True


def _document_key(document: Document) -> tuple[str, ...]:
    """Stable identity shared with cross-reference expansion."""
    metadata = document.metadata or {}
    chunk_id = metadata.get("chunk_id")
    if chunk_id:
        return ("chunk_id", str(chunk_id))
    source = metadata.get("source_file") or metadata.get("source") or ""
    return ("source_content", str(source), document.page_content)


def _citation(document: Document) -> dict[str, Any]:
    metadata = document.metadata or {}
    source_id = str(metadata.get("chunk_id", "")).strip()
    document_id = str(metadata.get("document_id", "")).strip()
    if not source_id or not document_id:
        raise ValueError("retrieved document is missing citation identity")
    return {
        "source_id": source_id,
        "document_id": document_id,
        "document_number": metadata.get("document_number"),
        "document_title": metadata.get("document_name") or metadata.get("document_title"),
        "article": metadata.get("article"),
        "clause": metadata.get("clause"),
        "point": metadata.get("point"),
        "page": metadata.get("page"),
        "source_file": metadata.get("source_file"),
        "source_url": metadata.get("source_url"),
        "pdf_url": metadata.get("pdf_url"),
        "excerpt": document.page_content,
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
        intent_queries = [i.text for i in analysis.intents if i.kind == "legal"] or [question]
        queries = [(query, query) for query in intent_queries]
        vehicle_types = detect_vehicle_types(question)
        if _is_penalty_or_permission_question(question):
            scopes = (
                tuple(VEHICLE_LABELS[v] for v in vehicle_types)
                if vehicle_types
                else _GENERIC_VEHICLE_CATEGORIES
            )
            queries = [
                (f"{query} đối với {scope}", label) for query, label in queries for scope in scopes
            ][:12]
        ranked_lists: list[list[Document]] = [[] for _ in queries]

        def retrieve_query(item: tuple[int, tuple[str, str]]) -> tuple[int, list[Document]]:
            index, (query, label) = item
            return index, [
                Document(d.page_content, metadata={**(d.metadata or {}), "intent": label})
                for d in self.retriever.retrieve(
                    query, top_k=max(1, top_k), effective_date=effective_date
                )
            ]

        if queries:
            with ThreadPoolExecutor(max_workers=min(4, len(queries))) as executor:
                for index, docs in executor.map(retrieve_query, enumerate(queries)):
                    ranked_lists[index] = docs
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
            scores, key=lambda key: (-scores[key], first_seen[key][0], first_seen[key][1])
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
                    document.page_content,
                    metadata={**metadata, "intent": sorted(intent_labels[key])},
                )
            )
        return documents[:top_k]

    def answer(
        self,
        question: str,
        *,
        chunks: Iterable[Document] | None = None,
        top_k: int = 5,
        effective_date: date | None = None,
    ) -> dict[str, Any]:
        analysis = analyze_question(question)
        route = classify_intent(question)
        if route == "chitchat":
            return {**CHITCHAT_RESPONSE, "claims": []}
        if route in {"web", "out_of_scope"} and not any(
            i.kind == "legal" for i in analysis.intents
        ):
            return {
                "answer": "Tôi chỉ có thể hỗ trợ các câu hỏi về pháp luật giao thông.",
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": "out_of_scope",
            }
        references = extract_references(question)
        documents = (
            list(chunks)
            if chunks is not None
            else self.retrieve(
                question, top_k=top_k, effective_date=effective_date, analysis=analysis
            )
        )
        if references and not all(
            any(metadata_matches(document.metadata or {}, reference) for document in documents)
            for reference in references
        ):
            structurally_matching = any(
                all(
                    metadata_matches(document.metadata or {}, reference) for reference in references
                )
                for document in documents
            )
            return {
                "answer": ABSTENTION_MESSAGE,
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": "temporal_mismatch"
                if structurally_matching and effective_date
                else "reference_not_found",
            }
        filtered_documents = [
            document
            for document in documents
            if _document_matches_filters(
                document, question=question, references=references, effective_date=effective_date
            )
        ]
        if not filtered_documents:
            structural_documents = [
                document
                for document in documents
                if not references
                or any(
                    metadata_matches(document.metadata or {}, reference) for reference in references
                )
            ]
            reason = (
                "missing_context"
                if documents and not _question_tokens(question)
                else "no_relevant_provision"
            )
            return {
                "answer": ABSTENTION_MESSAGE,
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": reason,
            }
        evidence_groups, _ = _intent_groups(question, filtered_documents, analysis=analysis)
        required_reference = references[0] if references else None
        decision = assess_evidence(
            filtered_documents,
            required_reference=required_reference.as_dict() if required_reference else None,
            required_intents=(
                (intent.text for intent in analysis.intents if intent.kind == "legal")
                if not references
                else (reference.as_dict().get("number", "") for reference in references)
            ),
        )
        if not decision.allowed:
            return {
                "answer": decision.message or "",
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": decision.reason or "insufficient_evidence",
            }
        try:
            cited_documents = []
            seen_ids: set[str] = set()
            for document in filtered_documents:
                source_id = str((document.metadata or {}).get("chunk_id", "")).strip()
                if not source_id or source_id in seen_ids:
                    continue
                seen_ids.add(source_id)
                cited_documents.append(document)
            citations = [_citation(document) for document in cited_documents]
        except ValueError:
            return {
                "answer": ABSTENTION_MESSAGE,
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": "insufficient_evidence",
            }
        if not citations:
            return {
                "answer": ABSTENTION_MESSAGE,
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": "insufficient_evidence",
            }
        answer = generate_answer(
            question, filtered_documents, evidence_groups=evidence_groups or None
        )
        claims = [
            {
                "claim": document.page_content,
                "provision_ids": [citation["source_id"]],
            }
            for document, citation in zip(cited_documents, citations, strict=True)
        ]
        return {"answer": answer, "citations": citations, "claims": claims, "status": "complete"}


CHITCHAT_RESPONSE = {
    "answer": "Xin chào! Tôi có thể giúp bạn tra cứu quy định pháp luật giao thông.",
    "citations": [],
    "status": "GREETING",
}


__all__ = ["RAGService"]
