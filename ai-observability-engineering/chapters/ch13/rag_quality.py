"""RAG quality as a monitored metric, with a judge you can pin (Listing 13.2).

Two things this code insists on.

**The hallucination rate is not an independent measurement.** It is
``1 - faithfulness``. Publishing both as if they were separate signals
invites someone to alert on one and report the other, and then to explain
a discrepancy that does not exist. The identity is asserted in the tests
for that reason.

**The judge is injected.** An eval whose judge is a live model call is an
eval you cannot run in CI and cannot reproduce next quarter. The mock
judge here is deterministic; swap it for a ragas-backed judge in
production and the surrounding code does not change.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

#: A judge scores one sample and returns (faithfulness, answer_relevancy),
#: each in [0, 1].
Judge = Callable[["RagSample"], tuple[float, float]]


@dataclass(frozen=True)
class RagSample:
    sample_id: str
    user_input: str
    response: str
    retrieved_contexts: tuple[str, ...]
    #: Whether the response is actually grounded in the contexts. Only
    #: the fixtures know this; the judge has to work it out.
    grounded: bool


#: Six fixed samples. Four grounded, two not, so the expected
#: faithfulness mean is 4/6 and the hallucination rate is 2/6.
FIXTURES: tuple[RagSample, ...] = (
    RagSample(
        "s1",
        "How long does shipping take?",
        "Standard shipping takes three to five business days.",
        ("Standard shipping takes three to five business days.",),
        grounded=True,
    ),
    RagSample(
        "s2",
        "Can I get a refund after 40 days?",
        "Refunds are available within 30 days of purchase.",
        ("Refunds are available within 30 days of purchase.",),
        grounded=True,
    ),
    RagSample(
        "s3",
        "Do you ship to Alaska?",
        "Yes, we ship to all fifty states.",
        ("Shipping is available to all fifty states.",),
        grounded=True,
    ),
    RagSample(
        "s4",
        "What is the expedited shipping fee?",
        "Expedited shipping costs $12.99.",
        ("Expedited shipping is available at checkout.",),
        # The fee is not in the context. Fluent, well formed, invented.
        grounded=False,
    ),
    RagSample(
        "s5",
        "Is there a loyalty discount?",
        "Loyalty members receive 15% off every order.",
        ("The loyalty program offers early access to sales.",),
        grounded=False,
    ),
    RagSample(
        "s6",
        "How do I track my order?",
        "You can track your order from the orders page in your account.",
        ("Orders can be tracked from the orders page in your account.",),
        grounded=True,
    ),
)


def deterministic_mock_judge(sample: RagSample) -> tuple[float, float]:
    """A judge with no model behind it and no variance in front of it.

    Returns exactly 1.0 or 0.0 for faithfulness so the aggregate is a
    clean fraction, which is what makes ``hallucination_rate ==
    1 - faithfulness_mean`` checkable rather than approximately true.
    """
    faithfulness = 1.0 if sample.grounded else 0.0
    # Relevancy is independent of grounding: an invented answer can be
    # perfectly on topic, which is exactly why relevancy alone is not a
    # quality gate.
    relevancy = 0.9
    return faithfulness, relevancy


@dataclass(frozen=True)
class RagQualityResult:
    sample_count: int
    faithfulness_mean: float
    answer_relevancy_mean: float

    @property
    def hallucination_rate(self) -> float:
        """Not an independent signal. The complement of faithfulness."""
        return round(1.0 - self.faithfulness_mean, 10)


def evaluate_rag_quality(
    samples: Sequence[RagSample] = FIXTURES,
    judge: Judge = deterministic_mock_judge,
) -> RagQualityResult:
    if not samples:
        raise ValueError("an eval over zero samples is not an eval")

    scores = [judge(sample) for sample in samples]
    faithfulness = sum(s[0] for s in scores) / len(scores)
    relevancy = sum(s[1] for s in scores) / len(scores)
    return RagQualityResult(
        sample_count=len(samples),
        faithfulness_mean=round(faithfulness, 10),
        answer_relevancy_mean=round(relevancy, 10),
    )
