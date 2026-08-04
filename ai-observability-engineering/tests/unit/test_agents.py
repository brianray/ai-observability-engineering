"""Unit tests: multi-agent failure detection."""

import pytest

from aiobs.agents import (
    AgentRun,
    MastCategory,
    MastFailureMode,
    classify,
    detect_missing_termination,
    detect_missing_verification,
    detect_step_repetition,
    detect_unbounded_consumption,
    failure_vector,
)


def _loop(times: int = 12) -> AgentRun:
    run = AgentRun(task="research")
    for _ in range(times):
        run.add("researcher", "search", tokens=1000)
    return run


def test_step_repetition_detected():
    assert detect_step_repetition(_loop())


def test_varied_steps_are_not_repetition():
    run = AgentRun(task="research")
    for i in range(12):
        run.add("researcher", f"step_{i}", tokens=100)
    assert not detect_step_repetition(run)


def test_repetition_threshold_must_be_at_least_two():
    with pytest.raises(ValueError):
        detect_step_repetition(_loop(), threshold=1)


def test_missing_termination():
    assert detect_missing_termination(_loop(times=25))
    terminated = _loop(times=25)
    terminated.terminated = True
    assert not detect_missing_termination(terminated)


def test_missing_verification_only_applies_after_termination():
    run = AgentRun(task="x", terminated=True, verified=False)
    assert detect_missing_verification(run)
    run.verified = True
    assert not detect_missing_verification(run)
    assert not detect_missing_verification(AgentRun(task="x"))


def test_unbounded_consumption():
    assert detect_unbounded_consumption(_loop(), token_budget=1000)
    assert not detect_unbounded_consumption(_loop(), token_budget=1_000_000)


def test_token_budget_must_be_positive():
    with pytest.raises(ValueError):
        detect_unbounded_consumption(_loop(), token_budget=0)


def test_handoff_depth_counts_agent_changes():
    run = AgentRun(task="x")
    run.add("a", "1").add("a", "2").add("b", "3").add("a", "4")
    assert run.handoff_depth == 2


def test_classify_returns_every_mode_tripped():
    modes = classify(_loop(times=25), token_budget=500)
    assert MastFailureMode.FM_1_3_STEP_REPETITION in modes
    assert MastFailureMode.FM_1_5_UNAWARE_OF_TERMINATION in modes


def test_clean_run_trips_nothing():
    run = AgentRun(task="x", terminated=True, verified=True)
    run.add("planner", "plan", tokens=100).add("writer", "draft", tokens=100)
    assert classify(run) == []


def test_mast_categories_derive_from_the_identifier():
    assert MastFailureMode.FM_1_3_STEP_REPETITION.category is MastCategory.SYSTEM_DESIGN
    assert (
        MastFailureMode.FM_2_3_TASK_DERAILMENT.category
        is MastCategory.INTER_AGENT_MISALIGNMENT
    )
    assert (
        MastFailureMode.FM_3_2_NO_OR_INCOMPLETE_VERIFICATION.category
        is MastCategory.TASK_VERIFICATION
    )


def test_taxonomy_has_fourteen_modes():
    """Cemri et al. identify fourteen. If this changes, the citation does too."""
    assert len(list(MastFailureMode)) == 14


def test_failure_vector_aggregates_across_runs():
    vector = failure_vector([_loop(), _loop()])
    assert vector[MastFailureMode.FM_1_3_STEP_REPETITION.value] == 2
