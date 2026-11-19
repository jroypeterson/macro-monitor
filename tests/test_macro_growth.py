"""Tests for the YoY growth data layer (market/macro_growth.py).

Covers the transforms (quarterly collapse + YoY%), the multpl.com S&P 500 EPS
parse, and the build orchestration's graceful per-series skip. No live calls.
"""

from __future__ import annotations

import pandas as pd
import pytest

from macro_monitor.market import macro_growth as G


def _quarters(values, start="2023Q1"):
    idx = pd.period_range(start=start, periods=len(values), freq="Q").to_timestamp(how="end").normalize()
    return pd.Series(values, index=idx, dtype=float)


def test_yoy_pct_is_four_quarter_change():
    s = _quarters([100, 101, 102, 103, 110, 90])
    yoy = G.yoy_pct(s)
    # 5th point (index 4) vs 1st (index 0): 110/100 - 1 = +10%
    assert yoy.iloc[0] == pytest.approx(10.0)
    # 6th (90) vs 2nd (101): 90/101 - 1 = -10.89%
    assert yoy.iloc[1] == pytest.approx((90 / 101 - 1) * 100, rel=1e-9)
    # first 4 quarters have no prior-year comparison -> dropped
    assert len(yoy) == 2


def test_to_quarterly_takes_quarter_end_of_monthly():
    idx = pd.date_range("2025-01-31", periods=6, freq="ME")
    s = pd.Series([1, 2, 3, 4, 5, 6], index=idx, dtype=float)
    q = G.to_quarterly(s)
    # Q1 2025 last month = Mar (=3), Q2 last = Jun (=6)
    assert list(q.values) == [3.0, 6.0]
    assert all(d.month in (3, 6, 9, 12) for d in q.index)


def test_fetch_sp500_eps_multpl_parses_rows(monkeypatch):
    # 500+ rows required by the guard; build a synthetic monthly table the regex
    # matches. Stay within pandas' Timestamp range (≤ ~2262) by using months.
    import calendar
    months = [calendar.month_abbr[m] for m in range(1, 13)]  # Jan..Dec
    html = "<table>" + "".join(
        f"<td>{months[i % 12]} 1, {1950 + i // 12}</td>\n<td>&#x2002;{10 + (i % 50)}.00</td>"
        for i in range(620)
    ) + "</table>"

    class _Resp:
        text = html
        def raise_for_status(self): pass

    monkeypatch.setattr(G.requests, "get", lambda *a, **k: _Resp())
    s = G.fetch_sp500_eps_multpl()
    assert len(s) >= 600
    assert s.index.is_monotonic_increasing  # sorted by date
    assert s.iloc[0] == pytest.approx(10.0)


def test_fetch_sp500_eps_multpl_raises_on_thin_parse(monkeypatch):
    class _Resp:
        text = "<td>Jan 1, 2020</td><td>10.0</td>"  # only 1 row
        def raise_for_status(self): pass

    monkeypatch.setattr(G.requests, "get", lambda *a, **k: _Resp())
    with pytest.raises(ValueError):
        G.fetch_sp500_eps_multpl()


def test_build_growth_series_skips_a_failing_source(monkeypatch):
    # FRED returns a usable quarterly series for everything except real_capex,
    # which raises — that one spec is skipped, the rest survive.
    good = _quarters([100, 101, 102, 103, 110, 112, 114, 116])

    class _FakeClient:
        def get_observations(self, series_id):
            if series_id == "PNFIC1":
                raise RuntimeError("boom")
            return good

    monkeypatch.setattr(G, "load_sp500_eps", lambda **k: good)
    out = G.build_growth_series(client=_FakeClient())
    assert "real_gdp" in out and "sp500_eps" in out
    assert "real_capex" not in out          # the failing source was skipped
    assert len(out) == len(G.SERIES) - 1
    # Every surviving series is a YoY% series (values, not levels):
    # last quarter (116) vs 4 quarters prior (103).
    assert out["real_gdp"].iloc[-1] == pytest.approx((116 / 103 - 1) * 100, rel=1e-9)


# ---- units: a rate changes in percentage points (Codex 2026Q4 #2) ----

def _monthly(values, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


def test_unemployment_yoy_is_percentage_points_not_relative_percent():
    """4.1% a year ago -> 4.4% now is +0.3pp. The published chart drew it +7.3%."""
    unrate = _monthly([4.1] * 12 + [4.4] * 12)          # Jan 2024 .. Dec 2025

    class _FakeClient:
        def get_observations(self, series_id):
            return unrate

    spec = next(s for s in G.SERIES if s.key == "unemployment")
    out = G.build_growth_series([spec], client=_FakeClient(), prefer_live=False)
    assert out["unemployment"].iloc[-1] == pytest.approx(0.3)


def test_gdp_spec_still_yields_percent():
    gdp = _quarters([100, 101, 102, 103, 110])

    class _FakeClient:
        def get_observations(self, series_id):
            return gdp

    spec = next(s for s in G.SERIES if s.key == "real_gdp")
    out = G.build_growth_series([spec], client=_FakeClient(), prefer_live=False)
    assert out["real_gdp"].iloc[-1] == pytest.approx(10.0)


def test_every_rate_series_declares_pp():
    for spec in G.SERIES:
        if spec.fred_id in G.RATE_SERIES:
            assert spec.unit == "pp", spec.key


def test_yoy_is_date_aligned_across_a_gap():
    """A missing quarter must not make the lag reach back five quarters."""
    s = _quarters([100, 101, 102, 103, 110, 111, 112, 113])
    gapped = s.drop(s.index[2])                          # 2023 Q3 missing
    yoy = G.yoy_pct(gapped)
    assert s.index[6] not in yoy.index                   # 2024 Q3 has no partner
    assert yoy[s.index[7]] == pytest.approx((113 / 103 - 1) * 100)
    pp = G.yoy_pp(gapped)
    assert pp[s.index[7]] == pytest.approx(10.0) and s.index[6] not in pp.index


def test_unfinished_quarter_of_monthly_series_is_dropped():
    s = _monthly([1, 2, 3, 4, 5])                        # Jan..May 2024
    q = G.to_quarterly(s)
    assert list(q.values) == [3.0]                       # Q2 (Apr-May only) dropped
    full = _monthly([1, 2, 3, 4, 5, 6])
    assert list(G.to_quarterly(full).values) == [3.0, 6.0]
    # Quarterly FRED series are dated quarter-START; never treat them as unfinished.
    qs = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2024-01-01", "2024-04-01", "2024-07-01"]))
    assert len(G.to_quarterly(qs)) == 3


def test_render_growth_bar_pp_labels(tmp_path, monkeypatch):
    from macro_monitor.market import growth_charts as GC
    seen: list[str] = []
    real_annotate = GC.plt.Axes.annotate

    def spy(self, text, *a, **k):
        seen.append(text)
        return real_annotate(self, text, *a, **k)

    monkeypatch.setattr(GC.plt.Axes, "annotate", spy)
    titles: list[str] = []
    real_title = GC.plt.Axes.set_title
    monkeypatch.setattr(GC.plt.Axes, "set_title",
                        lambda self, t, *a, **k: (titles.append(t), real_title(self, t, *a, **k))[1])
    GC.render_growth_bar(_quarters([0.3, -0.1]), "Unemployment Rate", "BLS",
                         tmp_path / "u.png", unit="pp")
    assert seen == ["+0.3pp", "-0.1pp"]
    assert "percentage points" in titles[0]
