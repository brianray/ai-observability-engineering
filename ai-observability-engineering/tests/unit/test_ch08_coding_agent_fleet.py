"""Unit tests: Chapter 8 coding-agent fleet join (Listing 8.5)."""

from __future__ import annotations

import pytest

from chapters.ch08.coding_agent_fleet import (
    KNOWN_HARNESSES,
    CodingSession,
    MergedChange,
    join_fleet,
)


def _session(sid: str, team: str = "payments", **kw) -> CodingSession:
    base: dict = {
        "session_id": sid,
        "harness": "claude_code",
        "user": f"{sid}@example.com",
        "team": team,
        "cost_center": "cc-100",
        "input_tokens": 1_000,
        "output_tokens": 500,
        "cache_read_tokens": 3_000,
        "cache_creation_tokens": 1_000,
        "cost_usd": 1.0,
        "tool_calls": 12,
        "permissions_granted": 10,
        "permissions_denied": 2,
        "edits_accepted": 8,
        "edits_rejected": 2,
    }
    base.update(kw)
    return CodingSession(**base)


def test_known_harnesses_are_the_four_the_chapter_names():
    assert KNOWN_HARNESSES == ("claude_code", "cursor", "codex", "copilot")


def test_cache_hit_rate_counts_cache_reads_against_all_cacheable_input():
    report = join_fleet([_session("s1")], [])
    m = report["payments"]
    # 3,000 cache reads out of 1,000 + 3,000 + 1,000 cacheable tokens.
    assert m.cache_hit_rate == pytest.approx(0.6)
    assert m.tokens == 5_500


def test_unattributed_cost_is_every_session_not_joined_to_a_merged_change():
    sessions = [_session("s1"), _session("s2"), _session("s3", cost_usd=4.0)]
    changes = [
        MergedChange("pr-1", ("s1",), merged=True, review_rounds=1, reverted_within_30d=False),
        MergedChange("pr-2", ("s2",), merged=False, review_rounds=0, reverted_within_30d=False),
    ]
    m = join_fleet(sessions, changes)["payments"]
    assert m.merged_changes == 1
    assert m.unattributed_sessions == 2
    assert m.unattributed_cost_usd == pytest.approx(5.0)
    assert m.unattributed_share == pytest.approx(5.0 / 6.0)


def test_tokens_per_merged_change_and_rework_rate():
    sessions = [_session("s1"), _session("s2")]
    changes = [
        MergedChange("pr-1", ("s1",), merged=True, review_rounds=2, reverted_within_30d=True),
        MergedChange("pr-2", ("s2",), merged=True, review_rounds=1, reverted_within_30d=False),
    ]
    m = join_fleet(sessions, changes)["payments"]
    assert m.tokens_per_merged_change == pytest.approx(11_000 / 2)
    assert m.rework_rate == pytest.approx(0.5)
    assert m.review_rounds == 3


def test_rates_are_none_not_zero_when_the_denominator_is_empty():
    m = join_fleet(
        [
            _session(
                "s1",
                edits_accepted=0,
                edits_rejected=0,
                permissions_granted=0,
                permissions_denied=0,
            )
        ],
        [],
    )["payments"]
    assert m.edit_accept_rate is None
    assert m.permission_denial_rate is None
    assert m.tokens_per_merged_change is None
    assert m.rework_rate is None


def test_a_change_touched_by_two_teams_counts_for_both():
    sessions = [_session("s1", team="payments"), _session("s2", team="platform", harness="cursor")]
    changes = [
        MergedChange("pr-1", ("s1", "s2"), merged=True, review_rounds=1, reverted_within_30d=False)
    ]
    report = join_fleet(sessions, changes)
    assert report["payments"].merged_changes == 1
    assert report["platform"].merged_changes == 1
    assert report["platform"].harnesses == {"cursor"}
    assert report["payments"].unattributed_sessions == 0
