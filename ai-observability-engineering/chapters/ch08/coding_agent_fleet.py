"""Joining coding-agent telemetry to the work it produced (Listing 8.5).

A coding agent such as Claude Code, Cursor, Codex, or Copilot is the one
tool-using agent most organizations already run at fleet scale, and the
one whose loop they do not own. The vendor controls the harness; what the
organization receives is the harness's native telemetry (sessions,
tokens, cache reads, tool calls, permission decisions, edit decisions)
and, separately, the systems of record the work lands in (pull requests,
tickets, CI). Kept apart, those are two logs. Joined, they answer the
question Chapter 7 asks of every AI system: what did it cost, and what
did it produce.

Three things this module insists on:

**Resource attributes carry identity.** ``user``, ``team``, and
``cost_center`` arrive as OTel resource attributes on the vendor's
metrics, not as labels the organization adds later. A fleet dashboard
that cannot slice by team is a bill, not an observation.

**Cache reads are counted in the denominator.** The share of input the
model read from cache rather than re-processed is the single largest
lever on coding-agent cost, and it is invisible if cache tokens are
folded into "input tokens" or dropped.

**Unattributed spend is a first-class number.** A session that joins to
no merged change is not noise to discard; it is the fleet-scale form of
the busy-without-progress loop Chapter 16 opens with.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

#: The harnesses this module expects to see. The join does not depend on
#: which one produced a session; it depends only on the session carrying
#: the fields below.
KNOWN_HARNESSES: tuple[str, ...] = ("claude_code", "cursor", "codex", "copilot")


@dataclass(frozen=True)
class CodingSession:
    """One agent session, as the harness's native OTel export describes it."""

    session_id: str
    harness: str
    user: str
    team: str
    cost_center: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float
    tool_calls: int
    permissions_granted: int
    permissions_denied: int
    edits_accepted: int
    edits_rejected: int

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )


@dataclass(frozen=True)
class MergedChange:
    """One change in the system of record, with the sessions that touched it."""

    change_id: str
    session_ids: tuple[str, ...]
    merged: bool
    review_rounds: int
    reverted_within_30d: bool


@dataclass
class TeamFleetMetrics:
    """What a fleet dashboard shows per team, computed from the join."""

    team: str
    sessions: int = 0
    cost_usd: float = 0.0
    tokens: int = 0
    cache_read_tokens: int = 0
    cacheable_tokens: int = 0
    edits_accepted: int = 0
    edits_rejected: int = 0
    permissions_granted: int = 0
    permissions_denied: int = 0
    merged_changes: int = 0
    reverted_changes: int = 0
    review_rounds: int = 0
    unattributed_sessions: int = 0
    unattributed_cost_usd: float = 0.0
    harnesses: set[str] = field(default_factory=set)

    @property
    def cache_hit_rate(self) -> float | None:
        if self.cacheable_tokens == 0:
            return None
        return self.cache_read_tokens / self.cacheable_tokens

    @property
    def edit_accept_rate(self) -> float | None:
        decided = self.edits_accepted + self.edits_rejected
        return None if decided == 0 else self.edits_accepted / decided

    @property
    def permission_denial_rate(self) -> float | None:
        decided = self.permissions_granted + self.permissions_denied
        return None if decided == 0 else self.permissions_denied / decided

    @property
    def tokens_per_merged_change(self) -> float | None:
        return None if self.merged_changes == 0 else self.tokens / self.merged_changes

    @property
    def rework_rate(self) -> float | None:
        return None if self.merged_changes == 0 else self.reverted_changes / self.merged_changes

    @property
    def unattributed_share(self) -> float | None:
        return None if self.cost_usd == 0 else self.unattributed_cost_usd / self.cost_usd


def join_fleet(
    sessions: list[CodingSession], changes: list[MergedChange]
) -> dict[str, TeamFleetMetrics]:
    """Join sessions to changes and roll both up by team.

    A session attributed to any merged change counts as attributed; every
    other session's cost lands in ``unattributed_cost_usd``. The join key
    is the session identifier the harness emits, which the organization's
    commit or pull-request tooling must carry forward; without that one
    field there is no join, and the fleet is observable only as a bill.
    """
    merged_sessions: set[str] = set()
    team_of: dict[str, str] = {s.session_id: s.team for s in sessions}
    per_team: dict[str, TeamFleetMetrics] = defaultdict(lambda: TeamFleetMetrics(team=""))

    for change in changes:
        if not change.merged:
            continue
        teams = {team_of[sid] for sid in change.session_ids if sid in team_of}
        for team in teams:
            metrics = per_team[team]
            metrics.team = team
            metrics.merged_changes += 1
            metrics.review_rounds += change.review_rounds
            if change.reverted_within_30d:
                metrics.reverted_changes += 1
        merged_sessions.update(change.session_ids)

    for s in sessions:
        metrics = per_team[s.team]
        metrics.team = s.team
        metrics.sessions += 1
        metrics.cost_usd += s.cost_usd
        metrics.tokens += s.total_tokens
        metrics.cache_read_tokens += s.cache_read_tokens
        metrics.cacheable_tokens += s.input_tokens + s.cache_read_tokens + s.cache_creation_tokens
        metrics.edits_accepted += s.edits_accepted
        metrics.edits_rejected += s.edits_rejected
        metrics.permissions_granted += s.permissions_granted
        metrics.permissions_denied += s.permissions_denied
        metrics.harnesses.add(s.harness)
        if s.session_id not in merged_sessions:
            metrics.unattributed_sessions += 1
            metrics.unattributed_cost_usd += s.cost_usd

    return dict(per_team)
