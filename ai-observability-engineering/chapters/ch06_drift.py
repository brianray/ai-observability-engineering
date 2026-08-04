"""Chapter 6: Drift Detection and Behavioral Stability."""

from __future__ import annotations

import random

from aiobs import Aiobs, Layer, MockProvider, Pillar, detect_drift, get_tracer
from aiobs.evals import default_suite

from .registry import example


@example(
    chapter=6,
    key="output_drift_psi",
    title="Detecting output drift with PSI and KS",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="6.4",
)
def output_drift_psi() -> dict:
    """The same detector run against a stable window and a shifted one.

    Neither estimator says the system is broken. Both say the
    distribution moved, which is the only thing a drift signal can
    honestly tell you.
    """
    tracer = get_tracer(__name__)
    rng = random.Random(7)
    reference = [rng.gauss(0.9, 0.05) for _ in range(400)]
    stable = [rng.gauss(0.9, 0.05) for _ in range(400)]
    shifted = [rng.gauss(0.6, 0.12) for _ in range(400)]

    results = {}
    with tracer.start_as_current_span("drift.evaluate") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        span.set_attribute(Aiobs.LAYER, Layer.MODEL_AND_INFERENCE.value)
        for method in ("psi", "ks"):
            stable_result = detect_drift(method, reference, stable)
            shifted_result = detect_drift(method, reference, shifted)
            results[method] = {
                "stable": {"score": stable_result.score, "verdict": stable_result.verdict},
                "shifted": {"score": shifted_result.score, "verdict": shifted_result.verdict},
            }
            span.set_attribute(f"aiobs.drift.{method}_stable", stable_result.score)
            span.set_attribute(f"aiobs.drift.{method}_shifted", shifted_result.score)
        span.set_attribute(Aiobs.DRIFT_METHOD, "psi,ks")

    return {
        "results": results,
        "both_agree": all(r["shifted"]["verdict"] != "stable" for r in results.values()),
    }


@example(
    chapter=6,
    key="retrieval_drift_incident",
    title="A document update that silently breaks grounding",
    pillar=Pillar.RESPONSIBILITY,
    layer=Layer.DATA_AND_RETRIEVAL,
    demonstrates_failure=True,
)
def retrieval_drift_incident() -> dict:
    """Chapter 1's case study, reproduced.

    Latency and uptime never move. Groundedness does, six weeks before
    anyone notices, which is exactly the window a drift monitor closes.
    """
    tracer = get_tracer(__name__)
    rng = random.Random(11)
    provider = MockProvider()
    suite = default_suite()

    corpus = [
        "Refund extensions apply only to active products purchased after March 2025",
        "Discontinued products are not eligible for a refund extension",
        "Warranty claims are handled separately from refund requests",
    ]

    def window(wrong_document_rate: float) -> list[float]:
        """Groundedness over 60 answers at a given retrieval error rate.

        Degradation is modeled the way it actually happens: retrieval
        starts returning a document that is topically adjacent but wrong,
        and the model answers fluently from it.
        """
        scores = []
        for i in range(60):
            correct = corpus[i % len(corpus)]
            retrieved = (
                corpus[(i + 1) % len(corpus)]
                if rng.random() < wrong_document_rate
                else correct
            )
            question = f"question {i} about refunds"
            reply = provider.chat(question, context=retrieved)
            scores.append(
                suite.scores(reply.text, context=correct, prompt=question)["groundedness"]
            )
        return scores

    before = window(wrong_document_rate=0.05)
    after = window(wrong_document_rate=0.60)

    result = detect_drift("psi", before, after)
    with tracer.start_as_current_span("retrieval.drift_check") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.RESPONSIBILITY.value)
        span.set_attribute(Aiobs.LAYER, Layer.DATA_AND_RETRIEVAL.value)
        span.set_attribute(Aiobs.DRIFT_SCORE, result.score)
        span.set_attribute(Aiobs.DRIFT_METHOD, result.method)

    return {
        "mean_groundedness_before": round(sum(before) / len(before), 4),
        "mean_groundedness_after": round(sum(after) / len(after), 4),
        "psi": result.score,
        "verdict": result.verdict,
        "latency_changed": False,
        "error_rate_changed": False,
    }
