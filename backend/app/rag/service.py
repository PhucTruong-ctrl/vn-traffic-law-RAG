"""Retrieval and grounded answer orchestration."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any

from langchain_core.documents import Document

from .analyzer import VEHICLE_LABELS, analyze_question, classify_intent, detect_vehicle_types
from .evidence import ABSTENTION_MESSAGE, assess_evidence
from .generator import generate_answer
from .query_rules import expand_query, requested_context
from .references import extract_references, metadata_matches
from .retrieval import Retriever

logger = logging.getLogger(__name__)
_QUESTION_STOPWORDS = frozenset(
    {
        "bao",
        "bị",
        "có",
        "đang",
        "điểm",
        "điều",
        "định",
        "đối",
        "được",
        "hoặc",
        "khi",
        "khiển",
        "khoản",
        "không",
        "là",
        "luật",
        "mức",
        "nào",
        "nghị",
        "người",
        "nhiêu",
        "phạt",
        "phương",
        "quy",
        "thế",
        "thông",
        "tiện",
        "tư",
        "và",
        "với",
        "xe",
    }
)


def _normalized_query(question: str) -> str:
    return " ".join(question.casefold().split())


def _needs_vehicle_scopes(question: str) -> bool:
    lowered = _normalized_query(question)
    return any(
        marker in lowered
        for marker in ("phạt", "xử phạt", "mức phạt", "tước", "trừ điểm", "có được")
    )


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE)
        if len(token) > 2 and token not in _QUESTION_STOPWORDS
    }


def _provision_family(document: Document) -> tuple[str, str, str]:
    metadata = document.metadata or {}
    return (
        str(metadata.get("document_id", "")),
        str(metadata.get("article", "")).removeprefix("Điều ").strip(),
        str(metadata.get("clause", "")).removeprefix("Khoản ").strip(),
    )


def _is_sanction(document: Document) -> bool:
    return bool(
        re.search(
            r"(?:phạt\s+tiền|trừ\s+điểm|tước\s+quyền|tịch\s+thu|tạm\s+giữ)",
            document.page_content,
            re.IGNORECASE,
        )
    )


def _document_matches_filters(
    document: Document, *, question: str, references: list[Any], effective_date: date | None
) -> bool:
    metadata = document.metadata or {}
    if references and not any(metadata_matches(metadata, reference) for reference in references):
        return False
    searchable = " ".join(
        [
            document.page_content,
            *(
                str(metadata.get(key, ""))
                for key in (
                    "provision_family",
                    "context",
                    "context_scope",
                    "violation",
                    "action",
                    "normalized_action",
                    "vehicle",
                    "vehicle_type",
                    "vehicle_categories",
                )
            ),
        ]
    )
    scopes = {str(scope).casefold() for scope in metadata.get("context_scope", ())}
    context = requested_context(question).casefold()
    if scopes and context and context not in scopes:
        return False
    question_tokens = _meaningful_tokens(expand_query(question))
    evidence_tokens = _meaningful_tokens(searchable)
    if not references and question_tokens and not question_tokens.intersection(evidence_tokens):
        return False
    vehicle_types = detect_vehicle_types(question)
    if vehicle_types:
        categories = {
            str(category).casefold() for category in metadata.get("vehicle_categories", ())
        }
        labels = {VEHICLE_LABELS[item].casefold() for item in vehicle_types}
        legacy_scope = " ".join(
            str(metadata.get(key, "")) for key in ("vehicle", "vehicle_type", "vehicle_category")
        ).casefold()
        if categories and not categories.intersection(vehicle_types):
            return False
        if not categories and legacy_scope and not any(label in legacy_scope for label in labels):
            return False
    # Context scope is checked before lexical relevance so explicit contexts
    # cannot be displaced by fan-out query wording.
    if effective_date:
        start = metadata.get("effective_from") or metadata.get("effective_date")
        end = metadata.get("effective_to")
        try:
            if start and datetime.fromisoformat(str(start)).date() > effective_date:
                return False
            if end and datetime.fromisoformat(str(end)).date() <= effective_date:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _version_key(document: Document) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    metadata = document.metadata or {}
    return (
        re.sub(
            r"[^\w]+",
            " ",
            str(metadata.get("normalized_action", "")).casefold(),
            flags=re.UNICODE,
        ).strip(),
        tuple(metadata.get("vehicle_categories", ())),
        tuple(metadata.get("context_scope", ())),
    )


def _prefer_current_versions(documents: list[Document]) -> list[Document]:
    current_actions = {
        _version_key(document)
        for document in documents
        if (document.metadata or {}).get("status") == "EFFECTIVE"
    }
    return [
        document
        for document in documents
        if str((document.metadata or {}).get("status", "")).upper() not in {"CEASED", "EXPIRED"}
        and not (
            (document.metadata or {}).get("status") == "PARTIALLY_EFFECTIVE"
            and _version_key(document) in current_actions
        )
    ]


def _document_key(document: Document) -> tuple[str, ...]:
    metadata = document.metadata or {}
    if metadata.get("chunk_id"):
        return ("chunk_id", str(metadata["chunk_id"]))
    return (
        "source_content",
        str(metadata.get("source_file") or metadata.get("source") or ""),
        document.page_content,
    )


def _citation(document: Document) -> dict[str, Any]:
    metadata = document.metadata or {}
    source_id = str(metadata.get("chunk_id", "")).strip()
    document_id = str(metadata.get("document_id", "")).strip()
    if not source_id or not document_id or not document.page_content.strip():
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
    question: str, documents: list[Document], *, analysis: Any | None = None
) -> tuple[dict[str, list[Document]], list[Document]]:
    analysis = analysis or analyze_question(question)
    intents = [intent for intent in analysis.intents if intent.kind == "legal"]
    if not intents:
        return {}, documents
    groups: dict[str, list[Document]] = {intent.text: [] for intent in intents}
    for document in documents:
        labels = (document.metadata or {}).get("intent") or (document.metadata or {}).get(
            "intent_text"
        )
        labels = (labels,) if isinstance(labels, str) else labels
        if isinstance(labels, (list, tuple, set)):
            for label in labels:
                if label in groups:
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
        queries = [
            (intent.text, intent.text) for intent in analysis.intents if intent.kind == "legal"
        ] or [(question, question)]
        vehicle_types = detect_vehicle_types(question)
        if _needs_vehicle_scopes(question):
            scopes = (
                tuple(VEHICLE_LABELS[item] for item in vehicle_types)
                if vehicle_types
                else tuple(dict.fromkeys(VEHICLE_LABELS.values()))
            )
            queries = [
                (f"{query} đối với {scope}", label) for query, label in queries for scope in scopes
            ][:12]
        ranked_lists: list[list[Document]] = [[] for _ in queries]

        def retrieve_one(item: tuple[int, tuple[str, str]]) -> tuple[int, list[Document]]:
            index, (query, label) = item
            return index, [
                Document(doc.page_content, metadata={**(doc.metadata or {}), "intent": label})
                for doc in self.retriever.retrieve(
                    expand_query(query),
                    top_k=max(1, top_k),
                    effective_date=effective_date,
                )
            ]

        with ThreadPoolExecutor(max_workers=min(4, len(queries))) as executor:
            for index, docs in executor.map(retrieve_one, enumerate(queries)):
                ranked_lists[index] = docs
        scores: dict[tuple[str, ...], float] = {}
        first_seen: dict[tuple[str, ...], tuple[int, int]] = {}
        representatives: dict[tuple[str, ...], Document] = {}
        labels: dict[tuple[str, ...], set[str]] = {}
        for list_index, docs in enumerate(ranked_lists):
            label = queries[list_index][1]
            for rank, doc in enumerate(docs, 1):
                key = _document_key(doc)
                scores[key] = scores.get(key, 0) + 1 / (60 + rank)
                first_seen.setdefault(key, (list_index, rank))
                representatives.setdefault(key, doc)
                labels.setdefault(key, set()).add(label)
        ordered = sorted(scores, key=lambda key: (-scores[key], first_seen[key]))
        counts: dict[tuple[Any, ...], int] = {}
        result: list[Document] = []
        for key in ordered:
            doc = representatives[key]
            metadata = doc.metadata or {}
            bucket = (
                metadata.get("document_id")
                or metadata.get("document_number")
                or metadata.get("source_file"),
                metadata.get("article"),
                metadata.get("clause"),
            )
            if counts.get(bucket, 0) >= 3:
                continue
            counts[bucket] = counts.get(bucket, 0) + 1
            result.append(
                Document(doc.page_content, metadata={**metadata, "intent": sorted(labels[key])})
            )
        return result[:top_k]

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
            intent.kind == "legal" for intent in analysis.intents
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
        for reference in references:
            structural = [
                doc for doc in documents if metadata_matches(doc.metadata or {}, reference)
            ]
            if not structural:
                return {
                    "answer": ABSTENTION_MESSAGE,
                    "citations": [],
                    "claims": [],
                    "status": "insufficient_evidence",
                    "reason_code": "reference_not_found",
                }
            if effective_date and not any(
                _document_matches_filters(
                    doc, question=question, references=[reference], effective_date=effective_date
                )
                for doc in structural
            ):
                return {
                    "answer": ABSTENTION_MESSAGE,
                    "citations": [],
                    "claims": [],
                    "status": "insufficient_evidence",
                    "reason_code": "temporal_mismatch",
                }
        direct = [
            doc
            for doc in documents
            if _document_matches_filters(
                doc, question=question, references=references, effective_date=effective_date
            )
        ]
        if chunks is None and _needs_vehicle_scopes(question):
            complete_family = getattr(self.retriever, "complete_family", None)
            if callable(complete_family):
                existing = {_document_key(doc) for doc in documents}
                for doc in direct:
                    for sibling in complete_family(doc, limit=2, effective_date=effective_date):
                        key = _document_key(sibling)
                        if key not in existing:
                            existing.add(key)
                            documents.append(sibling)
        if not references and effective_date is None:
            direct = _prefer_current_versions(direct)
        families = {_provision_family(doc) for doc in direct}
        filtered = list(direct)
        filtered.extend(
            doc
            for doc in documents
            if doc not in filtered and _is_sanction(doc) and _provision_family(doc) in families
        )
        if not filtered:
            return {
                "answer": ABSTENTION_MESSAGE,
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": "no_relevant_provision",
            }
        decision = assess_evidence(filtered, required_intents=None)
        if not decision.allowed:
            return {
                "answer": decision.message or ABSTENTION_MESSAGE,
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": decision.reason or "insufficient_evidence",
            }
        try:
            cited: list[Document] = []
            seen: set[str] = set()
            for doc in filtered:
                source_id = str((doc.metadata or {}).get("chunk_id", "")).strip()
                if source_id and source_id not in seen:
                    seen.add(source_id)
                    cited.append(doc)
            citations = [_citation(doc) for doc in cited]
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
        try:
            groups = _intent_groups(question, filtered, analysis=analysis)[0]
            nonempty_groups = {label: docs for label, docs in groups.items() if docs}
            answer = generate_answer(
                question,
                filtered,
                evidence_groups=nonempty_groups or None,
            )
        except Exception:
            return {
                "answer": ABSTENTION_MESSAGE,
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": "insufficient_evidence",
            }
        claims = [
            {"claim": doc.page_content, "provision_ids": [citation["source_id"]]}
            for doc, citation in zip(cited, citations, strict=True)
        ]
        citation_ids = {item["source_id"] for item in citations}
        claim_ids = {source_id for claim in claims for source_id in claim["provision_ids"]}
        if citation_ids != claim_ids:
            return {
                "answer": ABSTENTION_MESSAGE,
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": "insufficient_evidence",
            }
        return {"answer": answer, "citations": citations, "claims": claims, "status": "complete"}


CHITCHAT_RESPONSE = {
    "answer": "Xin chào! Tôi có thể giúp bạn tra cứu quy định pháp luật giao thông.",
    "citations": [],
    "status": "GREETING",
}

__all__ = ["RAGService"]
