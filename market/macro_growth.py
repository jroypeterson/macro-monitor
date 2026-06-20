"""Year-over-year growth series — the data layer for the Markets "growth" views.

Six headline figures, all expressed as **YoY % change**, quarterly:

  • Real GDP                              — BEA (FRED GDPC1)
  • Real Consumer Spending (PCE)          — BEA (FRED PCECC96)
  • Industrial Production                 — Federal Reserve Board (FRED INDPRO)
  • Real Capital Spending (nonres FI)     — BEA (FRED PNFIC1)
  • S&P 500 Earnings per Share            — S&P 500 reported TTM EPS via multpl.com
  • Unemployment Rate                     — BLS (FRED UNRATE)

Plus a companion for the S&P 500 earnings view:
  • US Corporate Profits (after tax)      — BEA (FRED CP)  [whole-economy, NOT S&P 500]

This module only fetches + transforms; rendering lives in `growth_charts.py`.
Covers PROJECT_IDEAS #31 (trailing-3yr quarterly figures page) and the *actual*
half of #7 (S&P 500 earnings YoY + corporate-profits companion). The forward
S&P 500 EPS overlay (FactSet Earnings Insight weekly email) is a deferred
enhancement — see PROJECT_IDEAS.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from ..collectors.fred import FREDClient

_MIRROR = Path(__file__).parent / "data"
_UA = {"User-Agent": "Mozilla/5.0 (macro_monitor research; jroypeterson@gmail.com)"}

# multpl.com S&P 500 reported earnings (trailing-twelve-month EPS), monthly table.
_SP500_EPS_URL = "https://www.multpl.com/s-p-500-earnings/table/by-month"
# Date cell, then a value cell that may lead with an &nbsp;/en-space entity.
_ROW = re.compile(r"<td>([A-Z][a-z]{2} \d{1,2}, \d{4})</td>\s*<td>(?:\s|&[^;]+;)*([\d.]+)")


@dataclass(frozen=True)
class GrowthSeries:
    key: str
    label: str
    source: str            # agency label shown on the chart
    fred_id: str | None    # FRED series id, or None for multpl-sourced S&P 500 EPS
    note: str = ""


# Order matches JP's #31 list.
SERIES: list[GrowthSeries] = [
    GrowthSeries("real_gdp", "Real GDP", "BEA", "GDPC1"),
    GrowthSeries("real_pce", "Real Consumer Spending (PCE)", "BEA", "PCECC96"),
    GrowthSeries("industrial_production", "Industrial Production", "Federal Reserve Board", "INDPRO"),
    GrowthSeries("real_capex", "Real Capital Spending (nonres. fixed investment)", "BEA", "PNFIC1"),
    GrowthSeries("sp500_eps", "S&P 500 Earnings per Share", "S&P 500 (multpl.com)", None),
    GrowthSeries("unemployment", "Unemployment Rate", "BLS", "UNRATE"),
]

# Companion series for the S&P 500 earnings view (#7).
CORPORATE_PROFITS = GrowthSeries(
    "corporate_profits", "US Corporate Profits (after tax)", "BEA", "CP",
    note="Whole-economy corporate profits — a macro complement to S&P 500 EPS, not the same thing.",
)


def to_quarterly(s: pd.Series) -> pd.Series:
    """Collapse any (monthly/quarterly) series to quarter-end observations.

    Monthly series (industrial production, unemployment) take the quarter's
    last monthly value so a quarterly YoY is well-defined; already-quarterly
    series (GDP, PCE, capex, profits) are unchanged in substance.
    """
    return s.dropna().resample("QE").last().dropna()


def yoy_pct(quarterly: pd.Series) -> pd.Series:
    """YoY % change of a quarterly series (vs the same quarter one year = 4q ago)."""
    q = quarterly.dropna()
    return ((q / q.shift(4) - 1.0) * 100.0).dropna()


def fetch_sp500_eps_multpl() -> pd.Series:
    """S&P 500 reported TTM EPS (monthly), 1871→present, from multpl.com.

    Same table shape as the CAPE scraper. Raises on fetch/parse failure so the
    caller can fall back to the mirror.
    """
    r = requests.get(_SP500_EPS_URL, headers=_UA, timeout=30)
    r.raise_for_status()
    rows = _ROW.findall(r.text)
    if len(rows) < 500:
        raise ValueError(f"multpl S&P 500 EPS parse returned only {len(rows)} rows")
    data = {pd.Timestamp(d).to_period("M").to_timestamp(): float(v) for d, v in rows}
    return pd.Series(data, name="sp500_eps").sort_index()


def _save_eps(s: pd.Series, mirror: Path = _MIRROR) -> None:
    today = date.today().isoformat()
    (mirror / "raw" / today).mkdir(parents=True, exist_ok=True)
    (mirror / "latest").mkdir(parents=True, exist_ok=True)
    csv = s.to_csv()
    (mirror / "raw" / today / "sp500_eps_multpl.csv").write_text(csv, encoding="utf-8")
    (mirror / "latest" / "sp500_eps_multpl.csv").write_text(csv, encoding="utf-8")


def load_sp500_eps(mirror: Path = _MIRROR, prefer_live: bool = True) -> pd.Series:
    """Current S&P 500 TTM EPS: live multpl (cached to mirror) → mirrored CSV."""
    if prefer_live:
        try:
            s = fetch_sp500_eps_multpl()
            _save_eps(s, mirror)
            return s
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] live S&P 500 EPS fetch failed ({exc}); falling back to mirror")
    csv = mirror / "latest" / "sp500_eps_multpl.csv"
    if csv.exists():
        return pd.read_csv(csv, index_col=0, parse_dates=True).iloc[:, 0].dropna()
    raise RuntimeError("S&P 500 EPS unavailable (live fetch failed and no mirror present)")


def _raw_series(
    spec: GrowthSeries, client: FREDClient | None, prefer_live: bool
) -> pd.Series:
    """The underlying level series for one spec (pre-YoY), as a dated pd.Series."""
    if spec.fred_id is None:  # multpl-sourced S&P 500 EPS
        return load_sp500_eps(prefer_live=prefer_live)
    client = client or FREDClient()
    return client.get_observations(spec.fred_id)


def build_growth_series(
    specs: list[GrowthSeries] | None = None,
    *,
    client: FREDClient | None = None,
    prefer_live: bool = True,
) -> dict[str, pd.Series]:
    """Fetch + transform each spec to a quarterly YoY% series.

    Returns {key: yoy_series}. A spec that fails to fetch is skipped with a
    warning (no silent total failure) so one dead source doesn't blank the page.
    """
    specs = specs if specs is not None else SERIES
    client = client or FREDClient()
    out: dict[str, pd.Series] = {}
    for spec in specs:
        try:
            raw = _raw_series(spec, client, prefer_live)
            out[spec.key] = yoy_pct(to_quarterly(raw))
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] growth series {spec.key} failed: {type(exc).__name__}: {exc}")
    return out
