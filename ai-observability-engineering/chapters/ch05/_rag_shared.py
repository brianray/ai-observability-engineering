"""Shared helpers for the Chapter 5 RAG tracing examples."""

from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor

from opentelemetry import context, trace
from opentelemetry.trace import SpanKind

from aiobs import Aiobs, ChatResponse, Layer, MockProvider, Operation, Pillar, get_tracer, llm_span
from aiobs.instrument import set_llm_attributes

QUERY = "Which refund extension policy applies to discontinued products?"
CORPUS = (
    "Refund extensions apply only to active products purchased after March 2025.",
    "Discontinued products are not eligible for any refund extension.",
    "Warranty claims are handled separately from refund requests.",
    "Manual review escalations go to analyst@example.com with ticket 123-45-6789.",
)


def vector_store(query: str) -> list[str]:
    """Return deterministic retrieval candidates seeded by the query text.

    The retriever uses overlap as the primary score and a query-specific hash
    only as a stable tiebreaker, so the example stays reproducible offline.
    """

    query_terms = set(query.lower().split())
    ranked = sorted(
        CORPUS,
        key=lambda doc: (
            -len(query_terms & set(doc.lower().split())),
            hashlib.sha256(f"{query}:{doc}".encode()).hexdigest(),
        ),
    )
    return list(ranked[:3])


def cross_encoder_rerank(query: str, docs: list[str]) -> list[str]:
    """Deterministic stand-in for a reranker.

    Listing 5.3 is about span parenting through a worker pool, not model
    quality, so this uses a stable lexical score instead of a real model.
    """

    query_terms = set(query.lower().split())
    return sorted(
        docs,
        key=lambda doc: (
            -len(query_terms & set(doc.lower().split())),
            -len(doc),
            doc,
        ),
    )


def build_prompt(query: str, docs: list[str]) -> str:
    context_block = "\n".join(f"- {doc}" for doc in docs)
    return (
        "Answer using only the retrieved context.\n"
        f"Question: {query}\n"
        f"Context:\n{context_block}"
    )


def llm(prompt: str, provider: MockProvider) -> ChatResponse:
    """Use the seeded mock provider and append predictable PII for redaction."""

    reply = provider.chat(prompt)
    answer = (
        f"{reply.text} Contact analyst@example.com or 123-45-6789 if the case "
        "needs manual review."
    )
    return ChatResponse(
        text=answer,
        model=reply.model,
        provider=reply.provider,
        input_tokens=reply.input_tokens,
        output_tokens=provider.count_tokens(answer),
        finish_reason=reply.finish_reason,
        response_id=reply.response_id,
        eval_scores=reply.eval_scores,
        failure_mode=reply.failure_mode,
    )


def redact_pii(text: str) -> str:
    """Redact obvious email and SSN-like strings for the post-processing span."""

    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]{2,}", "[REDACTED_EMAIL]", text)
    return re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", text)


def rerank_in_pool(
    tracer: trace.Tracer,
    query: str,
    docs: list[str],
    *,
    propagate_context: bool,
) -> list[str]:
    """Run reranking in a thread pool, with optional context propagation."""

    active_ctx = context.get_current() if propagate_context else None

    def worker() -> list[str]:
        token = context.attach(active_ctx) if active_ctx is not None else None
        try:
            with tracer.start_as_current_span("rag.rerank") as span:
                span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
                span.set_attribute(Aiobs.LAYER, Layer.DATA_AND_RETRIEVAL.value)
                span.set_attribute("aiobs.retrieval.candidate_count", len(docs))
                return cross_encoder_rerank(query, docs)
        finally:
            if token is not None:
                context.detach(token)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(worker).result()


def run_rag_pipeline(*, propagate_context: bool) -> dict:
    """Listings 5.3 and 5.4: same pipeline, different context propagation."""

    tracer = get_tracer(__name__)
    provider = MockProvider()

    with tracer.start_as_current_span("rag.request", kind=SpanKind.SERVER) as root:
        root.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        root.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)

        with tracer.start_as_current_span("rag.retrieve") as span:
            span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
            span.set_attribute(Aiobs.LAYER, Layer.DATA_AND_RETRIEVAL.value)
            retrieved_docs = vector_store(QUERY)
            reranked_docs = rerank_in_pool(
                tracer,
                QUERY,
                retrieved_docs,
                propagate_context=propagate_context,
            )
            span.set_attribute("aiobs.retrieval.candidate_count", len(retrieved_docs))

        with llm_span(
            name="rag.generate",
            provider=provider.name,
            model=provider.model,
            operation=Operation.CHAT,
            pillar=Pillar.PERFORMANCE,
            layer=Layer.MODEL_AND_INFERENCE,
            tracer_name=__name__,
        ) as span:
            prompt = build_prompt(QUERY, reranked_docs)
            reply = llm(prompt, provider)
            set_llm_attributes(
                span,
                provider=provider.name,
                model=reply.model,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                finish_reason=reply.finish_reason,
                response_id=reply.response_id,
            )

        with tracer.start_as_current_span("rag.post_process") as span:
            span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
            span.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
            redacted = redact_pii(reply.text)
            span.set_attribute("aiobs.post_process.redactions", int(redacted != reply.text))

    return {
        "query": QUERY,
        "retrieved_docs": retrieved_docs,
        "reranked_docs": reranked_docs,
        "generated_answer": reply.text,
        "redacted_answer": redacted,
    }
