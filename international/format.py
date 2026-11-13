"""Shared formatting helpers for the Global macro digest + dashboard."""

from __future__ import annotations

from .model import IntlSeriesResult

_MON = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_period(period: str) -> str:
    """'2025-12' -> 'Dec 2025'; '2026-Q1' -> 'Q1 2026'; '2026' -> '2026';
    '2025-06-11' -> 'Jun 2025'."""
    parts = period.split("-")
    if len(parts) == 1:
        return period
    year = parts[0]
    if parts[1].startswith("Q"):
        return f"{parts[1]} {year}"
    try:
        m = int(parts[1])
        return f"{_MON[m]} {year}"
    except (ValueError, IndexError):
        return period


def fmt_value(result: IntlSeriesResult) -> str:
    lo = result.latest
    if lo is None:
        return "—"
    v = -lo.value if result.invert else lo.value
    return f"{v:.{result.decimals}f}{result.unit}"


def ytd_change_bps(result: IntlSeriesResult) -> float | None:
    """Year-to-date change in basis points: latest value minus the last
    observation of the prior calendar year (the year-end reference). None
    when the series has no prior-year point to anchor against."""
    lo = result.latest
    if lo is None:
        return None
    try:
        latest_year = int(lo.period[:4])
    except ValueError:
        return None
    base = None
    for o in result.observations:
        try:
            if int(o.period[:4]) < latest_year:
                base = o  # keep the last prior-year reading
        except ValueError:
            continue
    if base is None:
        return None
    return (lo.value - base.value) * 100.0


def fmt_bps(bps: float | None) -> str:
    if bps is None:
        return ""
    sign = "+" if bps >= 0 else "−"
    return f"{sign}{abs(bps):.0f}bps"


def fmt_change(result: IntlSeriesResult) -> str:
    """Small delta vs the prior observation, in the series' own units
    (percentage points for a rate). Empty string when no prior point."""
    ch = result.change
    if ch is None or abs(ch) < 10 ** (-result.decimals):
        return ""
    arrow = "▲" if ch > 0 else "▼"
    return f"{arrow}{abs(ch):.{result.decimals}f}"


def fmt_change_vs(result: IntlSeriesResult) -> str:
    """The change WITH what it is measured against: '▼0.1 pt vs Nov 2025'.
    A bare '▼0.1' left the reader guessing the unit and the base (JP
    2026-11-12). 'pt' = percentage points, used for % series only; an index
    carries no unit word."""
    prev = result.previous
    if prev is None:
        return ""
    delta = fmt_change(result)
    if not delta:
        return f"unchanged vs {fmt_period(prev.period)}"
    unit = " pt" if result.unit == "%" else ""
    return f"{delta}{unit} vs {fmt_period(prev.period)}"


def is_step_series(result: IntlSeriesResult) -> bool:
    """A daily policy rate is stored as the dates its LEVEL changed (see
    sources/boe.py), so its latest 'period' is the last move, not the last
    reading: it reads 'last changed', and an old date is not staleness."""
    return result.indicator == "policy_rate" and result.freq == "daily"


# How many months a reading may lag today before it is called stale. Normal
# publication lags sit well inside these (UK unemployment runs ~4 months).
_STALE_AFTER_MONTHS = {"daily": 1, "monthly": 5, "quarterly": 9, "annual": 30}


def months_behind(period: str, as_of: str) -> int | None:
    """Whole months from the END of `period` to `as_of` (YYYY-MM-DD)."""
    try:
        ay, am = int(as_of[:4]), int(as_of[5:7])
        parts = period.split("-")
        y = int(parts[0])
        if len(parts) == 1:
            m = 12
        elif parts[1].startswith("Q"):
            m = int(parts[1][1:]) * 3
        else:
            m = int(parts[1])
    except (ValueError, IndexError):
        return None
    return (ay - y) * 12 + (am - m)


def is_stale(result: IntlSeriesResult, as_of: str) -> bool:
    """True when the latest reading is older than the series' frequency
    allows. A retired dataset keeps answering with its last value, which
    looks healthy unless the period is checked against today."""
    lo = result.latest
    if lo is None or is_step_series(result):
        return False
    behind = months_behind(lo.period, as_of)
    limit = _STALE_AFTER_MONTHS.get(result.freq)
    return behind is not None and limit is not None and behind > limit
