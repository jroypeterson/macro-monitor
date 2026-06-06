"""Tests for the transform math primitives. The math here is high-risk-
of-silent-bug — z-score against a trending raw series reads ~+2σ every
month, etc. — so checking it explicitly is worth the lines.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from macro_monitor.transforms import (
    annualized_mom,
    annualized_n_month,
    apply_transform,
    delta_zscore,
    level_zscore,
    mom_chg,
    mom_pct,
    qoq_pct_saar,
    raw,
    yoy_pct,
)


def monthly_series(values: list[float], start: str = "2020-01-01") -> pd.Series:
    idx = pd.date_range(start=start, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


def weekly_series(values: list[float], start: str = "2024-01-01") -> pd.Series:
    """Mondays, like FRED weekly series (e.g. GASREGW gas prices)."""
    idx = pd.date_range(start=start, periods=len(values), freq="W-MON")
    return pd.Series(values, index=idx, dtype=float)


def test_raw_returns_value_at_target():
    s = monthly_series([100.0, 101.0, 102.0])
    assert raw(s, pd.Timestamp("2020-02-01")) == 101.0


def test_weekly_yoy_matches_nearest_obs_a_year_back():
    # 60 weeks of data: target is the last; ~52 weeks earlier should match
    # even though no observation lands exactly one calendar year back.
    vals = [3.00 + 0.01 * i for i in range(60)]  # rising ~ $3.00 → $3.59
    s = weekly_series(vals)
    target = s.index[-1]
    got = apply_transform("yoy_pct_weekly", s, target)
    # cur vs the value ~52 weeks prior (index 7) → both known, positive YoY.
    assert got is not None
    assert got > 0


def test_weekly_mom_uses_4_week_lookback():
    # Flat then a step up in the last 4 weeks.
    vals = [4.00] * 20 + [4.40]  # last obs jumps 10% vs 4 weeks back (4.00)
    s = weekly_series(vals)
    target = s.index[-1]
    got = apply_transform("mom_pct_weekly", s, target)
    assert got == pytest.approx(10.0, abs=0.001)


def test_weekly_transforms_return_none_without_history():
    s = weekly_series([4.00, 4.05])  # too short for a year-back lookup
    target = s.index[-1]
    assert apply_transform("yoy_pct_weekly", s, target) is None


def test_raw_missing_period_returns_none():
    s = monthly_series([100.0, 101.0])
    assert raw(s, pd.Timestamp("2099-01-01")) is None


def test_yoy_pct_matches_definition():
    # 13 months of data; YoY at month 13 = 110/100 - 1 = 10%
    values = [100.0] * 12 + [110.0]
    s = monthly_series(values, start="2020-01-01")
    target = pd.Timestamp("2021-01-01")
    assert yoy_pct(s, target) == pytest.approx(10.0)


def test_mom_pct_matches_definition():
    s = monthly_series([100.0, 105.0])
    target = pd.Timestamp("2020-02-01")
    assert mom_pct(s, target) == pytest.approx(5.0)


def test_annualized_mom_compounds_correctly():
    # +0.5% MoM should compound to ~6.17% annualized
    s = monthly_series([100.0, 100.5])
    target = pd.Timestamp("2020-02-01")
    expected = (math.pow(1.005, 12) - 1.0) * 100.0
    assert annualized_mom(s, target) == pytest.approx(expected, rel=1e-9)


def test_annualized_mom_rejects_zero_prior():
    s = monthly_series([0.0, 1.0])
    target = pd.Timestamp("2020-02-01")
    assert annualized_mom(s, target) is None


def test_mom_chg_returns_level_difference():
    # Payrolls-style: +185K
    s = monthly_series([150_000.0, 150_185.0])
    target = pd.Timestamp("2020-02-01")
    assert mom_chg(s, target) == pytest.approx(185.0)


def test_qoq_pct_saar_matches_definition():
    # 4 months of data, value at month 4 vs month 1 (i.e. 3 months prior)
    s = monthly_series([100.0, 100.0, 100.0, 101.0])
    target = pd.Timestamp("2020-04-01")
    expected = (math.pow(101.0 / 100.0, 4) - 1.0) * 100.0
    assert qoq_pct_saar(s, target) == pytest.approx(expected, rel=1e-9)


def test_apply_transform_dispatches_by_name():
    s = monthly_series([100.0, 101.0])
    target = pd.Timestamp("2020-02-01")
    assert apply_transform("mom_pct", s, target) == pytest.approx(1.0)


def test_apply_transform_unknown_raises():
    s = monthly_series([100.0])
    with pytest.raises(KeyError):
        apply_transform("bogus_transform", s, pd.Timestamp("2020-01-01"))


def test_annualized_n_month_compounds_over_window():
    # 4 months: 100, 101, 102.01, 103.0301 — that's exactly +1%/mo.
    s = monthly_series([100.0, 101.0, 102.01, 103.0301])
    target = pd.Timestamp("2020-04-01")
    # 3mo annualized from 100 to 103.0301 over 3 months => same as +1%/mo annualized
    result = annualized_n_month(s, target, window_months=3)
    expected = (math.pow(1.01, 12) - 1.0) * 100.0
    assert result == pytest.approx(expected, rel=1e-6)


def test_delta_zscore_is_none_when_history_thin():
    s = monthly_series([100.0] * 6)
    target = pd.Timestamp("2020-06-01")
    # Only 6 months — below the 12-period minimum
    assert delta_zscore(s, target, "yoy_pct", lookback_years=5) is None


def test_delta_zscore_zero_when_constant_changes():
    # Stable monotonic growth: yoy_pct is constant, so deltas are 0, std=0, returns None
    values = [100.0 * math.pow(1.02 / 12, i) for i in range(60)]
    s = monthly_series(values, start="2020-01-01")
    target = pd.Timestamp("2024-12-01")
    assert delta_zscore(s, target, "yoy_pct", lookback_years=4) is None


def test_level_zscore_standardizes_latest_value():
    import statistics

    # Stationary alternating rate; level z = (latest - mean) / sample-std.
    vals = [3.0, 5.0] * 30
    s = monthly_series(vals)
    target = s.index[-1]
    z = level_zscore(s, target, "raw", lookback_years=5)
    expected = (vals[-1] - statistics.mean(vals)) / statistics.stdev(vals)
    assert z == pytest.approx(expected, rel=1e-9)


def test_level_zscore_is_none_when_history_thin():
    s = monthly_series([4.0] * 6)
    target = pd.Timestamp("2020-06-01")
    assert level_zscore(s, target, "raw", lookback_years=5) is None


def test_level_zscore_none_when_constant_level():
    # Flat level → std 0 → None (no meaningful z-score).
    s = monthly_series([4.0] * 60)
    target = pd.Timestamp("2024-12-01")
    assert level_zscore(s, target, "raw", lookback_years=5) is None
