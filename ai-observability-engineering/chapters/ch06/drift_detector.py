"""Listing 6.3: nearest-neighbor embedding drift and the items behind it."""

from __future__ import annotations

import math

from aiobs import Aiobs, Layer, Pillar, get_tracer
from aiobs.drift import embedding_drift_score, top_drifting_items
from chapters.registry import example


def _rotate(vector: tuple[float, float], radians: float) -> tuple[float, float]:
    x, y = vector
    cos_theta = math.cos(radians)
    sin_theta = math.sin(radians)
    return (
        x * cos_theta - y * sin_theta,
        x * sin_theta + y * cos_theta,
    )


@example(
    chapter=6,
    key="embedding_drift_neighbors",
    title="Detecting embedding drift with nearest neighbors",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="6.3",
)
def embedding_drift_neighbors() -> dict:
    """Score drift the way a retrieval system feels it item by item.

    Averaging every pairwise similarity would smear the signal across the
    whole matrix. The more actionable question is whether each current
    item can still find a close match in the historical reference set.
    """

    tracer = get_tracer(__name__)
    reference = [
        (1.0, 0.0),
        (0.8, 0.2),
        (0.1, 0.9),
        (-0.7, 0.6),
        (-0.5, -0.8),
    ]
    current = [_rotate(vector, math.pi / 5) for vector in reference]
    score = embedding_drift_score(reference, current)
    drifting = top_drifting_items(reference, current, k=3)

    with tracer.start_as_current_span("embedding.drift.evaluate") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        span.set_attribute(Aiobs.LAYER, Layer.MODEL_AND_INFERENCE.value)
        span.set_attribute("aiobs.drift.embedding_score", score)

    return {
        "embedding_drift_score": score,
        "top_drifting_items": drifting,
    }
