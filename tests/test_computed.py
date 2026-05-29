"""Tests for the computed-series engine.

The forcing-function use case for the engine is HC employment as
sum_of(621, 622, 623) — BLS publishes the sub-cuts but not the
exclude-social-assistance sum we want.
"""

from __future__ import annotations

import pandas as pd
import pytest

from macro_monitor.computed import compute_series


def monthly(values, start="2025-01-01"):
    idx = pd.date_range(start=start, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


def test_sum_of_aligns_by_date_index():
    a = monthly([100.0, 200.0, 300.0])
    b = monthly([10.0, 20.0, 30.0])
    c = monthly([1.0, 2.0, 3.0])
    result = compute_series("sum_of", {"A": a, "B": b, "C": c}, "HC_TOTAL")
    expected_values = [111.0, 222.0, 333.0]
    assert list(result.values) == expected_values
    assert result.name == "HC_TOTAL"


def test_sum_of_propagates_nan_for_data_gaps():
    """If any input has NaN on a date, the sum is NaN — never fabricate
    a partial sum that looks like real data."""
    a = monthly([100.0, float("nan"), 300.0])
    b = monthly([10.0, 20.0, 30.0])
    result = compute_series("sum_of", {"A": a, "B": b}, "X")
    assert result.iloc[0] == 110.0
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == 330.0


def test_sum_of_with_one_input_is_passthrough():
    a = monthly([1.0, 2.0, 3.0])
    result = compute_series("sum_of", {"A": a}, "X")
    assert list(result.values) == [1.0, 2.0, 3.0]


def test_unknown_method_raises():
    a = monthly([1.0])
    with pytest.raises(ValueError) as exc:
        compute_series("not_a_method", {"A": a}, "X")
    assert "not_a_method" in str(exc.value)


def test_empty_inputs_returns_empty_series():
    result = compute_series("sum_of", {}, "X")
    assert result.empty
    assert result.name == "X"


def test_sum_of_handles_misaligned_dates():
    """Inputs may have slightly different date ranges in real data
    (e.g. one series starts later). DataFrame alignment fills with NaN,
    which then propagates to the sum — by design."""
    a = pd.Series([100.0, 200.0], index=pd.date_range("2025-01-01", periods=2, freq="MS"))
    b = pd.Series([10.0, 20.0, 30.0], index=pd.date_range("2025-01-01", periods=3, freq="MS"))
    result = compute_series("sum_of", {"A": a, "B": b}, "X")
    # Jan and Feb have both → real sums; March has only B → NaN
    assert result.iloc[0] == 110.0
    assert result.iloc[1] == 220.0
    assert pd.isna(result.iloc[2])
