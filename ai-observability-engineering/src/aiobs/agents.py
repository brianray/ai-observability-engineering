"""Multi-agent tracing helpers (Part VI, Chapters 15-17).

Chapter 1 cites MAST, the Multi-Agent System Failure Taxonomy from Cemri
et al., for the observation that none of its fourteen failure modes is a
transport error. That is the design constraint for this module: an agent
run can be entirely healthy by HTTP standards and still be broken, so the
detectors here look at the shape of the run rather than at status codes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum


class MastCategory(str, Enum):
    SYSTEM_DESIGN = "system_design_issues"
    INTER_AGENT_MISALIGNMENT = "inter_agent_misalignment"
    TASK_VERIFICATION = "task_verification"


class MastFailureMode(str, Enum):
    """The fourteen modes, as identifiers. See Cemri et al. (arXiv:2503.13657)."""

    FM_1_1_DISOBEY_TASK_SPEC = "FM-1.1"
    FM_1_2_DISOBEY_ROLE_SPEC = "FM-1.2"
    FM_1_3_STEP_REPETITION = "FM-1.3"
    FM_1_4_LOSS_OF_HISTORY = "FM-1.4"
    FM_1_5_UNAWARE_OF_TERMINATION = "FM-1.5"
    FM_2_1_CONVERSATION_RESET = "FM-2.1"
    FM_2_2_FAIL_TO_ASK_CLARIFICATION = "FM-2.2"
    FM_2_3_TASK_DERAILMENT = "FM-2.3"
    FM_2_4_INFORMATION_WITHHOLDING = "FM-2.4"
    FM_2_5_IGNORED_OTHER_AGENT = "FM-2.5"
    FM_2_6_REASONING_ACTION_MISMATCH = "FM-2.6"
    FM_3_1_PREMATURE_TERMINATION = "FM-3.1"
    FM_3_2_NO_OR_INCOMPLETE_VERIFICATION = "FM-3.2"
    FM_3_3_INCORRECT_VERIFICATION = "FM-3.3"

    @property
    def category(self) -> MastCategory:
        prefix = self.value.split("-")[1].split(".")[0]
        return {
            "1": MastCategory.SYSTEM_DESIGN,
            "2": MastCategory.INTER_AGENT_MISALIGNMENT,
            "3": MastCategory.TASK_VERIFICATION,
        }[prefix]


@dataclass(frozen=True)
class AgentStep:
    agent: str
    action: str
    output: str = ""
    tokens: int = 0
    succeeded: bool = True


@dataclass
class AgentRun:
    """One multi-agent execution, as a flat sequence of steps."""

    task: str
    steps: list[AgentStep] = field(default_factory=list)
    terminated: bool = False
    verified: bool = False

    def add(self, agent: str, action: str, output: str = "", tokens: int = 0) -> AgentRun:
        self.steps.append(AgentStep(agent, action, output, tokens))
        return self

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens for s in self.steps)

    @property
    def handoff_depth(self) -> int:
        """Number of times control passed between distinct agents."""
        depth = 0
        previous: str | None = None
        for step in self.steps:
            if previous is not None and step.agent != previous:
                depth += 1
            previous = step.agent
        return depth


def detect_step_repetition(run: AgentRun, threshold: int = 3) -> bool:
    """MAST FM-1.3. The failure behind the $47,000 retry loop."""
    if threshold < 2:
        raise ValueError("threshold must be >= 2")
    counts = Counter((s.agent, s.action) for s in run.steps)
    return any(count >= threshold for count in counts.values())


def detect_missing_termination(run: AgentRun, max_steps: int = 20) -> bool:
    """MAST FM-1.5. Ran to the step ceiling without declaring completion."""
    return not run.terminated and len(run.steps) >= max_steps


def detect_missing_verification(run: AgentRun) -> bool:
    """MAST FM-3.2. Produced an answer nobody checked."""
    return run.terminated and not run.verified


def detect_unbounded_consumption(run: AgentRun, token_budget: int) -> bool:
    """OWASP LLM10. The cost failure that no error rate reveals."""
    if token_budget <= 0:
        raise ValueError("token_budget must be positive")
    return run.total_tokens > token_budget


def classify(run: AgentRun, *, token_budget: int = 100_000) -> list[MastFailureMode]:
    """Return every failure mode this run trips. Empty list means clean."""
    modes: list[MastFailureMode] = []
    if detect_step_repetition(run):
        modes.append(MastFailureMode.FM_1_3_STEP_REPETITION)
    if detect_missing_termination(run):
        modes.append(MastFailureMode.FM_1_5_UNAWARE_OF_TERMINATION)
    if detect_missing_verification(run):
        modes.append(MastFailureMode.FM_3_2_NO_OR_INCOMPLETE_VERIFICATION)
    if detect_unbounded_consumption(run, token_budget):
        modes.append(MastFailureMode.FM_1_1_DISOBEY_TASK_SPEC)
    return modes


def failure_vector(runs: Sequence[AgentRun]) -> dict[str, int]:
    """Failure-mode histogram across many runs, as Chapter 16 reports it."""
    counter: Counter[str] = Counter()
    for run in runs:
        for mode in classify(run):
            counter[mode.value] += 1
    return dict(sorted(counter.items()))
