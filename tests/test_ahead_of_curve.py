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


def test_resolve_end_release_anchor_keeps_newer_released_point():
    # H3: PCE's latest obs is May; a fresh Employment (PAYEMS) obs lands in June.
    # A release-thread rebuild for Employment must anchor the right edge to the
    # released family so its June point isn't cropped — NOT to PCE's stale May.
    from macro_monitor.ahead_of_curve.build import _resolve_end

    # Explicit indices so the anchor mismatch is unambiguous.
    pce = pd.Series(
        [1.0] * 5, index=pd.date_range("2026-01-01", periods=5, freq="MS"), dtype=float
    )  # latest = 2026-05-01
    payems = pd.Series(
        [1.0] * 6, index=pd.date_range("2026-01-01", periods=6, freq="MS"), dtype=float
    )  # latest = 2026-06-01 (newer)
    fetched = {"PCE": pce, "PAYEMS": payems}

    # Gallery build (default PCE anchor) → stable May right edge.
    assert _resolve_end(fetched, ("PCE",)) == pd.Timestamp("2026-05-01")
    # Employment release rebuild → June right edge, so the new point shows.
    assert _resolve_end(fetched, ("PAYEMS",)) == pd.Timestamp("2026-06-01")


def test_resolve_end_falls_back_when_anchor_missing():
    from macro_monitor.ahead_of_curve.build import _resolve_end

    other = pd.Series(
        [1.0] * 3, index=pd.date_range("2026-01-01", periods=3, freq="MS"), dtype=float
    )  # latest = 2026-03-01
    fetched = {"GS10": other}
    # Anchor series not fetched → newest date across all fetched series.
    assert _resolve_end(fetched, ("PCE",)) == pd.Timestamp("2026-03-01")


def test_yoy_pct_monthly_is_12_month_change():
    # 24 months: a clean +10% step exactly 12 months in.
    s = _monthly([100.0] * 12 + [110.0] * 12)
    out = yoy_pct(s)
    # The first defined YoY point is month 12 (index 12), = +10%.
    assert out.iloc[0] == pytest.approx(10.0)
    assert out.index[0] == s.index[12]


def test_yoy_pct_pairs_by_date_when_a_month_is_missing():
    """The October-2025 shape. BLS published no CPI that month, so CPIAUCSL and
    CE16OV each carry one hole; a ROW lag then reached back thirteen months for the
    twelve prints after it, and the published charts were wrong by up to 0.4pp on a
    chartpack whose whole subject is the rate of change.
    """
    s = _monthly([100.0 + i for i in range(30)])          # +1/month ramp
    gapped = s.drop(s.index[15])                          # one month vanishes
    out = yoy_pct(gapped)
    for ts, value in out.items():
        base_ts = ts - pd.DateOffset(years=1)
        assert base_ts in gapped.index
        assert value == pytest.approx((gapped[ts] / gapped[base_ts] - 1) * 100)


def test_yoy_pct_drops_the_point_whose_partner_is_missing():
    s = _monthly([100.0 + i for i in range(30)])
    missing = s.index[15]
    out = yoy_pct(s.drop(missing))
    assert missing not in out.index                        # the hole itself
    assert missing + pd.DateOffset(years=1) not in out.index   # and its partner


def test_yoy_accel_is_also_date_aligned():
    s = _monthly([100.0 * (1.01 ** i) for i in range(40)])
    gapped = s.drop(s.index[20])
    out = charts.yoy_accel(gapped)
    y = yoy_pct(gapped)
    for ts, value in out.items():
        assert value == pytest.approx(y[ts] - y[ts - pd.DateOffset(years=1)])


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


def test_key_takeaways_headline_and_bullets():
    from macro_monitor.ahead_of_curve.summary import key_takeaways

    # Real PCE accelerating: monthly growth rate rises every month -> YoY keeps rising
    # -> acceleration positive through the latest point.
    base = [100.0]
    for i in range(48):
        base.append(base[-1] * (1 + 0.0008 * i))
    pce = _monthly(base, start="2022-01-01")
    flat = _monthly([100.0] * len(base), start="2022-01-01")
    fetched = {"PCE": pce, "PCEPI": flat, "FEDFUNDS": _monthly([4.3] * 30, start="2024-01-01")}
    headline, bullets = key_takeaways(fetched)
    assert "leading indicator" in headline.lower()
    assert "accelerating" in headline
    assert any("real consumer spending" in b.lower() for b in bullets)
    assert any("fed funds" in b.lower() for b in bullets)


def test_key_takeaways_empty_when_no_data():
    from macro_monitor.ahead_of_curve.summary import key_takeaways

    headline, bullets = key_takeaways({})
    assert headline == "" and bullets == []


def test_series_average_lines_short_10y_full():
    from macro_monitor.ahead_of_curve.stats import series_average_lines

    s = _monthly([2.0 + (i % 12) * 0.0 for i in range(240)], start="2006-05-01")  # flat 2.0
    fig = FigureSpec(id="r", title="Rates", series=[
        charts.SeriesSpec(fred="GS10", label="10Y", transform="raw")])
    lines = series_average_lines(fig, {"GS10": s}, pd.Timestamp("2026-04-01"))
    assert len(lines) == 1
    assert "1-yr" in lines[0] and "10-yr" in lines[0] and "full-history" in lines[0]


def test_series_average_lines_skips_acceleration():
    from macro_monitor.ahead_of_curve.stats import series_average_lines

    s = _monthly([100.0 + i for i in range(60)])
    fig = FigureSpec(id="a", title="Accel", series=[
        charts.SeriesSpec(fred="PCE", label="x", transform="yoy_accel")])
    assert series_average_lines(fig, {"PCE": s}, s.index.max()) == []


def test_timeline_stat_lines_declines_and_durations():
    from macro_monitor.ahead_of_curve.stats import timeline_stat_lines

    # Two bear windows in a synthetic S&P that halves then recovers in each.
    idx = pd.date_range("1970-01-01", periods=240, freq="MS")
    vals = [100.0] * 240
    for i in range(12, 18):   # ~-40% dip
        vals[i] = 60.0
    for i in range(120, 126):  # ~-25% dip
        vals[i] = 75.0
    sp = pd.Series(vals, index=idx, dtype=float)
    bears = [charts.BearMarket(pd.Timestamp("1971-01-01"), pd.Timestamp("1971-06-01"), "A"),
             charts.BearMarket(pd.Timestamp("1980-01-01"), pd.Timestamp("1980-06-01"), "B")]
    recs = [(pd.Timestamp("1970-01-01"), pd.Timestamp("1970-11-01")),
            (pd.Timestamp("1973-11-01"), pd.Timestamp("1975-03-01"))]
    lines = timeline_stat_lines(bears, recs, sp)
    assert any("bear markets" in ln.lower() and "peak-to-trough" in ln.lower() for ln in lines)
    assert any("recessions" in ln.lower() and "duration" in ln.lower() for ln in lines)
    assert any("deepest" in ln and "shallowest" in ln for ln in lines)


def test_config_files_present_and_valid():
    import yaml
    d = Path(__file__).parent.parent / "ahead_of_curve"
    figs, _ = parse_figures(yaml.safe_load((d / "figures.yaml").read_text(encoding="utf-8")))
    bears = parse_bear_markets(yaml.safe_load((d / "bear_markets.yaml").read_text(encoding="utf-8")))
    assert len(figs) >= 16, "5 MVP + 3 acceleration + Phase-3 figures + timeline"
    accel = [f for f in figs if any(s.transform == "yoy_accel" for s in f.series)]
    assert len(accel) == 3, "PCE, capex, real-earnings acceleration charts"
    timelines = [f for f in figs if not f.series]
    assert len(timelines) == 1, "the bands-only bear/recession timeline"
    assert len(bears) >= 12, "bear list extended back to the post-war era"


def test_timeline_renders_without_series(tmp_path):
    # A bands-only figure (no economic series) must render as a valid timeline.
    fig = FigureSpec(id="tl", title="Timeline", bands="both", lookback_years=50, series=[])
    bears = [charts.BearMarket(pd.Timestamp("1973-01-01"), pd.Timestamp("1974-10-01"), "")]
    recs = [(pd.Timestamp("1980-01-01"), pd.Timestamp("1980-07-01"))]
    out = render_figure(fig, {}, bears, recs, pd.Timestamp("2026-04-01"),
                        tmp_path / "tl.png", "note")
    assert out.exists() and out.stat().st_size > 1000


def test_dual_axis_renders_with_right_axis_series(tmp_path):
    # A figure with a right-axis log S&P-style series renders (twinx path).
    left = _monthly([100.0 + i for i in range(120)], start="2016-01-01")
    sp = _monthly([2000.0 * (1.01 ** i) for i in range(120)], start="2016-01-01")
    fetched = {"GS10": left, "GSPC": sp}
    fig = FigureSpec(
        id="dual", title="Dual", bands="both", lookback_years=8,
        series=[
            charts.SeriesSpec(fred="GS10", label="10Y", transform="raw"),
            charts.SeriesSpec(fred="GSPC", label="S&P 500", transform="raw",
                              unit="level", axis="right", scale="log"),
        ],
    )
    out = render_figure(fig, fetched, [], [], sp.index.max(), tmp_path / "dual.png", "n")
    assert out.exists() and out.stat().st_size > 1000


def test_sp500_overlay_figures_are_dual_axis():
    import yaml
    d = Path(__file__).parent.parent / "ahead_of_curve"
    figs, _ = parse_figures(yaml.safe_load((d / "figures.yaml").read_text(encoding="utf-8")))
    sp = [f for f in figs if any(s.fred == "GSPC" for s in f.series)]
    assert len(sp) == 3, "growth / real-earnings / long-rates vs stock market"
    for f in sp:
        right = [s for s in f.series if s.axis == "right"]
        assert right and right[0].scale == "log"


def test_unit_override_index_series(tmp_path):
    # An index-unit raw series renders with plain-number formatting (no % suffix).
    from macro_monitor.ahead_of_curve.charts import _fmt_value, _plot_series
    s = _monthly([70.0 + i * 0.1 for i in range(40)])
    spec = charts.SeriesSpec(fred="UMCSENT", label="Sentiment", transform="raw", unit="index")
    vals, unit = _plot_series(spec, {"UMCSENT": s})
    assert unit == "index"
    assert _fmt_value(72.3, "index") == "72.3"
    assert _fmt_value(2.1, "pct") == "2.1%"


def test_gallery_renders_glossary(tmp_path):
    # The bottom-of-page glossary is injected regardless of which figures render,
    # so an empty-figure render still carries it (no network needed).
    from macro_monitor.ahead_of_curve import build
    out = tmp_path / "index.html"
    build._render_gallery_html([], {}, out, "data through 2026-06-05", {}, "", [])
    html = out.read_text(encoding="utf-8")
    assert 'id="glossary"' in html
    assert "Glossary of terms" in html            # TOC link
    assert "Year-over-year (YoY) rate of change" in html
    assert "S&amp;P 500 bear markets" in html
