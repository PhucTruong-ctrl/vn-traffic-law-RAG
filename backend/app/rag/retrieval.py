"""Local persistent LangChain Qdrant hybrid retrieval."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import date, datetime
from threading import Lock
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Condition,
    FieldCondition,
    Filter,
    MatchValue,
    SparseVector,
)

from app.config import get_embedding_settings, get_qdrant_settings

from .cross_refs import expand_cross_references, expand_sibling_completions
from .query_rules import load_query_rules, requested_context
from .references import LegalReference, metadata_matches, parse_reference

logger = logging.getLogger(__name__)

_SANCTION_COMPLETION_RE = re.compile(
    r"(?:phạt\s+tiền|trừ\s+điểm|tước\s+quyền|tịch\s+thu|tạm\s+giữ)",
    re.IGNORECASE,
)


class OpenRouterEmbeddings(Embeddings):
    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        api_key: str,
        base_url: str,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        # A throttled provider must fail fast: retrieval falls back to the local
        # sparse index instead of blocking until the request deadline expires.
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout if timeout is not None else _EMBEDDING_TIMEOUT_SECONDS,
            max_retries=0 if max_retries is None else max_retries,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        segments: list[str] = []
        owners: list[list[int]] = []
        for text in texts:
            start = len(segments)
            segments.extend(text[index : index + 24000] for index in range(0, len(text), 24000))
            owners.append(list(range(start, len(segments))))
        response = self.client.embeddings.create(
            model=self.model,
            input=segments,
            dimensions=self.dimensions,
        )
        vectors = [item.embedding for item in response.data]
        return [
            [
                sum(vectors[index][dimension] for index in indices) / len(indices)
                for dimension in range(len(vectors[0]))
            ]
            for indices in owners
        ]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


_FAMILY_CONTEXT_RE = re.compile(
    r"(?:điều|chương|mục|tiêu đề|quy định|áp dụng|đối với)",
    re.IGNORECASE,
)


def _temporal_match(document: Document, effective_date: date | None) -> bool:
    if effective_date is None:
        return True
    metadata = _metadata(document)
    parsed: list[date | None] = []
    for key in ("effective_from", "effective_to"):
        value = metadata.get(key)
        if value in (None, ""):
            parsed.append(None)
            continue
        try:
            parsed.append(datetime.fromisoformat(str(value)).date())
        except (TypeError, ValueError):
            return False
    start, end = parsed
    return (start is None or start <= effective_date) and (end is None or effective_date < end)


class RetrievalProviderError(RuntimeError):
    """Raised when the configured retrieval provider cannot be used."""


_EMBEDDING_TIMEOUT_SECONDS = 8.0


def extract_reference(question: str) -> dict[str, str]:
    """Return the legacy mapping for an explicit article reference."""
    reference = parse_reference(question)
    if reference is None or not reference.article:
        return {}
    return reference.as_dict()


def _metadata(doc: Document) -> dict[str, Any]:
    return {str(key): value for key, value in doc.metadata.items()}


def _reference_match(doc: Document, reference: LegalReference | None) -> bool:
    return reference is None or metadata_matches(_metadata(doc), reference)


def _reference_score(doc: Document, reference: LegalReference | None) -> int:
    if not reference or not _reference_match(doc, reference):
        return 0
    score = 100
    if reference.clause:
        score += 10
    if reference.point:
        score += 10
    return score


def _reference_filter(reference: LegalReference | None) -> Filter | None:
    if not reference or not reference.article:
        return None
    conditions: list[Condition] = [
        FieldCondition(
            key="metadata.article",
            match=MatchValue(value=reference.article),
        )
    ]
    for key in ("clause", "point"):
        value = getattr(reference, key)
        if value:
            conditions.append(
                FieldCondition(
                    key=f"metadata.{key}",
                    match=MatchValue(value=value),
                )
            )
    return Filter(must=conditions)


def _payload_document(payload: Mapping[str, Any]) -> Document | None:
    """Convert a LangChain Qdrant payload into a Document."""
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = payload
    content = payload.get("page_content")
    if content is None:
        content = payload.get("text")
    if content is None:
        return None
    return Document(page_content=str(content), metadata=dict(metadata))


def _exact_qdrant_documents(store: Any, reference: LegalReference, limit: int) -> list[Document]:
    """Scroll Qdrant payloads for an explicit reference when vector hits miss."""
    reference_data = reference.as_dict()
    client = getattr(store, "client", None)
    collection = getattr(store, "collection_name", None)
    if client is None or not collection:
        return []

    structural: list[Condition] = []
    if reference.document_id:
        structural.append(
            FieldCondition(
                key="metadata.document_id",
                match=MatchValue(value=reference.document_id),
            )
        )
    elif reference.number:
        number_match = re.fullmatch(r"(?P<number>\d+)/(?P<year>\d{4})", reference.number)
        if number_match:
            structural.append(
                FieldCondition(
                    key="metadata.document_id",
                    match=MatchValue(
                        value=f"nd-{number_match.group('number')}-{number_match.group('year')}"
                    ),
                )
            )
    structural.extend(
        FieldCondition(
            key=f"metadata.{key}",
            match=MatchValue(value=value),
        )
        for key, value in reference_data.items()
        if key in {"article", "clause", "point"} and value
    )
    number = reference_data.get("number")
    number_match = re.fullmatch(r"(?P<number>\d+)/(?P<year>\d{4})", number) if number else None
    if number and not number_match:
        number_values = [number]
        alternate = number.replace("d", "đ") if "d" in number else number.replace("đ", "d")
        if alternate not in number_values:
            number_values.append(alternate)
        filters = [
            Filter(
                must=structural,
                should=[
                    FieldCondition(
                        key="metadata.document_number",
                        match=MatchValue(value=value),
                    )
                    for value in number_values
                ],
            )
        ]
    else:
        filters = [Filter(must=structural)]
    if not structural:
        return []

    documents: list[Document] = []
    seen: set[tuple[str, str]] = set()
    for query_filter in filters:
        try:
            points, _ = client.scroll(
                collection_name=collection,
                scroll_filter=query_filter,
                limit=min(max(limit * 3, limit), 64),
                with_payload=True,
            )
        except Exception:
            continue
        for point in points:
            payload = getattr(point, "payload", None)
            if not isinstance(payload, Mapping):
                continue
            document = _payload_document(payload)
            if document is None or not _reference_match(document, reference):
                continue
            key = (
                str(document.metadata.get("chunk_id", "")),
                document.page_content,
            )
            if key not in seen:
                seen.add(key)
                documents.append(document)
            if len(documents) >= limit:
                return documents
    return documents


_CONTEXT_ACTION_MARKERS = {
    "railway_crossing": ("đường ngang", "cầu chung", "đường sắt"),
}


def _normalized_action(value: object) -> str:
    return re.sub(r"[^\w]+", " ", str(value).casefold(), flags=re.UNICODE).strip()


def _action_matches(value: object, expected: str, context: str = "") -> bool:
    normalized = _normalized_action(value)
    if normalized == expected or (expected and expected in normalized):
        return True
    markers = _CONTEXT_ACTION_MARKERS.get(context, ())
    return bool(markers and "đèn đỏ" in normalized and any(item in normalized for item in markers))


def _document_action_match(document: Document, expected: str, context: str = "") -> bool:
    metadata = _metadata(document)
    return any(
        _action_matches(metadata.get(field, ""), expected, context)
        for field in ("normalized_action", "action", "violation")
    )


def _context_document_action_match(document: Document, expected: str, context: str) -> bool:
    normalized = " ".join(
        _normalized_action(_metadata(document).get(field, ""))
        for field in ("normalized_action", "action", "violation")
    )
    return "đèn đỏ" in normalized and any(
        marker in normalized for marker in _CONTEXT_ACTION_MARKERS.get(context, ())
    )


def _action_terms(question: str) -> tuple[str, ...]:
    """Return canonical action terms, longest and deterministic first."""
    normalized_question = _normalized_action(question)
    aliases = load_query_rules().get("action_aliases", {})
    terms = {
        _normalized_action(str(canonical))
        for alias, canonical in aliases.items()
        if _normalized_action(str(alias)) in normalized_question
    }
    return tuple(sorted((term for term in terms if term), key=lambda term: (-len(term), term)))


def _metadata_text_documents(
    store: Any,
    field: str,
    text: str,
    limit: int,
    *,
    context: str = "",
    effective_date: date | None = None,
    required_vehicle: str = "",
):
    client = getattr(store, "client", None)
    collection = getattr(store, "collection_name", None)
    normalized_text = _normalized_action(text)
    if client is None or not collection or not normalized_text:
        return []
    try:
        documents: list[Document] = []
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=collection,
                limit=256,
                offset=offset,
                with_payload=True,
            )
            documents.extend(
                document
                for point in points
                if isinstance((payload := getattr(point, "payload", None)), Mapping)
                and (document := _payload_document(payload)) is not None
                and _document_action_match(document, normalized_text, context)
                and _date_eligible(document.metadata, effective_date)
            )
            if offset is None or len(documents) >= limit:
                break
    except Exception:
        return []
    return documents[:limit]


def _date_eligible(metadata: Mapping[str, Any], effective_date: date | None) -> bool:
    if effective_date is None:
        return True
    for key in ("effective_from", "valid_from"):
        value = metadata.get(key)
        if value:
            try:
                if effective_date < date.fromisoformat(str(value)[:10]):
                    return False
            except ValueError:
                pass
            break
    for key in ("effective_to", "valid_to"):
        value = metadata.get(key)
        if value:
            try:
                if effective_date > date.fromisoformat(str(value)[:10]):
                    return False
            except ValueError:
                pass
            break
    return True


def _sibling_completion_documents(
    store: Any,
    original: Document,
    limit: int,
    effective_date: date | None = None,
) -> list[Document]:
    """Return bounded structural provision-family context for an original."""
    if limit < 1:
        return []
    metadata = _metadata(original)
    document_key = next(
        (
            key
            for key in ("document_id", "document_number", "document_name", "source_file")
            if str(metadata.get(key, "")).strip()
        ),
        "",
    )
    document_id = str(metadata.get(document_key, "")).strip()
    article = str(metadata.get("article", "")).strip()
    clause = str(metadata.get("clause", "")).strip()
    if not document_key or not document_id or not article:
        return []
    client = getattr(store, "client", None)
    collection = getattr(store, "collection_name", None)
    if client is None or not collection:
        return []
    must: list[Condition] = [
        FieldCondition(key=f"metadata.{document_key}", match=MatchValue(value=document_id)),
        FieldCondition(key="metadata.article", match=MatchValue(value=article)),
    ]
    if clause:
        must.append(FieldCondition(key="metadata.clause", match=MatchValue(value=clause)))
    try:
        points, _ = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(must=must),
            limit=min(max(limit * 8, 32), 128),
            with_payload=True,
        )
    except Exception:
        return []
    result: list[Document] = []
    seen = {_identity(original)}
    for point in points:
        payload = getattr(point, "payload", None)
        if not isinstance(payload, Mapping):
            continue
        document = _payload_document(payload)
        if document is None:
            continue
        candidate_metadata = _metadata(document)
        if (
            str(candidate_metadata.get(document_key, "")).strip() != document_id
            or str(candidate_metadata.get("article", "")).strip() != article
            or (clause and str(candidate_metadata.get("clause", "")).strip() != clause)
            or not _temporal_match(document, effective_date)
        ):
            continue
        if not (
            _SANCTION_COMPLETION_RE.search(document.page_content)
            or _FAMILY_CONTEXT_RE.search(document.page_content)
        ):
            continue
        identity = _identity(document)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(document)

    # The clause header carries the fine amount ("Phạt tiền từ ... đồng"), so it
    # must survive the limit even when other siblings match the context wording.
    result.sort(key=lambda doc: (bool(_metadata(doc).get("point")), _identity(doc)[0]))
    return result[:limit]


_sibling_completion_documents_impl = _sibling_completion_documents


def complete_family(
    store: Any,
    original: Document,
    *,
    limit: int = 2,
    effective_date: date | None = None,
) -> list[Document]:
    """Return bounded structural provision-family context for an original."""
    return _sibling_completion_documents_impl(store, original, limit, effective_date)


def _identity(document: Document) -> tuple[str, str]:
    metadata = _metadata(document)
    chunk_id = str(metadata.get("chunk_id", "")).strip()
    if chunk_id:
        return "chunk_id", chunk_id
    return str(metadata.get("source_file") or metadata.get("source") or ""), document.page_content


class Retriever:
    """Deep module over a persistent local Qdrant hybrid vector store."""

    def __init__(self, *, top_k: int = 8) -> None:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self.top_k = min(top_k, 50)
        self._store: Any = None
        self._client: Any = None
        self._sparse_embeddings: Any = None
        self._collection_name: str = "traffic_law"
        self._sparse_vector_name: str = "sparse"
        self._store_lock = Lock()

    def _store_for_query(self) -> Any:
        if self._store is not None:
            return self._store
        with self._store_lock:
            if self._store is not None:
                return self._store
            self._store = self._create_store()
            return self._store

    def _create_store(self, mode: Any | None = None) -> Any:
        try:
            qdrant = get_qdrant_settings()
            embedding = get_embedding_settings()
            if not embedding.openrouter_api_key:
                raise RetrievalProviderError("OPENROUTER_API_KEY is required for retrieval")
            dense = OpenRouterEmbeddings(
                model=embedding.model,
                dimensions=getattr(embedding, "dimensions", 768),
                api_key=embedding.openrouter_api_key,
                base_url=embedding.openrouter_base_url,
                timeout=getattr(embedding, "timeout_seconds", None),
                max_retries=getattr(embedding, "max_retries", None),
            )
            from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode

            sparse = FastEmbedSparse("Qdrant/bm25")
            client = (
                QdrantClient(url=qdrant.url, timeout=qdrant.timeout)
                if qdrant.url
                else QdrantClient(path=str(qdrant.path), timeout=qdrant.timeout)
            )
            store = QdrantVectorStore(
                client=client,
                collection_name=qdrant.collection,
                embedding=dense,
                sparse_embedding=sparse,
                retrieval_mode=RetrievalMode.HYBRID if mode is None else mode,
                vector_name="dense",
                sparse_vector_name="sparse",
            )
            self._client = client
            self._sparse_embeddings = sparse
            self._collection_name = qdrant.collection
            try:
                # Load the local BM25 model now so the fallback stays inside the
                # request deadline instead of paying the cold start there.
                sparse.embed_query("khởi động")
            except Exception:
                logger.warning("sparse warm-up failed", exc_info=True)
            return store
        except RetrievalProviderError:
            raise
        except Exception as exc:
            raise RetrievalProviderError("Qdrant or embedding provider is unavailable") from exc

    def _sparse_search(self, question: str, limit: int) -> list[Document]:
        """Query the same collection through its sparse BM25 vectors, no provider call."""
        self._store_for_query()
        if self._sparse_embeddings is None or self._client is None:
            return []
        vector = self._sparse_embeddings.embed_query(question)
        points = self._client.query_points(
            collection_name=self._collection_name,
            query=SparseVector(indices=list(vector.indices), values=list(vector.values)),
            using=self._sparse_vector_name,
            limit=max(limit * 3, limit),
            with_payload=True,
        ).points
        documents: list[Document] = []
        for point in points:
            payload = getattr(point, "payload", None)
            if isinstance(payload, Mapping) and (document := _payload_document(payload)):
                documents.append(document)
        return documents

    def _similarity_search(self, question: str, limit: int) -> list[Document]:
        """Search the hybrid index, degrading to the local sparse index when the provider fails."""
        store = self._store_for_query()
        try:
            return list(store.similarity_search(question, k=max(limit * 3, limit)))
        except Exception:
            logger.warning("dense retrieval failed, using the local sparse index", exc_info=True)
        try:
            return self._sparse_search(question, limit)
        except Exception:
            logger.warning("sparse retrieval failed as well", exc_info=True)
            return []

    def resolve_reference(
        self,
        reference: LegalReference,
        *,
        limit: int | None = None,
    ) -> list[Document]:
        """Resolve an explicit reference through exact metadata/Qdrant matching."""
        if not reference.article:
            return []
        store = self._store_for_query()
        documents = _exact_qdrant_documents(store, reference, limit or self.top_k)
        return [
            document for document in documents if metadata_matches(document.metadata, reference)
        ]

    def fetch_provisions(
        self,
        reference: LegalReference,
        *,
        question: str = "",
        limit: int = 12,
        effective_date: date | None = None,
    ) -> list[Document]:
        """Fetch provisions by exact payload coordinates, ranking bare references."""
        if limit < 1 or not (reference.article or reference.clause or reference.point):
            return []
        store = self._store_for_query()
        if reference.document_id:
            documents = _exact_qdrant_documents(store, reference, limit)
            documents = [doc for doc in documents if metadata_matches(doc.metadata, reference)]
        else:
            if not question:
                return []
            documents = _exact_qdrant_documents(store, reference, max(limit * 8, limit))
            documents = [doc for doc in documents if metadata_matches(doc.metadata, reference)]
            ranked = self._similarity_search(question, max(limit * 3, limit))
            rank = {_identity(doc): index for index, doc in enumerate(ranked)}
            documents.sort(key=lambda doc: (rank.get(_identity(doc), len(rank)), _identity(doc)))
        if effective_date:
            documents = [doc for doc in documents if _temporal_match(doc, effective_date)]
        return documents[:limit]

    def complete_family(
        self,
        document: Document,
        *,
        limit: int = 2,
        effective_date: date | None = None,
    ) -> list[Document]:
        """Return bounded sanction siblings from the same provision family."""
        return _sibling_completion_documents(
            self._store_for_query(), document, limit, effective_date
        )

    def retrieve(
        self,
        question: str,
        *,
        top_k: int | None = None,
        effective_date: date | None = None,
    ) -> list[Document]:
        limit = min(top_k or self.top_k, 50)
        if limit < 1:
            raise ValueError("top_k must be positive")
        from .references import extract_references

        references = extract_references(question)
        if references:
            canonical_references = [reference for reference in references if reference.document_id]
            if len(canonical_references) > limit:
                raise RetrievalProviderError("top_k is too small for all explicit references")
            exact: list[Document] = []
            seen: set[tuple[str, str]] = set()
            missing = False
            for reference in references:
                matches = self.resolve_reference(reference, limit=limit)
                if effective_date:
                    matches = [
                        document
                        for document in matches
                        if _temporal_match(document, effective_date)
                    ]
                representative = next(
                    (document for document in matches if _identity(document) not in seen),
                    None,
                )
                if representative is None:
                    missing = True
                    continue
                exact.append(representative)
                seen.add(_identity(representative))
            if missing and not exact:
                # An explicit reference that cannot be resolved exactly must
                # degrade to hybrid search instead of killing retrieval: the
                # caller still enforces its own reference coverage check.
                exact = []
            if exact:
                if len(exact) < limit:
                    for sibling in self.complete_family(
                        exact[0], limit=limit - len(exact), effective_date=effective_date
                    ):
                        if _identity(sibling) not in seen:
                            exact.append(sibling)
                            seen.add(_identity(sibling))
                            if len(exact) >= limit:
                                break
                return exact[:limit]

        store = self._store_for_query()
        documents = self._similarity_search(question, limit)
        action_terms = _action_terms(question)
        if action_terms:
            action_documents: list[Document] = []
            for action_term in action_terms:
                action_documents.extend(
                    _metadata_text_documents(
                        store,
                        "normalized_action",
                        action_term,
                        max(limit * 2, limit),
                        context=requested_context(question),
                        effective_date=effective_date,
                    )
                )
            existing = {_identity(doc) for doc in action_documents}
            documents = [
                *action_documents,
                *[doc for doc in documents if _identity(doc) not in existing],
            ]
        if not documents and action_terms:
            raise RetrievalProviderError("retrieval provider returned no documents")
        context = requested_context(question)
        canonical_actions = tuple(_normalized_action(term) for term in action_terms if term)
        ranked = sorted(
            enumerate(documents),
            key=lambda item: (
                -(
                    4
                    if _CONTEXT_ACTION_MARKERS.get(context)
                    and any(
                        _context_document_action_match(item[1], action, context)
                        for action in canonical_actions
                    )
                    else (
                        3
                        if any(
                            _normalized_action(_metadata(item[1]).get("normalized_action", ""))
                            == action
                            for action in canonical_actions
                        )
                        else 1
                    )
                ),
                item[0],
            ),
        )
        originals = [doc for _, doc in ranked[:limit]]
        with_siblings = expand_sibling_completions(
            originals,
            lambda document, **kwargs: _sibling_completion_documents(
                store, document, kwargs.get("limit", 2), effective_date
            ),
            max_documents=limit,
            max_siblings=2,
        )
        expanded = expand_cross_references(
            with_siblings, self.resolve_reference, max_documents=limit
        )
        return expanded[:limit]


__all__ = ["Retriever", "RetrievalProviderError", "extract_reference", "complete_family"]
