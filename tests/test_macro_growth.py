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
