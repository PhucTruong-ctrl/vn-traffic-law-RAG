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

from app.config import (  # noqa: E402
    get_embedding_settings,
    get_qdrant_settings,
)


def _setting(settings: object, name: str, default: object) -> object:
    """Read optional embedding settings from lightweight test doubles."""
    return getattr(settings, name, default)


_DEFAULT_EMBEDDING = get_embedding_settings()


def _embedding_kwargs(settings: object) -> dict[str, object]:
    return {
        "model": _setting(settings, "model", _DEFAULT_EMBEDDING.model),
        "dimensions": _setting(settings, "dimensions", _DEFAULT_EMBEDDING.dimensions),
        "api_key": _setting(settings, "openrouter_api_key", _DEFAULT_EMBEDDING.openrouter_api_key)
        or None,
        "base_url": _setting(
            settings, "openrouter_base_url", _DEFAULT_EMBEDDING.openrouter_base_url
        ),
    }


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
    parser.add_argument(
        "--force-recreate",
        action="store_true",
        help="allow recreation of an explicitly named collection",
    )
    args = parser.parse_args(argv)
    if args.force_recreate and args.collection is None:
        raise SystemExit("--force-recreate requires explicit --collection")
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
        dense = OpenAIEmbeddings(**_embedding_kwargs(embedding))
        sparse = FastEmbedSparse("Qdrant/bm25")
        client_options = (
            {
                "url": qdrant.url,
                "timeout": qdrant.timeout,
                **({"api_key": qdrant.api_key} if qdrant.api_key else {}),
            }
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
            force_recreate=args.force_recreate,
        )
        store.add_documents(documents)
        info = store.client.get_collection(collection)
        if info.points_count != len(documents):
            raise RuntimeError(
                f"collection {collection!r} has expected {len(documents)} points, "
                f"found {info.points_count}"
            )
        print(f"indexed {len(documents)} chunks in HYBRID collection {store.collection_name}")
    except Exception as exc:
        raise SystemExit(f"Qdrant HYBRID indexing failed: {exc}") from exc
    finally:
        if store is not None:
            store.client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
