"""Listing 5.3: a RAG pipeline whose worker-pool spans stay in one trace."""

from __future__ import annotations

from aiobs import Layer, Pillar
from chapters.registry import example

from ._rag_shared import run_rag_pipeline


@example(
    chapter=5,
    key="rag_pipeline_traced",
    title="Trace a RAG reranker across a thread pool",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="5.3",
)
def rag_pipeline_traced() -> dict:
    """Listings 5.3 and 5.4 with the context-propagation fix applied.

    The interesting part is not that the pipeline reranks documents; it is
    that ``rag.rerank`` executes on a worker thread without becoming an
    orphaned root span. Capturing the current OTel context before submit and
    re-attaching it in the worker keeps the trace tree honest.
    """

    return run_rag_pipeline(propagate_context=True)
