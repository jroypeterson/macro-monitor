"""Tests for the Tier B posting gate.

The gate is the load-bearing logic that distinguishes "post every release"
from "post only when the move is unusual." Subtle bugs here are exactly
what would either spam #macro or silently swallow material data.
"""

from __future__ import annotations

import pytest

from macro_monitor.config import FamilyConfig, TierBGate
from macro_monitor.release_runner import ContextResult, ReleaseResult
from macro_monitor.tier_b_gate import evaluate


def _family_template(tier: str, gate: TierBGate | None) -> FamilyConfig:
    """Construct a minimal FamilyConfig that's valid enough for gate testing.
    We don't need the full series + chart spec — the gate only looks at
    family.tier and family.tier_b_gate."""
    return FamilyConfig.model_validate({
        "tier": tier,
        "family_type": "numeric",
        "cadence": "monthly",
        "release_calendar_id": 1,
        "release_time_et": "08:30",
        "source": "fred",
        "display_name": "Test Family",
        "period_label_format": "{month_name} {year}",
        "headline": [
            {"id": "TEST", "label": "test", "primary_transform": "raw"}
        ],
        "tier_b_gate": gate.model_dump() if gate else None,
        "dedupe": {"headline_hash": ["TEST"], "component_hash": []},
        "agency": {"release_page": "http://test", "archive_path": "x"},
    })


def _result_with_z(z_score: float | None) -> ReleaseResult:
    """Construct a ReleaseResult carrying a specific z-score in its context."""
    if z_score is None:
        ctx = ContextResult(
            anchor_series="TEST",
            anchor_transform="raw",
            trends=[],
            zscore=None,
            zscore_lookback_years=5,
            zscore_kind="delta",
        )
    else:
        ctx = ContextResult(
            anchor_series="TEST",
            anchor_transform="raw",
            trends=[],
            zscore=z_score,
            zscore_lookback_years=5,
            zscore_kind="delta",
        )
    return ReleaseResult(
        family_id="test",
        family_display_name="Test Family",
        period="2026-04",
        period_label="April 2026",
        headline=[],
        components=[],
        computed=[],
        context=ctx,
        source="fred",
        source_fetched_at="2026-05-28T12:00:00+00:00",
        latest_observation_period="2026-04",
        expected_observation_period="2026-04",
        is_stale=False,
        source_lag_minutes=None,
    )


def test_tier_a_always_posts():
    family = _family_template(tier="A", gate=None)
    result = _result_with_z(z_score=0.1)  # small z, but tier A doesn't care
    verdict = evaluate(family, result)
    assert verdict.should_post is True
    assert "tier a" in verdict.reason.lower()


def test_tier_a_posts_even_when_z_score_none():
    """Tier A doesn't care about z-score at all. First few prints of a
    new series have no z-score; Tier A still posts."""
    family = _family_template(tier="A", gate=None)
    result = _result_with_z(z_score=None)
    verdict = evaluate(family, result)
    assert verdict.should_post is True


def test_tier_b_posts_when_z_exceeds_threshold():
    gate = TierBGate(threshold=1.0, vs="trailing_5y_volatility")
    family = _family_template(tier="B", gate=gate)
    result = _result_with_z(z_score=1.5)
    verdict = evaluate(family, result)
    assert verdict.should_post is True
    assert "material surprise" in verdict.reason


def test_tier_b_posts_on_large_negative_surprise():
    """A -2σ surprise is just as material as +2σ. abs(z) check."""
    gate = TierBGate(threshold=1.0, vs="trailing_5y_volatility")
    family = _family_template(tier="B", gate=gate)
    result = _result_with_z(z_score=-2.3)
    verdict = evaluate(family, result)
    assert verdict.should_post is True


def test_tier_b_skips_when_z_below_threshold():
    gate = TierBGate(threshold=1.0, vs="trailing_5y_volatility")
    family = _family_template(tier="B", gate=gate)
    result = _result_with_z(z_score=0.7)
    verdict = evaluate(family, result)
    assert verdict.should_post is False
    assert "not material" in verdict.reason


def test_tier_b_skips_when_z_score_unavailable():
    """First few prints of a Tier B series have no z-score yet (insufficient
    history). Skip rather than spam the channel with a 'no data' card."""
    gate = TierBGate(threshold=1.0, vs="trailing_5y_volatility")
    family = _family_template(tier="B", gate=gate)
    result = _result_with_z(z_score=None)
    verdict = evaluate(family, result)
    assert verdict.should_post is False
    assert "insufficient history" in verdict.reason


def test_tier_b_threshold_is_inclusive():
    """A z-score exactly equal to the threshold should fire (>= not >)."""
    gate = TierBGate(threshold=1.0, vs="trailing_5y_volatility")
    family = _family_template(tier="B", gate=gate)
    result = _result_with_z(z_score=1.0)
    verdict = evaluate(family, result)
    assert verdict.should_post is True


def test_consensus_gate_falls_back_to_posting_pre_v15():
    """Consensus-based gating is Phase 1.5; until it ships, fall back to
    posting so we don't silently swallow data we'd want to see."""
    gate = TierBGate(threshold=1.0, vs="consensus")
    family = _family_template(tier="B", gate=gate)
    result = _result_with_z(z_score=0.1)
    verdict = evaluate(family, result)
    assert verdict.should_post is True
    assert "consensus" in verdict.reason.lower()
