"""Retrieval and grounded answer orchestration."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import date
from typing import Any

from langchain_core.documents import Document

from .analyzer import (
    CANONICAL_VEHICLE_CATEGORIES,
    VEHICLE_LABELS,
    analyze_question,
    analyze_request,
    classify_intent,
    detect_vehicle_types,
    normalize_vehicle_metadata,
)
from .evidence import (
    ABSTENTION_MESSAGE,
    CLARIFICATION_REQUIRED_MESSAGE,
    RETRIEVAL_FAILURE_MESSAGE,
)
from .generator import generate_answer
from .query_rules import expand_query, load_query_rules, requested_context
from .references import extract_references, metadata_matches
from .retrieval import RetrievalProviderError, Retriever
from .verification import sanitize_response

CHITCHAT_RESPONSE = {
    "answer": "Xin chào! Tôi có thể giúp bạn tra cứu quy định pháp luật giao thông.",
    "citations": [],
    "status": "GREETING",
}

logger = logging.getLogger(__name__)
_GENERIC_VEHICLE_CATEGORIES = tuple(VEHICLE_LABELS[k] for k in CANONICAL_VEHICLE_CATEGORIES)
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
    }
)
_RAILWAY_TERMS = frozenset(("đường sắt", "đường ngang", "rào chắn", "tàu hỏa", "cầu chung"))
# Question-frame words (pronouns, time deixis, modals, interrogatives) name no conduct.
# A penalty question built only from these describes no violation, so it cannot be
# answered from the corpus and must be clarified instead of guessed.
_QUESTION_FRAME_TOKENS = frozenset(
    {
        "anh",
        "bao",
        "bây",
        "bắt",
        "buộc",
        "chị",
        "cho",
        "chúng",
        "chính",
        "cần",
        "cụ",
        "cũng",
        "đây",
        "đó",
        "giúp",
        "gì",
        "hôm",
        "hỏi",
        "kính",
        "làm",
        "mai",
        "mình",
        "mong",
        "muốn",
        "nay",
        "ngày",
        "như",
        "phải",
        "qua",
        "rồi",
        "sao",
        "tôi",
        "trường",
        "và",
        "vấn",
        "vậy",
        "xin",
        "xác",
        "ạ",
    }
)
_PENALTY_TERMS = frozenset(("phạt", "xử phạt", "mức phạt", "tước", "trừ điểm"))
_OUT_OF_SCOPE_TERMS = (
    ("thuế", "thu nhập cá nhân"),
    ("luật hình sự", "tội phạm", "truy tố", "hình phạt hình sự"),
    ("hợp đồng", "tranh chấp dân sự", "bồi thường dân sự", "khởi kiện", "đơn kiện"),
    ("hàng không", "aviation", "máy bay", "chuyến bay"),
)


def _is_clear_out_of_scope(question: str) -> bool:
    lowered = _normalized_query(question)
    if _is_railway_question(question):
        return False
    return any(any(term in lowered for term in domain) for domain in _OUT_OF_SCOPE_TERMS)


def _normalized_query(question: str) -> str:
    return " ".join(question.casefold().split())


def _question_tokens(question: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[^\W\d_]+", _normalized_query(question), flags=re.UNICODE)
        if t not in _QUESTION_STOPWORDS and len(t) > 1
    }


def _conduct_tokens(question: str) -> set[str]:
    """Question tokens that could name a violation or its subject matter."""
    return _question_tokens(question) - _QUESTION_FRAME_TOKENS


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


def _canonical_coordinates(documents: Iterable[Document]) -> list[str]:
    """Deduped `{document}__dieu-N[__khoan-M[__diem-X]]` ids, first-seen order."""
    coordinates: list[str] = []
    seen: set[str] = set()
    for document in documents:
        metadata = normalize_vehicle_metadata(document.metadata or {})
        document_id = metadata.get("document_id")
        article = str(metadata.get("article", "")).removeprefix("Điều ").strip()
        if not document_id or not article:
            continue
        coordinate = f"{document_id}__dieu-{article}"
        for key, prefix in (("clause", "khoan"), ("point", "diem")):
            if metadata.get(key) is None:
                break
            value = str(metadata.get(key, "")).removeprefix("Khoản ").removeprefix("Điểm ").strip()
            if not value:
                break
            coordinate += f"__{prefix}-{value}"
        if coordinate not in seen:
            seen.add(coordinate)
            coordinates.append(coordinate)
    return coordinates


def _provision_family(document: Document) -> tuple[str, str, str]:
    metadata = normalize_vehicle_metadata(document.metadata or {})
    return (
        str(metadata.get("document_id", "")),
        str(metadata.get("article", "")).removeprefix("Điều ").strip(),
        str(metadata.get("clause", "")).removeprefix("Khoản ").strip(),
    )


def _action_terms_for_question(question: str) -> tuple[str, ...]:
    """Return canonical action terms implied by configured aliases."""
    normalized_question = re.sub(r"[^\w]+", " ", question.casefold(), flags=re.UNICODE).strip()
    terms = {
        re.sub(r"[^\w]+", " ", str(canonical).casefold(), flags=re.UNICODE).strip()
        for alias, canonical in load_query_rules().get("action_aliases", {}).items()
        if re.sub(r"[^\w]+", " ", str(alias).casefold(), flags=re.UNICODE).strip()
        in normalized_question
    }
    return tuple(sorted((term for term in terms if term), key=lambda term: (-len(term), term)))


def _action_document_matches(document: Document, required: tuple[str, ...]) -> bool:
    metadata = normalize_vehicle_metadata(document.metadata or {})
    actual = " ".join(
        str(metadata.get(key, "")) for key in ("normalized_action", "action", "violation")
    ).casefold()
    text = document.page_content.casefold()
    configured = load_query_rules().get("action_evidence_aliases", {})
    return all(
        term in actual
        or term in text
        or any(
            str(alias).casefold() in actual or str(alias).casefold() in text
            for alias in configured.get(term, ())
        )
        for term in required
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
    document: Document,
    *,
    question: str,
    references: list[Any],
    effective_date: date | None,
    required_action_terms: tuple[str, ...] = (),
) -> bool:
    metadata = normalize_vehicle_metadata(document.metadata or {})
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
    raw_scopes = metadata.get("context_scope", ())
    scopes = (
        {str(scope).casefold() for scope in raw_scopes}
        if isinstance(raw_scopes, (list, tuple, set))
        else {str(raw_scopes).casefold()}
        if raw_scopes
        else set()
    )
    context = requested_context(question).casefold()
    if scopes and context and context not in scopes and context != "road_traffic":
        return False
    if (
        not references
        and not required_action_terms
        and (_meaningful_tokens(expand_query(question)) & _meaningful_tokens(searchable)) == set()
    ):
        return False
    vehicle_types = detect_vehicle_types(question)
    if vehicle_types:
        raw_categories = metadata.get("vehicle_categories", ())
        categories = (
            {str(category) for category in raw_categories}
            if isinstance(raw_categories, (list, tuple, set))
            else {str(raw_categories)}
            if raw_categories
            else set()
        )
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
    return not required_action_terms or _action_document_matches(document, required_action_terms)


def _version_key(document: Document) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    metadata = normalize_vehicle_metadata(document.metadata or {})
    categories = metadata.get("vehicle_categories")
    scopes = metadata.get("context_scope")
    return (
        re.sub(
            r"[^\w]+", " ", str(metadata.get("normalized_action", "")).casefold(), flags=re.UNICODE
        ).strip(),
        tuple(str(value) for value in categories)
        if isinstance(categories, (list, tuple, set))
        else (),
        tuple(str(value) for value in scopes) if isinstance(scopes, (list, tuple, set)) else (),
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
    metadata = normalize_vehicle_metadata(document.metadata or {})
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
    metadata = normalize_vehicle_metadata(document.metadata or {})
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
    if analysis is None:
        analysis = analyze_question(question)
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
    if not any(groups.values()):
        groups[next(iter(groups))] = list(documents)
    return groups, documents


class RAGService:
    def __init__(self, retriever: Retriever | None = None, *, clock: Any | None = None) -> None:
        self.retriever = retriever or Retriever()
        self.clock = clock or __import__("time").monotonic

    def _search_and_fuse(
        self,
        queries: list[tuple[str, str]],
        *,
        top_k: int | None,
        effective_date: date | None,
        deadline: float | None,
    ) -> list[Document]:
        def retrieve_one(item: tuple[int, tuple[str, str]]) -> tuple[int, list[Document], bool]:
            index, (query, label) = item
            if deadline is not None and self.clock() >= deadline:
                return index, [], True
            try:
                docs = self.retriever.retrieve(
                    expand_query(query), top_k=8, effective_date=effective_date
                )
            except RetrievalProviderError:
                return index, [], True
            return (
                index,
                [
                    Document(d.page_content, metadata={**(d.metadata or {}), "intent": label})
                    for d in docs
                ],
                False,
            )

        ranked_lists: list[list[Document]] = [[] for _ in queries]
        provider_failures = 0
        harvested = False
        executor = ThreadPoolExecutor(max_workers=min(8, max(1, len(queries))))
        try:
            futures = {executor.submit(retrieve_one, item): item[0] for item in enumerate(queries)}
            wait_for = None if deadline is None else max(0.0, deadline - self.clock())
            try:
                for future in as_completed(futures, timeout=wait_for):
                    index, docs, failed = future.result()
                    ranked_lists[index] = docs
                    provider_failures += int(failed)
                    harvested = harvested or bool(docs)
            except FuturesTimeout:
                pass
        finally:
            # A bounded request never waits on a throttled provider: whatever
            # arrived in time is used, the rest is abandoned in the background.
            executor.shutdown(wait=deadline is None, cancel_futures=deadline is not None)
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
        counts: dict[tuple[object, ...], int] = {}
        selected: list[Document] = []
        fusion_k = min(25, max(12, top_k or 12))
        for key in sorted(scores, key=lambda item: (-scores[item], first_seen[item])):
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
            selected.append(
                Document(doc.page_content, metadata={**metadata, "intent": sorted(labels[key])})
            )
            if len(selected) >= fusion_k:
                break
        if not selected and provider_failures == len(queries):
            raise RetrievalProviderError("every retrieval query failed")
        if not selected and not harvested and deadline is not None and self.clock() >= deadline:
            raise TimeoutError("retrieval deadline expired before any query returned")
        return selected

    def retrieve(
        self,
        question: str,
        *,
        top_k: int = 5,
        effective_date: date | None = None,
        analysis: Any | None = None,
        deadline: float | None = None,
    ) -> list[Document]:
        analysis = analysis or analyze_question(question)
        queries = [(i.text, i.text) for i in analysis.intents if i.kind == "legal"] or [
            (question, question)
        ]
        vehicle_types = tuple(
            getattr(analysis, "vehicle_types", ()) or detect_vehicle_types(question)
        )
        if _needs_vehicle_scopes(question):
            scopes = (
                tuple(VEHICLE_LABELS[i] for i in vehicle_types)
                if vehicle_types
                else _GENERIC_VEHICLE_CATEGORIES
            )
            queries = (
                [(f"{queries[0][0]} đối với {scope}", queries[0][1]) for scope in scopes]
                if len(queries) == 1
                else [
                    (f"{query} đối với {scope}", label)
                    for scope in scopes
                    for query, label in queries
                ][:4]
            )
        return self._search_and_fuse(
            queries, top_k=top_k, effective_date=effective_date, deadline=deadline
        )

    def retrieve_for_request(
        self,
        request: Any,
        *,
        top_k: int | None = None,
        effective_date: date | None = None,
        deadline: float | None = None,
    ) -> list[Document]:
        queries = [(query, query) for query in request.expanded_queries]
        vehicle_types = tuple(
            getattr(request.frames, "vehicle_types", ())
            or detect_vehicle_types(request.standalone_query)
        )
        if _needs_vehicle_scopes(request.standalone_query):
            scopes = (
                tuple(VEHICLE_LABELS[i] for i in vehicle_types)
                if vehicle_types
                else _GENERIC_VEHICLE_CATEGORIES
            )
            queries = (
                [(f"{queries[0][0]} đối với {scope}", queries[0][1]) for scope in scopes]
                if len(queries) == 1
                else [
                    (f"{query} đối với {scope}", label)
                    for scope in scopes
                    for query, label in queries
                ][:4]
            )
        return self._search_and_fuse(
            queries, top_k=top_k, effective_date=effective_date, deadline=deadline
        )

    def answer(
        self,
        question: str,
        *,
        history: object = (),
        chunks: Iterable[Document] | None = None,
        top_k: int | None = None,
        effective_date: date | None = None,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        end = deadline if deadline is not None else self.clock() + 30.0
        started = self.clock()
        retrieval_ms = 0.0
        generation_ms = 0.0
        documents: list[Document] = []

        def abstain(reason: str) -> dict[str, Any]:
            message = (
                RETRIEVAL_FAILURE_MESSAGE
                if reason in {"retrieval_timeout", "retrieval_unavailable"}
                else CLARIFICATION_REQUIRED_MESSAGE
                if reason == "clarification_required"
                else ABSTENTION_MESSAGE
            )
            return {
                "answer": message,
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": reason,
                "debug": {
                    "stage_ms": {
                        "retrieval": retrieval_ms,
                        "generation": 0.0,
                        "total": max((self.clock() - started) * 1000.0, 0.0),
                    },
                    "retrieved_provision_ids": _canonical_coordinates(documents),
                    "retrieved_chunk_ids": [],
                    "cited_provision_ids": [],
                },
            }

        request = analyze_request(
            question, history, deadline=min(end, self.clock() + 12.0), clock=self.clock
        )
        if request.category == "chitchat":
            return {
                **CHITCHAT_RESPONSE,
                "claims": [],
                "debug": {
                    "stage_ms": {"retrieval": 0.0, "generation": 0.0, "total": 0.0},
                    "retrieved_provision_ids": [],
                    "cited_provision_ids": [],
                },
            }
        if request.category == "out_of_scope" or _is_clear_out_of_scope(question):
            return {
                "answer": "Tôi chỉ có thể hỗ trợ các câu hỏi về pháp luật giao thông.",
                "citations": [],
                "claims": [],
                "status": "insufficient_evidence",
                "reason_code": "out_of_scope",
                "debug": {
                    "stage_ms": {"retrieval": 0.0, "generation": 0.0, "total": 0.0},
                    "retrieved_provision_ids": [],
                    "cited_provision_ids": [],
                },
            }
        analysis, standalone = request.frames, request.standalone_query
        references, route = extract_references(question), classify_intent(standalone)
        # A penalty question that names no conduct and no provision cannot be grounded,
        # so refusing here also avoids paying for a retrieval that cannot help. The
        # decision reads the user's own words: an analyzer rewrite must never be able to
        # turn an underspecified question into an answerable one.
        if (
            _is_penalty_or_permission_question(question)
            and not references
            and not _action_terms_for_question(question)
            and not _conduct_tokens(question)
        ):
            return abstain("clarification_required")
        try:
            documents = (
                list(chunks)
                if chunks is not None
                else self.retrieve_for_request(
                    request,
                    top_k=top_k,
                    effective_date=effective_date,
                    deadline=min(end, self.clock() + 25.0),
                )
            )
        except RetrievalProviderError:
            logger.warning("retrieval provider unavailable for question=%r", standalone)
            return abstain("retrieval_unavailable")
        except TimeoutError:
            logger.warning("retrieval timed out for question=%r", standalone)
            return abstain("retrieval_timeout")
        if not documents:
            if (
                _is_penalty_or_permission_question(standalone)
                and not references
                and not _action_terms_for_question(standalone)
            ):
                return abstain("clarification_required")
            return abstain("insufficient_evidence")
        for reference in references:
            structural = [d for d in documents if metadata_matches(d.metadata or {}, reference)]
            if not structural:
                try:
                    fetched = self.retriever.fetch_provisions(
                        reference,
                        question=standalone,
                        limit=12,
                        effective_date=effective_date,
                    )
                except RetrievalProviderError:
                    fetched = []
                if fetched:
                    by_key = {_document_key(d): d for d in fetched}
                    by_key.update({_document_key(d): d for d in documents})
                    documents = list(by_key.values())
                    structural = [
                        d for d in documents if metadata_matches(d.metadata or {}, reference)
                    ]
            if not structural:
                return abstain("reference_not_found")
            if effective_date and not any(
                _document_matches_filters(
                    d,
                    question=standalone,
                    references=[reference],
                    effective_date=effective_date,
                    required_action_terms=(),
                )
                for d in structural
            ):
                return abstain("temporal_mismatch")
        action_terms = _action_terms_for_question(standalone)
        direct = [
            d
            for d in documents
            if _document_matches_filters(
                d,
                question=standalone,
                references=references[:1],
                effective_date=effective_date,
                required_action_terms=action_terms,
            )
        ]
        if effective_date and not direct:
            return abstain("temporal_mismatch")
        railway_markers = ("đường ngang", "cầu chung", "đường sắt", "rào chắn", "tàu hỏa")
        railway_only = documents and all(
            "railway_crossing" in str((d.metadata or {}).get("context_scope", "")).casefold()
            or any(marker in d.page_content.casefold() for marker in railway_markers)
            for d in documents
        )
        if railway_only and not any(marker in standalone.casefold() for marker in railway_markers):
            return abstain("no_relevant_provision")
        if not references and effective_date is None:
            direct = _prefer_current_versions(direct)
        filtered = list(direct or documents)
        families = {_provision_family(d) for d in documents}
        complete_family = getattr(self.retriever, "complete_family", None)
        if complete_family:
            # The fine amount lives in the clause header, which carries no action
            # wording and is therefore absent from the action-filtered `direct`
            # set. Complete families over everything that is cited, not `direct`.
            completed: set[tuple[str, str, str]] = set()
            for document in filtered[:6]:
                family = _provision_family(document)
                if not family or family in completed:
                    continue
                completed.add(family)
                try:
                    # Header first: the chunk that carries the fine amount.
                    siblings = complete_family(document, limit=3, effective_date=effective_date)
                except Exception:
                    continue
                for sibling in siblings:
                    if sibling not in filtered:
                        filtered.append(sibling)
        filtered.extend(
            d
            for d in documents
            if d not in filtered and _is_sanction(d) and _provision_family(d) in families
        )
        cited, seen = [], set()
        for document in filtered:
            metadata = normalize_vehicle_metadata(document.metadata or {})
            if (
                not metadata.get("chunk_id")
                or not metadata.get("document_id")
                or not (metadata.get("article") or metadata.get("provision_family"))
            ):
                continue
            if str(metadata["chunk_id"]) not in seen:
                seen.add(str(metadata["chunk_id"]))
                cited.append(document)
        citations = [_citation(d) for d in cited]
        cited_by_source = {
            str(citation["source_id"]): document
            for document, citation in zip(cited, citations, strict=True)
        }
        claims = [
            {
                "claim": cited_by_source[citation["source_id"]].page_content,
                "provision_ids": [citation["source_id"]],
            }
            for citation in citations
        ]
        groups, _ = _intent_groups(standalone, filtered, analysis=analysis)
        groups = {label: docs for label, docs in groups.items() if docs}
        retrieval_ms = max((self.clock() - started) * 1000.0, 0.0)
        generation_started = self.clock()
        try:
            answer_text = generate_answer(
                standalone,
                filtered,
                evidence_groups=groups or None,
                deadline=min(end, self.clock() + 18.0),
                clock=self.clock,
            )
        except TimeoutError:
            return abstain("request_timeout")
        except Exception:
            return abstain("generation_failed")
        generation_ms = max((self.clock() - generation_started) * 1000.0, 0.0)
        sanitized = sanitize_response(
            standalone,
            route,
            analysis,
            references,
            effective_date,
            filtered,
            answer_text,
            citations,
            claims,
        )
        if not sanitized.allowed:
            return abstain(sanitized.reason)
        return {
            "answer": sanitized.answer,
            "citations": list(sanitized.citations),
            "claims": list(sanitized.claims),
            "status": "verified",
            "debug": {
                "stage_ms": {
                    "retrieval": retrieval_ms,
                    "generation": generation_ms,
                    "total": max((self.clock() - started) * 1000.0, 0.0),
                },
                "retrieved_provision_ids": _canonical_coordinates(documents),
                "retrieved_chunk_ids": [
                    str(normalize_vehicle_metadata(d.metadata or {}).get("chunk_id"))
                    for d in documents
                    if normalize_vehicle_metadata(d.metadata or {}).get("chunk_id")
                ],
                "cited_provision_ids": _canonical_coordinates(cited),
            },
        }
