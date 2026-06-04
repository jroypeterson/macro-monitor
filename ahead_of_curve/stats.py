"""Footnote statistics for the gallery:

1. Per-chart trailing averages (short-term 1-yr / 10-yr / full-history) of each plotted
   series — added below the non-acceleration charts.
2. Timeline statistics — average/min/max S&P 500 peak-to-trough bear-market decline and
   average/min/max NBER recession duration — added below the bear/recession timeline.
"""
from __future__ import annotations

import pandas as pd

from .charts import BearMarket, FigureSpec, _fmt_value, _plot_series


def _is_acceleration(fig: FigureSpec) -> bool:
    return bool(fig.series) and all(s.transform == "yoy_accel" for s in fig.series)


def series_average_lines(fig: FigureSpec, fetched: dict[str, pd.Series],
                         end: pd.Timestamp) -> list[str]:
    """One line per plotted series: short-term (1-yr), 10-yr, and full-history averages.
    Skipped for the acceleration charts and the bands-only timeline."""
    if _is_acceleration(fig) or not fig.series:
        return []
    lines: list[str] = []
    for s in fig.series:
        values, unit = _plot_series(s, fetched)
        values = values.dropna()
        values = values[values.index <= end]
        if values.empty:
            continue

        def _avg(years: int) -> float | None:
            window = values[values.index >= end - pd.DateOffset(years=years)]
            return float(window.mean()) if len(window) else None

        a1, a10 = _avg(1), _avg(10)
        afull = float(values.mean())
        parts = []
        if a1 is not None:
            parts.append(f"1-yr {_fmt_value(a1, unit)}")
        if a10 is not None:
            parts.append(f"10-yr {_fmt_value(a10, unit)}")
        parts.append(f"full-history {_fmt_value(afull, unit)}")
        lines.append(f"{s.label}: " + " · ".join(parts))
    return lines


def _bear_declines(bears: list[BearMarket], sp500: pd.Series | None
                   ) -> list[tuple[BearMarket, float]]:
    """Peak-to-trough % decline of the S&P 500 within each bear-market window
    (max drawdown = min/max over the window). Only bears with S&P coverage."""
    out: list[tuple[BearMarket, float]] = []
    if sp500 is None or sp500.dropna().empty:
        return out
    s = sp500.dropna()
    for b in bears:
        win = s[(s.index >= b.start) & (s.index <= b.end)]
        if len(win) >= 2 and float(win.max()) > 0:
            out.append((b, float(win.min()) / float(win.max()) - 1.0))
    return out


def timeline_stat_lines(bears: list[BearMarket],
                        recessions: list[tuple[pd.Timestamp, pd.Timestamp]],
                        sp500: pd.Series | None) -> list[str]:
    lines: list[str] = []

    declines = _bear_declines(bears, sp500)
    if declines:
        vals = [d for _, d in declines]
        avg = sum(vals) / len(vals)
        deepest = min(declines, key=lambda x: x[1])   # most negative
        shallowest = max(declines, key=lambda x: x[1])
        lines.append(
            f"<b>S&amp;P 500 bear markets ({len(declines)} with price data):</b> "
            f"average peak-to-trough decline {avg * 100:.0f}% · "
            f"deepest {deepest[1] * 100:.0f}% ({deepest[0].name}) · "
            f"shallowest {shallowest[1] * 100:.0f}% ({shallowest[0].name})."
        )

    if recessions:
        # Inclusive month count (peak month through trough month), so a one-month
        # flag reads as 1, not 0.
        months = [
            (b.to_period("M") - a.to_period("M")).n + 1 for a, b in recessions
        ]
        avg = sum(months) / len(months)
        lines.append(
            f"<b>NBER recessions ({len(recessions)} since {min(a for a, _ in recessions):%Y}):</b> "
            f"average duration {avg:.0f} months · shortest {min(months)} · longest {max(months)}."
        )
    return lines
