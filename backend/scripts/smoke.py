"""Exercise real Qdrant HYBRID retrieval and OpenRouter generation."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # noqa: E402
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode  # noqa: E402

from app.config import (  # noqa: E402
    get_embedding_settings,
    get_generation_settings,
    get_qdrant_settings,
)

QUESTIONS = (
    "Người điều khiển xe máy phải đội mũ bảo hiểm như thế nào?",
    "Mức phạt khi vượt đèn đỏ đối với ô tô là bao nhiêu?",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    qdrant, embedding, generation = (
        get_qdrant_settings(),
        get_embedding_settings(),
        get_generation_settings(),
    )
    if not generation.openrouter_api_key or not embedding.openrouter_api_key:
        raise SystemExit("smoke requires OPENROUTER_API_KEY for embeddings and generation")
    try:
        dense = OpenAIEmbeddings(
            model=embedding.model,
            api_key=embedding.openrouter_api_key,
            base_url=embedding.openrouter_base_url,
        )
        store = QdrantVectorStore.from_existing_collection(
            collection_name=qdrant.collection,
            embedding=dense,
            sparse_embedding=FastEmbedSparse("Qdrant/bm25"),
            retrieval_mode=RetrievalMode.HYBRID,
            url=qdrant.url,
            api_key=qdrant.api_key or None,
        )
        llm = ChatOpenAI(
            model=generation.model,
            api_key=generation.openrouter_api_key,
            base_url=generation.openrouter_base_url,
        )
        for question in QUESTIONS:
            started = time.perf_counter()
            hits = store.similarity_search_with_score(question, k=args.top_k)
            context = "\n\n".join(doc.page_content for doc, _ in hits)
            answer = llm.invoke(
                "Chỉ dựa trên ngữ cảnh pháp luật sau đây để trả lời bằng tiếng Việt.\n"
                f"{context}\n\nCâu hỏi: {question}"
            ).content
            print(
                f"QUESTION: {question}\nHITS: {len(hits)}\nANSWER: {answer}\n"
                f"LATENCY_MS: {(time.perf_counter() - started) * 1000:.1f}\n"
            )
    except Exception as exc:
        raise SystemExit(f"smoke failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
