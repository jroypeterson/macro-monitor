"""Tests for the Ahead-of-the-Curve chart module: the YoY/deflate math, band
parsing, recession-range collapsing, figure-config parsing, and a render smoke
test (no network — synthetic series in, PNG out)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from macro_monitor.ahead_of_curve import charts
from macro_monitor.ahead_of_curve.charts import (
    FigureSpec,
    parse_bear_markets,
    parse_figures,
    real_deflate,
    recession_ranges,
    render_figure,
    yoy_pct,
)


def _monthly(values, start="2000-01-01"):
    idx = pd.date_range(start=start, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


def test_yoy_pct_monthly_is_12_month_change():
    # 24 months: a clean +10% step exactly 12 months in.
    s = _monthly([100.0] * 12 + [110.0] * 12)
    out = yoy_pct(s)
    # The first defined YoY point is month 12 (index 12), = +10%.
    assert out.iloc[0] == pytest.approx(10.0)
    assert out.index[0] == s.index[12]


def test_infer_periods_per_year():
    monthly = _monthly([1.0] * 30)
    quarterly = pd.Series(range(20), index=pd.date_range("2000-01-01", periods=20, freq="QS"), dtype=float)
    assert charts._infer_periods_per_year(monthly) == 12
    assert charts._infer_periods_per_year(quarterly) == 4


def test_real_deflate_divides_and_rebases():
    nominal = _monthly([100.0, 110.0, 121.0])
    deflator = _monthly([100.0, 100.0, 100.0])
    real = real_deflate(nominal, deflator)
    # Rebased to 100 at first point; constant deflator => mirrors nominal growth.
    assert real.iloc[0] == pytest.approx(100.0)
    assert real.iloc[2] == pytest.approx(121.0)


def test_real_deflate_strips_inflation():
    # Nominal and deflator rise together => real is flat.
    nominal = _monthly([100.0, 105.0, 110.25])
    deflator = _monthly([100.0, 105.0, 110.25])
    real = real_deflate(nominal, deflator)
    assert real.iloc[-1] == pytest.approx(100.0)


def test_parse_bear_markets():
    bears = parse_bear_markets({"bear_markets": [
        {"start": "1973-01", "end": "1974-10", "name": "1973-74"},
    ]})
    assert len(bears) == 1
    assert bears[0].start == pd.Timestamp("1973-01-01")
    assert bears[0].name == "1973-74"


def test_recession_ranges_collapses_runs():
    # 0,0,1,1,0,1 -> two ranges: months 2-3 and month 5 (open run to end).
    flags = _monthly([0, 0, 1, 1, 0, 1])
    ranges = recession_ranges(flags)
    assert len(ranges) == 2
    assert ranges[0][0] == flags.index[2]
    assert ranges[0][1] == flags.index[3]
    assert ranges[1][0] == flags.index[5]


def test_parse_figures_reads_series_and_divide_by():
    figs, note = parse_figures({
        "default_lookback_years": 40,
        "source_note": "src",
        "figures": [
            {"id": "f1", "title": "T1", "bands": "bear", "series": [
                {"fred": "PCE", "divide_by": "PCEPI", "label": "Real PCE", "transform": "yoy"},
            ]},
        ],
    })
    assert note == "src"
    assert figs[0].id == "f1"
    assert figs[0].lookback_years == 40
    assert figs[0].series[0].divide_by == "PCEPI"
    assert figs[0].fred_ids() == {"PCE", "PCEPI"}


def test_render_figure_smoke(tmp_path):
    # Synthetic 30y monthly series, a yoy figure with one bear band -> PNG exists.
    s = _monthly([100.0 + i for i in range(360)], start="1996-01-01")
    fetched = {"PCE": s, "PCEPI": _monthly([100.0] * 360, start="1996-01-01")}
    fig = FigureSpec(
        id="t", title="Test", subtitle="sub", bands="bear", lookback_years=20,
        series=[charts.SeriesSpec(fred="PCE", divide_by="PCEPI", label="Real", transform="yoy")],
    )
    bears = [charts.BearMarket(pd.Timestamp("2008-10-01"), pd.Timestamp("2009-03-01"), "GFC")]
    out = render_figure(fig, fetched, bears, [], s.index.max(), tmp_path / "t.png", "note")
    assert out.exists() and out.stat().st_size > 1000


def test_yoy_accel_sign_tracks_acceleration():
    from macro_monitor.ahead_of_curve.charts import yoy_accel
    # Build a series whose YoY growth steadily accelerates, then decelerates.
    # 48 months: first 24 grow at an increasing rate, last 24 at a decreasing rate.
    vals = [100.0]
    rates = [0.005 * i for i in range(24)] + [0.005 * (24 - i) for i in range(24)]
    for r in rates:
        vals.append(vals[-1] * (1 + r))
    s = _monthly(vals)
    accel = yoy_accel(s)
    # Acceleration is positive while growth is speeding up, negative while slowing.
    assert (accel.iloc[: len(accel) // 2] > 0).mean() > 0.7
    assert accel.iloc[-1] < 0


def test_figure_footnotes_report_cadence_next_release_and_period():
    from datetime import date

    from macro_monitor.ahead_of_curve.schedule import figure_footnotes

    pce = _monthly([100.0 + i for i in range(40)], start="2023-01-01")  # latest = Apr 2026
    capex = pd.Series(range(20), index=pd.date_range("2021-04-01", periods=20, freq="QS"), dtype=float)
    fetched = {"PCE": pce, "PCEPI": pce, "PNFI": capex, "GDPDEF": capex}
    figs, _ = parse_figures({"figures": [
        {"id": "f", "title": "T", "series": [
            {"fred": "PCE", "divide_by": "PCEPI", "label": "Real PCE (YoY)", "transform": "yoy"},
            {"fred": "PNFI", "divide_by": "GDPDEF", "label": "Real Capex (YoY)", "transform": "yoy"},
        ]},
    ]})
    next_dates = {54: date(2026, 6, 25), 53: date(2026, 6, 25)}
    foot = figure_footnotes(figs, fetched, next_dates)["f"]
    assert len(foot) == 2  # one per numerator series; deflators omitted
    assert "monthly" in foot[0] and "next release ~Jun 25, 2026" in foot[0]
    assert "covers May 2026" in foot[0]      # latest Apr + 1 month
    assert "quarterly" in foot[1] and "covers" in foot[1]


def test_config_files_present_and_valid():
    import yaml
    d = Path(__file__).parent.parent / "ahead_of_curve"
    figs, _ = parse_figures(yaml.safe_load((d / "figures.yaml").read_text(encoding="utf-8")))
    bears = parse_bear_markets(yaml.safe_load((d / "bear_markets.yaml").read_text(encoding="utf-8")))
    assert len(figs) == 8, "MVP 5 + 3 acceleration charts"
    accel = [f for f in figs if any(s.transform == "yoy_accel" for s in f.series)]
    assert len(accel) == 3, "PCE, capex, real-earnings acceleration charts"
    assert len(bears) >= 8, "expected the curated bear-market list"
