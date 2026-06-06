"""Series transforms. Math primitives applied to FRED observations.

z-score / trend / Tier B-gate math ALWAYS runs on the primary_transform,
never the raw series. This avoids the v3 bug where z-scores against a
monotonically trending raw level read ~+2σ every month.

Each transform takes a pandas Series indexed by date and a target date,
and returns the transformed value (or None if insufficient history).
"""

from __future__ import annotations

import math
from typing import Callable

import pandas as pd

# Map of transform name -> callable. Wired up at the bottom.
TRANSFORMS: dict[str, Callable[[pd.Series, pd.Timestamp], float | None]] = {}


def _register(name: str) -> Callable:
    def decorator(fn: Callable[[pd.Series, pd.Timestamp], float | None]) -> Callable:
        TRANSFORMS[name] = fn
        return fn

    return decorator


def _value_at(series: pd.Series, target: pd.Timestamp) -> float | None:
    if target not in series.index:
        return None
    val = series.loc[target]
    if pd.isna(val):
        return None
    return float(val)


def _months_offset(series: pd.Series, target: pd.Timestamp, months: int) -> float | None:
    """Value at target offset by `months` calendar months."""
    prior = target - pd.DateOffset(months=months)
    return _value_at(series, prior)


def _value_near(
    series: pd.Series, when: pd.Timestamp, tol_days: int = 10
) -> float | None:
    """Value at the observation CLOSEST to `when`, within `tol_days`.

    Weekly series (e.g. gas prices) are stamped on Mondays, so a
    calendar-offset target (target - 1 month / 1 year) rarely lands on an
    exact observation date — an exact-match lookup returns None. This finds
    the nearest non-null observation within a tolerance so weekly YoY / MoM
    work without forcing the series onto a monthly grid.
    """
    valid = series.dropna()
    if valid.empty:
        return None
    idx = valid.index
    # Nearest index by absolute time distance.
    deltas = (idx - when).to_series().abs()
    nearest_pos = deltas.values.argmin()
    nearest_date = idx[nearest_pos]
    if abs((nearest_date - when).days) > tol_days:
        return None
    return float(valid.loc[nearest_date])


@_register("yoy_pct_weekly")
def yoy_pct_weekly(series: pd.Series, target: pd.Timestamp) -> float | None:
    """Year-over-year % change for WEEKLY series — matches the nearest
    observation ~52 weeks back (within a 10-day tolerance) instead of an
    exact calendar-month index, so weekly data (gas prices) works."""
    cur = _value_at(series, target)
    prior = _value_near(series, target - pd.DateOffset(years=1))
    if cur is None or prior is None or prior == 0:
        return None
    return 100.0 * (cur / prior - 1.0)


@_register("mom_pct_weekly")
def mom_pct_weekly(series: pd.Series, target: pd.Timestamp) -> float | None:
    """~Month-over-month % change for WEEKLY series — matches the nearest
    observation ~4 weeks back. (A true calendar month doesn't align to a
    weekly grid; 4 weeks is the standard weekly-series convention.)"""
    cur = _value_at(series, target)
    prior = _value_near(series, target - pd.Timedelta(weeks=4))
    if cur is None or prior is None or prior == 0:
        return None
    return 100.0 * (cur / prior - 1.0)


@_register("raw")
def raw(series: pd.Series, target: pd.Timestamp) -> float | None:
    return _value_at(series, target)


@_register("yoy_pct")
def yoy_pct(series: pd.Series, target: pd.Timestamp) -> float | None:
    cur = _value_at(series, target)
    prior = _months_offset(series, target, 12)
    if cur is None or prior is None or prior == 0:
        return None
    return 100.0 * (cur / prior - 1.0)


@_register("mom_pct")
def mom_pct(series: pd.Series, target: pd.Timestamp) -> float | None:
    cur = _value_at(series, target)
    prior = _months_offset(series, target, 1)
    if cur is None or prior is None or prior == 0:
        return None
    return 100.0 * (cur / prior - 1.0)


@_register("annualized_mom")
def annualized_mom(series: pd.Series, target: pd.Timestamp) -> float | None:
    """MoM percent change compounded to an annual rate.

    For inflation indexes, this is the "is this print's pace unusual"
    signal. YoY would be ~92% autocorrelated and statistically near-useless
    as a surprise measure.
    """
    cur = _value_at(series, target)
    prior = _months_offset(series, target, 1)
    if cur is None or prior is None or prior <= 0:
        return None
    ratio = cur / prior
    if ratio <= 0:
        return None
    return 100.0 * (math.pow(ratio, 12) - 1.0)


@_register("mom_chg")
def mom_chg(series: pd.Series, target: pd.Timestamp) -> float | None:
    """Level change month-over-month (e.g. payrolls +175K)."""
    cur = _value_at(series, target)
    prior = _months_offset(series, target, 1)
    if cur is None or prior is None:
        return None
    return float(cur - prior)


@_register("qoq_pct_saar")
def qoq_pct_saar(series: pd.Series, target: pd.Timestamp) -> float | None:
    cur = _value_at(series, target)
    prior_q = target - pd.DateOffset(months=3)
    prior = _value_at(series, prior_q)
    if cur is None or prior is None or prior <= 0:
        return None
    ratio = cur / prior
    if ratio <= 0:
        return None
    return 100.0 * (math.pow(ratio, 4) - 1.0)


def apply_transform(
    name: str, series: pd.Series, target: pd.Timestamp
) -> float | None:
    """Apply a named transform. Raises KeyError on unknown transform names
    (caught by the config validator at load time).
    """
    if name not in TRANSFORMS:
        raise KeyError(f"Unknown transform: {name!r}")
    return TRANSFORMS[name](series, target)


def annualized_n_month(series: pd.Series, target: pd.Timestamp, window_months: int) -> float | None:
    """Compound MoM over a trailing window, annualized.

    Used for "3mo annualized" / "6mo annualized" trend lines on inflation.
    """
    cur = _value_at(series, target)
    prior = _months_offset(series, target, window_months)
    if cur is None or prior is None or prior <= 0:
        return None
    ratio = cur / prior
    if ratio <= 0:
        return None
    return 100.0 * (math.pow(ratio, 12.0 / window_months) - 1.0)


def delta_zscore(
    series: pd.Series,
    target: pd.Timestamp,
    transform: str,
    lookback_years: int = 5,
) -> float | None:
    """Compute the z-score of the LATEST change in the transformed series
    against the trailing N years of changes in that same transform.

    "Is this print's *move* unusual" — answers the right question for a
    Tier B gate; a level z-score answers a different question.
    """
    if transform not in TRANSFORMS:
        raise KeyError(f"Unknown transform: {transform!r}")
    fn = TRANSFORMS[transform]

    # Transform the series at each historical period in the window.
    end = target
    start = target - pd.DateOffset(years=lookback_years)
    history_dates = [d for d in series.index if start <= d <= end]
    if len(history_dates) < 12:
        return None

    transformed = []
    for d in history_dates:
        v = fn(series, d)
        if v is not None:
            transformed.append(v)
    if len(transformed) < 12:
        return None

    s = pd.Series(transformed)
    deltas = s.diff().dropna()
    if len(deltas) < 12 or deltas.std() == 0:
        return None
    return float(deltas.iloc[-1] / deltas.std())


def level_zscore(
    series: pd.Series,
    target: pd.Timestamp,
    transform: str,
    lookback_years: int = 5,
) -> float | None:
    """Compute the z-score of the LATEST transformed value against the
    trailing N years of that same transform: ``(latest - mean) / std``.

    "Is the current *level* unusual" — the right question when the anchor
    transform is stationary (a rate or a YoY%: unemployment rate, job-
    openings rate, sentiment index). Do NOT use this with a raw,
    non-stationary level (e.g. a price index): every print would read ~+2σ
    because the level only trends up. ``delta_zscore`` answers the
    move-unusual question instead.
    """
    if transform not in TRANSFORMS:
        raise KeyError(f"Unknown transform: {transform!r}")
    fn = TRANSFORMS[transform]

    end = target
    start = target - pd.DateOffset(years=lookback_years)
    history_dates = [d for d in series.index if start <= d <= end]
    if len(history_dates) < 12:
        return None

    transformed = []
    for d in history_dates:
        v = fn(series, d)
        if v is not None:
            transformed.append(v)
    if len(transformed) < 12:
        return None

    s = pd.Series(transformed)
    if s.std() == 0:
        return None
    return float((s.iloc[-1] - s.mean()) / s.std())
