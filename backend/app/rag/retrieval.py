"""Local persistent LangChain Qdrant hybrid retrieval."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from threading import Lock
from typing import Any

from langchain_core.documents import Document
from pydantic import SecretStr
from qdrant_client import QdrantClient
from qdrant_client.models import Condition, FieldCondition, Filter, MatchValue

from app.config import get_embedding_settings, get_qdrant_settings

from .cross_refs import expand_cross_references, expand_sibling_completions
from .references import LegalReference, metadata_matches, parse_reference

_SANCTION_COMPLETION_RE = re.compile(
    r"(?:phạt\s+tiền|trừ\s+điểm|tước\s+quyền|tịch\s+thu|tạm\s+giữ)",
    re.IGNORECASE,
)
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
    structural.extend(
        FieldCondition(
            key=f"metadata.{key}",
            match=MatchValue(value=reference_data[key]),
        )
        for key in ("article", "clause", "point")
        if reference_data.get(key)
    )
    number = reference_data.get("number")
    if number:
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
                limit=max(limit * 3, limit),
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
    if normalized == expected:
        return True
    markers = _CONTEXT_ACTION_MARKERS.get(context, ())
    return bool(markers and "đèn đỏ" in normalized and any(item in normalized for item in markers))


def _metadata_text_documents(
    store: Any, field: str, text: str, limit: int, *, context: str = ""
) -> list[Document]:
    client = getattr(store, "client", None)
    collection = getattr(store, "collection_name", None)
    normalized_text = _normalized_action(text)
    if client is None or not collection or not normalized_text:
        return []
    documents: list[Document] = []
    offset: Any = None
    try:
        while len(documents) < limit:
            points, next_offset = client.scroll(
                collection_name=collection,
                offset=offset,
                limit=max(limit * 4, 64),
                with_payload=True,
            )
            documents.extend(
                document
                for point in points
                if isinstance((payload := getattr(point, "payload", None)), Mapping)
                and (document := _payload_document(payload)) is not None
                and _action_matches(document.metadata.get(field, ""), normalized_text, context)
            )
            if next_offset is None or next_offset == offset:
                break
            offset = next_offset
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
            limit=max(limit * 4, limit),
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
        if len(result) >= limit:
            break
    return result


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
        self.top_k = top_k
        self._store: Any = None
        self._store_lock = Lock()

    def _store_for_query(self) -> Any:
        if self._store is not None:
            return self._store
        with self._store_lock:
            if self._store is not None:
                return self._store
            return self._create_store()

    def _create_store(self) -> Any:
        """Create the configured hybrid store exactly once."""
        try:
            from langchain_openai import OpenAIEmbeddings
            from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
        except ImportError as exc:
            raise RetrievalProviderError(
                "Retrieval integration is not installed; run `uv sync --project backend`"
            ) from exc

        try:
            qdrant = get_qdrant_settings()
            embedding = get_embedding_settings()
            if not embedding.openrouter_api_key:
                raise RetrievalProviderError("OPENROUTER_API_KEY is required for retrieval")
            dense = OpenAIEmbeddings(
                model=embedding.model,
                dimensions=getattr(embedding, "dimensions", 768),
                api_key=SecretStr(embedding.openrouter_api_key),
                base_url=embedding.openrouter_base_url,
            )
            sparse = FastEmbedSparse("Qdrant/bm25")
            client = (
                QdrantClient(url=qdrant.url, timeout=qdrant.timeout)
                if qdrant.url
                else QdrantClient(path=str(qdrant.path), timeout=qdrant.timeout)
            )
            self._store = QdrantVectorStore(
                client=client,
                collection_name=qdrant.collection,
                embedding=dense,
                sparse_embedding=sparse,
                retrieval_mode=RetrievalMode.HYBRID,
                vector_name="dense",
                sparse_vector_name="sparse",
            )
            if hasattr(self._store, "client"):
                self._store.client.get_collection(qdrant.collection)
            return self._store
        except RetrievalProviderError:
            raise
        except Exception as exc:
            raise RetrievalProviderError("Qdrant or embedding provider is unavailable") from exc

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
        limit = top_k or self.top_k
        if limit < 1:
            raise ValueError("top_k must be positive")
        from .references import extract_references

        references = extract_references(question)
        if references:
            canonical_references = [reference for reference in references if reference.document_id]
            if canonical_references and len(canonical_references) > limit:
                raise RetrievalProviderError("top_k is too small for all explicit references")
            exact: list[Document] = []
            seen: set[tuple[str, str]] = set()
            for reference in references:
                matches = self.resolve_reference(reference, limit=limit)
                if effective_date:
                    matches = [
                        document
                        for document in matches
                        if _temporal_match(document, effective_date)
                    ]
                if not matches:
                    continue
                for document in matches:
                    identity = _identity(document)
                    if identity not in seen:
                        exact.append(document)
                        seen.add(identity)
                        break
            if canonical_references and len(exact) < len(canonical_references):
                return []
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

        query = question
        if effective_date:
            query = f"{query} (hiệu lực {effective_date.isoformat()})"
        try:
            store = self._store_for_query()
            documents = store.similarity_search(query, k=max(limit * 3, limit))
            documents = [
                document for document in documents if _temporal_match(document, effective_date)
            ]
        except RetrievalProviderError:
            raise
        except Exception as exc:
            raise RetrievalProviderError("hybrid retrieval provider is unavailable") from exc
        if ";" in question:
            from .query_rules import requested_context

            expanded_terms = [part.strip() for part in question.split(";")[1:] if part.strip()]
            normalized_action = max(expanded_terms, key=len, default="")
            action_documents = _metadata_text_documents(
                store,
                "normalized_action",
                normalized_action,
                max(limit * 2, limit),
                context=requested_context(question),
            )
            existing = {_identity(doc) for doc in action_documents}
            documents = [
                *action_documents,
                *[doc for doc in documents if _identity(doc) not in existing],
            ]
        ranked = sorted(
            enumerate(documents),
            key=lambda item: (-_reference_score(item[1], None), item[0]),
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
