"""Release-schedule footnotes for the Ahead-of-the-Curve charts.

For each chart's headline (numerator) series, work out: how often it publishes, the
latest period we have, when the next data point is expected (FRED's scheduled release
date), and which period that release will cover. Reuses the FRED release-date calendar
(the same release_calendar_ids macro_monitor's weekly preview uses).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..collectors.fred import FREDClient
from .charts import FigureSpec, _infer_periods_per_year

# FRED series -> the FRED release that publishes it (release_id).
SERIES_RELEASE_ID: dict[str, int] = {
    "PCE": 54, "PCEPI": 54, "PSAVERT": 54,  # Personal Income & Outlays
    "PNFI": 53, "GDPDEF": 53, "GDP": 53,    # Gross Domestic Product
    "CE16OV": 50, "AHETPI": 50, "UNRATE": 50,  # Employment Situation
    "CPIAUCSL": 10,                         # Consumer Price Index
    "FEDFUNDS": 18, "GS10": 18,             # H.15 Selected Interest Rates
    "IPMAN": 14, "INDPRO": 14,              # G.17 Industrial Production
    "UMCSENT": 175,                         # U. Michigan Consumer Sentiment
}
RELEASE_NAME: dict[int, str] = {
    54: "Personal Income & Outlays", 53: "GDP", 50: "Employment Situation",
    10: "CPI", 18: "H.15 Selected Interest Rates", 14: "Industrial Production (G.17)",
    175: "U. Michigan Consumer Sentiment",
}
_FREQ = {52: "weekly", 12: "monthly", 4: "quarterly", 1: "annual"}


def _next_period(latest: pd.Timestamp, periods_per_year: int) -> pd.Timestamp:
    """The reference period the NEXT release will cover = latest period + one step."""
    if periods_per_year == 4:
        return latest + pd.DateOffset(months=3)
    if periods_per_year == 1:
        return latest + pd.DateOffset(years=1)
    return latest + pd.DateOffset(months=1)


def next_release_dates(
    client: FREDClient, release_ids: set[int], today: date | None = None
) -> dict[int, date | None]:
    """{release_id: the next future scheduled release date, or None if unavailable}."""
    today = today or date.today()
    iso = today.isoformat()
    out: dict[int, date | None] = {}
    for rid in release_ids:
        try:
            dates = client.get_release_dates(
                release_id=rid, realtime_start=iso, realtime_end="9999-12-31",
                include_release_dates_with_no_data=True,
            )
            future = sorted(d.date for d in dates if d.date > today)
            out[rid] = future[0] if future else None
        except Exception:  # noqa: BLE001 — schedule is a nicety; never break the build
            out[rid] = None
    return out


def figure_footnotes(
    figures: list[FigureSpec],
    fetched: dict[str, pd.Series],
    next_dates: dict[int, date | None],
) -> dict[str, list[str]]:
    """{figure_id: [one footnote line per headline series]}.

    Footnote form: "Real PCE: monthly · latest Apr 2026 · next release ~Jun 25, 2026
    (covers May 2026)". Deflator series (divide_by) are omitted — the numerator is the
    economic series that drives the data point."""
    out: dict[str, list[str]] = {}
    for f in figures:
        lines: list[str] = []
        seen: set[str] = set()
        for s in f.series:
            sid = s.fred
            if sid in seen:
                continue
            seen.add(sid)
            base = fetched.get(sid)
            if base is None or base.dropna().empty:
                continue
            ppy = _infer_periods_per_year(base)
            freq = _FREQ.get(ppy, "periodic")
            latest = base.dropna().index.max()
            rid = SERIES_RELEASE_ID.get(sid)
            nd = next_dates.get(rid) if rid is not None else None
            cov = _next_period(latest, ppy)
            label = s.label.split(" — ")[0]  # trim the "— Δ (pp)" suffix on accel labels
            if rid == 18:  # H.15 rates publish each business day; period is the monthly avg
                lines.append(f"{label}: monthly average (H.15 updates each business day) "
                             f"· latest {latest:%b %Y}")
            elif nd is not None:
                lines.append(f"{label}: {freq} · latest {latest:%b %Y} · "
                             f"next release ~{nd:%b %d, %Y} (covers {cov:%b %Y})")
            else:
                lines.append(f"{label}: {freq} · latest {latest:%b %Y}")
        out[f.id] = lines
    return out
