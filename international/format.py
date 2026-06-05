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
