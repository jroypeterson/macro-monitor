"""Tier B posting gate.

Tier A families post unconditionally on every release.
Tier B families post only when the move is unusual — currently measured
as |delta z-score| >= threshold against the trailing 5y distribution of
changes (Phase 1; consensus-based gating is Phase 1.5).

Per the v5 plan §5: 'Level z-score and delta z-score answer different
questions; "is this print's move unusual" is the right question for a
gate.' The delta z-score is computed in compute_release using the
anchor_transform — we read it directly here.

Gate logic is intentionally narrow and side-effect-free; the orchestrator
decides what to do with the verdict (publish vs skip).
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import FamilyConfig
from .release_runner import ReleaseResult


@dataclass(frozen=True)
class GateVerdict:
    """Result of running the Tier B gate against a release.

    should_post: True if the release should be published to Slack.
    reason: human-readable explanation (logged + surfaced in dashboards).
    z_score: the computed z-score that drove the decision (None if not
             available — typical for series with thin history).
    """

    should_post: bool
    reason: str
    z_score: float | None


def evaluate(family: FamilyConfig, result: ReleaseResult) -> GateVerdict:
    """Decide whether `result` should be posted to Slack based on the
    family's tier + tier_b_gate config."""

    # Tier A: always post. No gate to evaluate.
    if family.tier == "A":
        return GateVerdict(
            should_post=True,
            reason="tier A — always posts",
            z_score=None,
        )

    # Tier B without a gate is a config bug (validator catches this), but
    # be defensive and default to posting so we don't silently swallow
    # data.
    if family.tier_b_gate is None:
        return GateVerdict(
            should_post=True,
            reason="tier B without tier_b_gate (defensive default — config bug?)",
            z_score=None,
        )

    # Phase 1.5: consensus-based gating. Until that ships, fall back to
    # the volatility gate so the family still posts on big surprises.
    if family.tier_b_gate.vs == "consensus":
        return GateVerdict(
            should_post=True,
            reason="consensus gate not implemented (v1.5); defaulting to post",
            z_score=None,
        )

    # Phase 1: trailing_5y_volatility — read the z-score that compute_release
    # already computed against the family's anchor_transform (delta or level
    # per the family's zscore_kind; both are |z|>=threshold-gated identically).
    z = (
        result.context.zscore
        if result.context is not None
        else None
    )
    threshold = family.tier_b_gate.threshold

    if z is None:
        # No z-score available — typically because the series doesn't
        # have enough history. Skip rather than post (safer: a Tier B
        # family with no history shouldn't spam the channel on its first
        # observation).
        return GateVerdict(
            should_post=False,
            reason="no z-score available (insufficient history)",
            z_score=None,
        )

    if abs(z) >= threshold:
        return GateVerdict(
            should_post=True,
            reason=f"|z|={abs(z):.2f}σ >= {threshold:.2f}σ — material surprise",
            z_score=z,
        )

    return GateVerdict(
        should_post=False,
        reason=f"|z|={abs(z):.2f}σ < {threshold:.2f}σ — not material",
        z_score=z,
    )
