"""Listing 5.4: the same RAG pipeline with the classic orphan-span bug."""

from __future__ import annotations

from aiobs import Layer, Pillar
from chapters.registry import example

from ._rag_shared import run_rag_pipeline


@example(
    chapter=5,
    key="rag_pipeline_broken",
    title="A thread-pool reranker that drops trace context",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="5.4",
    demonstrates_failure=True,
)
def rag_pipeline_broken() -> dict:
    """Exercise 5.2: reproduce the orphaned rerank span on purpose.

    The business logic is identical to Listing 5.3. The only difference is
    that the worker thread starts its span without the submitting thread's
    context attached, so ``rag.rerank`` becomes a new trace root.
    """

    return run_rag_pipeline(propagate_context=False)
