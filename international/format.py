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


def fmt_change(result: IntlSeriesResult) -> str:
    """Small delta vs the prior observation, in the series' own units
    (percentage points for a rate). Empty string when no prior point."""
    ch = result.change
    if ch is None or abs(ch) < 10 ** (-result.decimals):
        return ""
    arrow = "▲" if ch > 0 else "▼"
    return f"{arrow}{abs(ch):.{result.decimals}f}"
