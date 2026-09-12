"""Create a fresh Qdrant HYBRID index from canonical legal JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "backend"))
from langchain_core.documents import Document  # noqa: E402
from langchain_openai import OpenAIEmbeddings  # noqa: E402
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode  # noqa: E402

from app.config import get_embedding_settings, get_qdrant_settings  # noqa: E402


def _load(path: Path) -> list[Document]:
    try:
        return [
            Document(page_content=item["page_content"], metadata=item["metadata"])
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
            for item in [json.loads(line)]
        ]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(f"invalid chunks JSONL: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=_ROOT / "data/processed/chunks.jsonl")
    parser.add_argument("--collection", default=None)
    args = parser.parse_args(argv)
    if not args.chunks.is_file():
        raise SystemExit(f"chunks file not found: {args.chunks}")
    documents = _load(args.chunks)
    if not documents:
        raise SystemExit("chunks file contains no documents")
    qdrant = get_qdrant_settings()
    embedding = get_embedding_settings()
    collection = args.collection if args.collection is not None else qdrant.collection
    store = None
    try:
        qdrant.path.mkdir(parents=True, exist_ok=True)
        dense = OpenAIEmbeddings(
            model=embedding.model,
            dimensions=embedding.dimensions,
            api_key=embedding.openrouter_api_key or None,
            base_url=embedding.openrouter_base_url,
        )
        sparse = FastEmbedSparse("Qdrant/bm25")
        client_options = (
            {"url": qdrant.url, "timeout": qdrant.timeout}
            if qdrant.url
            else {"path": str(qdrant.path.resolve()), "timeout": qdrant.timeout}
        )

        store = QdrantVectorStore.construct_instance(
            embedding=dense,
            sparse_embedding=sparse,
            retrieval_mode=RetrievalMode.HYBRID,
            collection_name=collection,
            vector_name="dense",
            sparse_vector_name="sparse",
            client_options=client_options,
            force_recreate=True,
        )
        store.add_documents(documents)
        info = store.client.get_collection(collection)
        if info.points_count <= 0:
            raise RuntimeError(f"collection {collection!r} contains no points after indexing")
        print(f"indexed {len(documents)} chunks in fresh HYBRID collection {store.collection_name}")
    except Exception as exc:
        raise SystemExit(f"Qdrant HYBRID indexing failed: {exc}") from exc
    finally:
        if store is not None:
            store.client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
