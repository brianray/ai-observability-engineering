"""Named failure scenarios.

Each scenario is a small, reproducible version of a production failure the
book returns to. Chapters use them as the "before" state; tests use them
to prove a detector actually fires.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..agents import AgentRun
from ..providers import FailureMode, MockProvider


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    description: str
    pillar: str
    detected_by: str
    build: Callable[[], object]

    def __call__(self) -> object:
        return self.build()


def _silent_retry_loop() -> AgentRun:
    """Eleven days of green dashboards and a $47,000 bill (Chapter 1)."""
    run = AgentRun(task="research competitor pricing")
    for _ in range(12):
        run.add("researcher", "search_web", "no new results", tokens=4200)
    return run


def _confidently_wrong() -> MockProvider:
    """Status 200, latency normal, answer false (Chapters 1 and 13)."""
    return MockProvider(failure_mode=FailureMode.CONFIDENTLY_WRONG)


def _ungrounded_rag() -> MockProvider:
    """Retrieval drifted; the assistant answers from the model, not the corpus."""
    return MockProvider(failure_mode=FailureMode.UNGROUNDED)


def _no_termination() -> AgentRun:
    """MAST FM-1.5. The agent never decides it is finished."""
    run = AgentRun(task="summarize the quarterly report")
    for i in range(25):
        run.add("summarizer", f"refine_{i}", tokens=800)
    return run


def _unverified_output() -> AgentRun:
    """MAST FM-3.2. An answer nobody checked before it shipped."""
    run = AgentRun(task="generate the config change", terminated=True, verified=False)
    run.add("planner", "plan", tokens=500)
    run.add("executor", "apply", tokens=700)
    return run


SCENARIOS: dict[str, Scenario] = {
    s.key: s
    for s in (
        Scenario(
            key="silent_retry_loop",
            title="The $47,000 silent retry loop",
            description="Uptime 99.99%, error rate 0.0%, and an infinite retry loop underneath.",
            pillar="roi",
            detected_by="aiobs.agents.detect_step_repetition",
            build=_silent_retry_loop,
        ),
        Scenario(
            key="confidently_wrong",
            title="Confidently wrong behind a 200",
            description="Fluent, well formed, factually false. Every performance metric healthy.",
            pillar="responsibility",
            detected_by="aiobs.evals.HallucinationEvaluator",
            build=_confidently_wrong,
        ),
        Scenario(
            key="ungrounded_rag",
            title="Retrieval drift in a RAG assistant",
            description="A document update breaks retrieval; answers stop being grounded.",
            pillar="responsibility",
            detected_by="aiobs.evals.GroundednessEvaluator",
            build=_ungrounded_rag,
        ),
        Scenario(
            key="no_termination",
            title="Agent unaware of termination",
            description="MAST FM-1.5. Runs to the step ceiling without completing.",
            pillar="performance",
            detected_by="aiobs.agents.detect_missing_termination",
            build=_no_termination,
        ),
        Scenario(
            key="unverified_output",
            title="Unverified agent output",
            description="MAST FM-3.2. The run terminated, but nothing checked the result.",
            pillar="risk",
            detected_by="aiobs.agents.detect_missing_verification",
            build=_unverified_output,
        ),
    )
}


def get(key: str) -> Scenario:
    try:
        return SCENARIOS[key]
    except KeyError as exc:
        raise KeyError(f"unknown scenario {key!r}; have {sorted(SCENARIOS)}") from exc
