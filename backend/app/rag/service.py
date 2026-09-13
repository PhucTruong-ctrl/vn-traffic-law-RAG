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
from .generator import generate_answer
from .query_rules import expand_query, requested_context
from .references import extract_references, metadata_matches
from .retrieval import Retriever

logger = logging.getLogger(__name__)
_GENERIC_VEHICLE_CATEGORIES = ("ô tô", "xe mô tô, xe gắn máy", "xe thô sơ")
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
_RAILWAY_TERMS = frozenset(("đường sắt", "đường ngang", "rào chắn", "tàu hỏa", "cầu chung"))
_PENALTY_TERMS = frozenset(("phạt", "xử phạt", "mức phạt", "tước", "trừ điểm"))


def _normalized_query(question: str) -> str:
    return " ".join(question.casefold().split())


def _question_tokens(question: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[^\W\d_]+", _normalized_query(question), flags=re.UNICODE)
        if t not in _QUESTION_STOPWORDS and len(t) > 1
    }


def _is_railway_question(question: str) -> bool:
    return any(token in _normalized_query(question) for token in _RAILWAY_TERMS)


def _is_penalty_or_permission_question(question: str) -> bool:
    lowered = _normalized_query(question)
    return any(term in lowered for term in _PENALTY_TERMS) or any(
        term in lowered for term in ("được phép", "có được", "được không", "cấm")
    )


def _needs_vehicle_scopes(question: str) -> bool:
    return _is_penalty_or_permission_question(question)


def _meaningful_tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE)
        if len(t) > 2 and t not in _QUESTION_STOPWORDS
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
                str(metadata.get(k, ""))
                for k in (
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
    if (
        not references
        and (_meaningful_tokens(expand_query(question)) & _meaningful_tokens(searchable)) == set()
    ):
        return False
    vehicle_types = detect_vehicle_types(question)
    if vehicle_types:
        categories = {str(c).casefold() for c in metadata.get("vehicle_categories", ())}
        labels = {VEHICLE_LABELS[item].casefold() for item in vehicle_types}
        legacy_scope = " ".join(
            str(metadata.get(k, "")) for k in ("vehicle", "vehicle_type", "vehicle_category")
        ).casefold()
        if categories and not categories.intersection(vehicle_types):
            return False
        if not categories and legacy_scope and not any(label in legacy_scope for label in labels):
            return False
    if effective_date:
        start = metadata.get("effective_from") or metadata.get("effective_date")
        end = metadata.get("effective_to")
        try:
            if start and date.fromisoformat(str(start)[:10]) > effective_date:
                return False
            if end and date.fromisoformat(str(end)[:10]) <= effective_date:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _version_key(document: Document) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    metadata = document.metadata or {}
    return (
        re.sub(
            r"[^\w]+", " ", str(metadata.get("normalized_action", "")).casefold(), flags=re.UNICODE
        ).strip(),
        tuple(metadata.get("vehicle_categories", ())),
        tuple(metadata.get("context_scope", ())),
    )


def _prefer_current_versions(documents: list[Document]) -> list[Document]:
    current = {
        _version_key(d) for d in documents if (d.metadata or {}).get("status") == "EFFECTIVE"
    }
    return [
        d
        for d in documents
        if str((d.metadata or {}).get("status", "")).upper() not in {"CEASED", "EXPIRED"}
        and not (
            (d.metadata or {}).get("status") == "PARTIALLY_EFFECTIVE" and _version_key(d) in current
        )
    ]


def _document_key(document: Document) -> tuple[str, ...]:
    metadata = document.metadata or {}
    return (
        ("chunk_id", str(metadata["chunk_id"]))
        if metadata.get("chunk_id")
        else (
            "source_content",
            str(metadata.get("source_file") or metadata.get("source") or ""),
            document.page_content,
        )
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
    intents = [i for i in analysis.intents if i.kind == "legal"]
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
        queries = [(i.text, i.text) for i in analysis.intents if i.kind == "legal"] or [
            (question, question)
        ]
        vehicle_types = detect_vehicle_types(question)
        if _needs_vehicle_scopes(question):
            scopes = (
                tuple(VEHICLE_LABELS[i] for i in vehicle_types)
                if vehicle_types
                else tuple(VEHICLE_LABELS.values())
            )
            queries = [(f"{q} đối với {scope}", label) for q, label in queries for scope in scopes][
                :12
            ]

        def retrieve_one(item):
            index, (query, label) = item
            return index, [
                Document(d.page_content, metadata={**(d.metadata or {}), "intent": label})
                for d in self.retriever.retrieve(
                    expand_query(query), top_k=max(1, top_k), effective_date=effective_date
                )
            ]

        ranked_lists: list[list[Document]] = [[] for _ in queries]
        with ThreadPoolExecutor(max_workers=min(4, len(queries))) as executor:
            for index, docs in executor.map(retrieve_one, enumerate(queries)):
                ranked_lists[index] = docs
        scores: dict[tuple[str, ...], float] = {}
        first_seen: dict[tuple[str, ...], tuple[int, int]] = {}
        representatives: dict[tuple[str, ...], Document] = {}
        labels: dict[tuple[str, ...], set[str]] = {}
        for list_index, docs in enumerate(ranked_lists):
            for rank, doc in enumerate(docs, 1):
                key = _document_key(doc)
                scores[key] = scores.get(key, 0) + 1 / (60 + rank)
                first_seen.setdefault(key, (list_index, rank))
                representatives.setdefault(key, doc)
                labels.setdefault(key, set()).add(queries[list_index][1])
        counts: dict[tuple[str | None, ...], int] = {}
        legal_labels = list(dict.fromkeys(label for _, label in queries))
        selected: list[tuple[str, ...]] = []
        selected_set: set[tuple[str, ...]] = set()

        def add_candidate(key: tuple[str, ...]) -> None:
            if key in selected_set:
                return
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
                return
            counts[bucket] = counts.get(bucket, 0) + 1
            selected.append(key)
            selected_set.add(key)

        # Reserve capacity for distinct intents, but never emit beyond top_k.
        for label in legal_labels[:top_k]:
            candidates = [
                key for key in scores if label in labels.get(key, set()) and key not in selected_set
            ]
            if candidates:
                add_candidate(min(candidates, key=lambda item: (-scores[item], first_seen[item])))
        for key in sorted(scores, key=lambda k: (-scores[k], first_seen[k])):
            if len(selected) >= top_k:
                break
            add_candidate(key)
        return [
            Document(
                representatives[key].page_content,
                metadata={**(representatives[key].metadata or {}), "intent": sorted(labels[key])},
            )
            for key in selected[:top_k]
        ]

    def answer(
        self,
        question: str,
        *,
        chunks: Iterable[Document] | None = None,
        top_k: int = 5,
        effective_date: date | None = None,
    ) -> dict[str, Any]:
        analysis = analyze_question(question)
        references = extract_references(question)
        route = classify_intent(question)
        if route == "chitchat":
            return {**CHITCHAT_RESPONSE, "claims": []}
        if (
            route in {"web", "out_of_scope"}
            and not references
            and not any(i.kind == "legal" for i in analysis.intents)
        ):
            return {
                "answer": "Tôi chỉ có thể hỗ trợ các câu hỏi về pháp luật giao thông.",
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": "out_of_scope",
            }
        documents = (
            list(chunks)
            if chunks is not None
            else self.retrieve(
                question, top_k=top_k, effective_date=effective_date, analysis=analysis
            )
        )
        for reference in references:
            structural = [d for d in documents if metadata_matches(d.metadata or {}, reference)]
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
                    d, question=question, references=[reference], effective_date=effective_date
                )
                for d in structural
            ):
                return {
                    "answer": ABSTENTION_MESSAGE,
                    "citations": [],
                    "claims": [],
                    "status": "insufficient_evidence",
                    "reason_code": "temporal_mismatch",
                }
        direct = [
            d
            for d in documents
            if _document_matches_filters(
                d, question=question, references=references[:1], effective_date=effective_date
            )
        ]
        if not direct and documents and not references:
            mismatch_reason = "no_relevant_provision"
        else:
            mismatch_reason = None
        if not references and effective_date is None:
            direct = _prefer_current_versions(direct)
        families = {_provision_family(d) for d in direct}
        filtered = list(direct)
        filtered.extend(
            d
            for d in documents
            if d not in filtered and _is_sanction(d) and _provision_family(d) in families
        )
        decision = assess_evidence(
            filtered,
            required_reference=references[0].as_dict() if references else None,
            required_intents=(
                (
                    i.text
                    for i in analysis.intents
                    if i.kind == "legal"
                    and len(analysis.intents) > 1
                    and i.text.rsplit(";", 1)[-1].strip()
                    not in {
                        "mức phạt",
                        "trừ điểm GPLX",
                        "tước quyền sử dụng",
                        "xử lý/tạm giữ phương tiện",
                    }
                )
                if not references
                else None
            ),
        )
        if not decision.allowed:
            return {
                "answer": decision.message or ABSTENTION_MESSAGE,
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": mismatch_reason or decision.reason or "insufficient_evidence",
            }
        try:
            cited = []
            seen = set()
            for doc in filtered:
                source_id = str((doc.metadata or {}).get("chunk_id", "")).strip()
                document_id = str((doc.metadata or {}).get("document_id", "")).strip()
                has_location = bool(
                    str((doc.metadata or {}).get("article") or "").strip()
                    or str((doc.metadata or {}).get("provision_family") or "").strip()
                )
                if not source_id or not document_id or not has_location:
                    raise ValueError("retrieved document is missing citation identity")
                if source_id not in seen:
                    seen.add(source_id)
                    cited.append(doc)
            citations = [_citation(d) for d in cited]
            groups = {
                label: docs
                for label, docs in _intent_groups(question, filtered, analysis=analysis)[0].items()
                if docs
            }
            answer = generate_answer(question, filtered, evidence_groups=groups or None)
        except Exception:
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
        claims = [
            {"claim": d.page_content, "provision_ids": [c["source_id"]]}
            for d, c in zip(cited, citations, strict=True)
        ]
        return {"answer": answer, "citations": citations, "claims": claims, "status": "complete"}


CHITCHAT_RESPONSE = {
    "answer": "Xin chào! Tôi có thể giúp bạn tra cứu quy định pháp luật giao thông.",
    "citations": [],
    "status": "GREETING",
}
__all__ = ["RAGService"]
