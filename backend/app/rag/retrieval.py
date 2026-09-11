"""Local persistent LangChain Qdrant hybrid retrieval."""

import re
import unicodedata
from collections.abc import Mapping
from datetime import date
from typing import Any

from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import get_embedding_settings, get_qdrant_settings

_REFERENCE_RE = re.compile(
    r"(?:(?:điểm\s+(?P<point>[a-zđ])\s+)?"
    r"(?:khoản\s+(?P<clause>\d+)\s+)?điều\s+(?P<article>\d+)"
    r"(?:\s+(?:của\s+)?(?P<kind>nghị\s+định|thông\s+tư)\s*"
    r"(?:số\s+)?(?P<number>\d+(?:\s*/\s*\d{4})?(?:\s*/\s*[a-zđ0-9-]+)?))?)",
    re.IGNORECASE,
)

_DOCUMENT_NUMBER_RE = re.compile(
    r"(?P<number>\d+\s*/\s*\d{4}(?:\s*/\s*[a-zđ0-9-]+)?)",
    re.IGNORECASE,
)


def _normalize_document_number(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    normalized = normalized.replace("\u0111", "d")
    return re.sub(r"\s+", "", normalized)


def _normalize_metadata_number(value: Any) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    match = _DOCUMENT_NUMBER_RE.search(value)
    return _normalize_document_number(match.group("number") if match else value)


class RetrievalProviderError(RuntimeError):
    """Raised when the configured Qdrant or embedding provider is unavailable."""


def extract_reference(question: str) -> dict[str, str]:
    match = _REFERENCE_RE.search(question)
    if not match:
        return {}
    reference = {key: value.strip() for key, value in match.groupdict().items() if value}
    if "number" in reference:
        reference["number"] = _normalize_document_number(reference["number"])
    for key in ("point", "kind"):
        if key in reference:
            reference[key] = reference[key].casefold()
    return reference


def _metadata(doc: Document) -> dict[str, Any]:
    return {str(key): value for key, value in doc.metadata.items()}


def _reference_match(doc: Document, reference: Mapping[str, str]) -> bool:
    if not reference:
        return True
    metadata = _metadata(doc)
    article = str(metadata.get("article", "")).strip()
    if article != reference.get("article", article):
        return False
    expected_number = reference.get("number")
    if expected_number:
        metadata_number = _normalize_metadata_number(
            metadata.get("document_number") or metadata.get("document_name")
        )
        if metadata_number != expected_number:
            return False
    clause = reference.get("clause")
    if clause and str(metadata.get("clause", "")).strip() != clause:
        return False
    point = reference.get("point")
    return not point or str(metadata.get("point", "")).strip().casefold() == point


def _reference_score(doc: Document, reference: Mapping[str, str]) -> int:
    if not reference or not _reference_match(doc, reference):
        return 0
    score = 100
    if reference.get("clause"):
        score += 10
    if reference.get("point"):
        score += 10
    return score


def _reference_filter(reference: Mapping[str, str]) -> Filter | None:
    if not reference:
        return None
    conditions = [
        FieldCondition(
            key="metadata.article",
            match=MatchValue(value=reference["article"]),
        )
    ]
    for key in ("clause", "point"):
        value = reference.get(key)
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


def _exact_qdrant_documents(store: Any, reference: Mapping[str, str], limit: int) -> list[Document]:
    """Scroll Qdrant payloads for an explicit reference when vector hits miss."""
    client = getattr(store, "client", None)
    collection = getattr(store, "collection_name", None)
    if client is None or not collection:
        return []

    structural = [
        FieldCondition(
            key=f"metadata.{key}",
            match=MatchValue(value=reference[key]),
        )
        for key in ("article", "clause", "point")
        if reference.get(key)
    ]
    number = reference.get("number")
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


class Retriever:
    """Deep module over a persistent local Qdrant hybrid vector store."""

    def __init__(self, *, top_k: int = 8) -> None:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self.top_k = top_k
        self._store: Any = None

    def _store_for_query(self) -> Any:
        if self._store is not None:
            return self._store
        try:
            from langchain_openai import OpenAIEmbeddings
            from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode

            qdrant = get_qdrant_settings()
            embedding = get_embedding_settings()

            dense = OpenAIEmbeddings(
                model=embedding.model,
                dimensions=768,
                api_key=embedding.openrouter_api_key,
                base_url=embedding.openrouter_base_url,
            )
            sparse = FastEmbedSparse("Qdrant/bm25")
            client = QdrantClient(path=str(qdrant.path))
            self._store = QdrantVectorStore(
                client=client,
                collection_name=qdrant.collection,
                embedding=dense,
                sparse_embedding=sparse,
                retrieval_mode=RetrievalMode.HYBRID,
                vector_name="dense",
                sparse_vector_name="sparse",
            )
            return self._store
        except RetrievalProviderError:
            raise
        except Exception as exc:
            raise RetrievalProviderError("hybrid retrieval provider is unavailable") from exc

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
        reference = extract_reference(question)
        query = question
        if effective_date:
            query = f"{query} (hiệu lực {effective_date.isoformat()})"
        query_filter = _reference_filter(reference)
        try:
            store = self._store_for_query()
            if query_filter:
                documents = store.similarity_search(
                    query,
                    k=max(limit * 3, limit),
                    filter=query_filter,
                )
            else:
                documents = store.similarity_search(query, k=max(limit * 3, limit))
        except RetrievalProviderError:
            raise
        except Exception as exc:
            raise RetrievalProviderError("hybrid retrieval provider is unavailable") from exc
        ranked = sorted(
            enumerate(documents),
            key=lambda item: (-_reference_score(item[1], reference), item[0]),
        )
        if reference:
            ranked = [item for item in ranked if _reference_match(item[1], reference)]
            if len(ranked) < limit:
                exact_documents = _exact_qdrant_documents(store, reference, limit)
                existing = {
                    (
                        str(doc.metadata.get("chunk_id", "")),
                        doc.page_content,
                    )
                    for _, doc in ranked
                }
                for document in exact_documents:
                    key = (
                        str(document.metadata.get("chunk_id", "")),
                        document.page_content,
                    )
                    if key not in existing:
                        ranked.append((len(ranked), document))
                        existing.add(key)
                    if len(ranked) >= limit:
                        break
        return [doc for _, doc in ranked[:limit]]


__all__ = ["Retriever", "RetrievalProviderError", "extract_reference"]
