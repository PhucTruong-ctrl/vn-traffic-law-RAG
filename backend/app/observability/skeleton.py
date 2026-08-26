"""Runnable skeleton of the VNLaw ``legal_query`` trace.

Emits a single ``legal_query`` trace with nested spans (``analyze_query``,
``dense_retrieval``, ``generate``) to exercise the Langfuse instrumentation,
then flushes so the trace is delivered before the process exits.

Usage::

    uv run python -m app.observability.skeleton "mức phạt vượt đèn đỏ năm 2024?"

Runs fully offline when ``LANGFUSE_ENABLED=false`` (no-op stub path).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.config import get_settings
from app.observability.langfuse_client import build_prompt, get_langfuse, trace_legal_query

# Model ids used by the skeleton spans (doc 07 §7.3.3).
GENERATION_MODEL = "gemini-3.5-flash"
EMBEDDING_MODEL = "gemini-embedding-2"

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _fallback_dir() -> Path:
    """Prompt fallback dir: configured path when present, else the repo copy."""
    configured = Path(get_settings().fallback_prompts_dir)
    if configured.is_dir():
        return configured
    return _REPO_ROOT / "prompts" / "fallback"


def run_legal_query_trace(query: str) -> str:
    """Run a full ``legal_query`` trace for ``query`` and return the trace id.

    Off the correctness path (doc 00 §4.11): when Langfuse is disabled every
    call becomes a no-op and the run still completes without network access.
    """
    settings = get_settings()
    trace_id = uuid.uuid4().hex
    user_id = "skeleton"

    root = trace_legal_query(query=query, trace_id=trace_id, user_id=user_id)

    # analyze_query: query understanding summary.
    analyze = root.start_observation(
        as_type="span",
        name="analyze_query",
        input={"query": query},
        metadata={"prompt_source": settings.prompt_source},
    )
    analyze.update(
        output={"intent": "legal_penalty_query", "extracted_entities": ["đèn đỏ", "2024"]}
    )
    analyze.end()

    # dense_retrieval: top-k hit summary, not full document content.
    dense = root.start_observation(
        as_type="span",
        name="dense_retrieval",
        input={"query": query, "top_k": 8},
        metadata={"embedding_model": EMBEDDING_MODEL, "retriever": "qdrant_dense"},
    )
    dense.update(output={"hit_count": 8, "top_hit_ids": ["c001", "c002", "c003"]})
    dense.end()

    # generate: LLM call with model_id and pinned fallback prompt metadata.
    generator_prompt = build_prompt(
        name="legal-generator-v1", fallback_path=_fallback_dir() / "generator.yaml"
    )
    generation = root.start_observation(
        name="generate",
        as_type="generation",
        model=GENERATION_MODEL,
        input={"query": query},
        metadata={
            "prompt_source": generator_prompt.source,
            "prompt_version": settings.fallback_prompt_version_generator
            or generator_prompt.version,
            "prompt_hash": generator_prompt.prompt_hash,
        },
    )
    generation.update(
        output={
            "answer_summary": "Mức phạt vượt đèn đỏ năm 2024 quy định tại "
            "Nghị định 168/2024/NĐ-CP (phạt tiền, tước GPLX).",
            "claim_count": 3,
        },
        usage_details={"input": 412, "output": 386},
    )
    generation.end()

    root.update(output={"status": "completed", "claim_count": 3})
    root.end()

    get_langfuse().flush()
    return trace_id


if __name__ == "__main__":
    import sys

    question = sys.argv[1] if len(sys.argv) > 1 else "mức phạt vượt đèn đỏ năm 2024?"
    trace_id = run_legal_query_trace(question)
    print(f"trace_id={trace_id}")
