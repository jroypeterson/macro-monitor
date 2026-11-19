"""Drug-price YoY must pair each month with the same month a year earlier.

Codex 2026Q4 #3: `_yoy` was `dropna().pct_change(12)`. BLS published no
October 2025 CPI, so for twelve months after the gap the CPI line was a
13-month change. No network: pure transform tests."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from macro_monitor import drugprices as D

REPO = Path(D.__file__).parent


def _monthly(n=30, start="2024-01-01"):
    idx = pd.date_range(start, periods=n, freq="MS")
    return pd.Series([100.0 * (1.01 ** i) for i in range(n)], index=idx)


def test_gap_month_is_not_bridged_to_thirteen_months():
    s = _monthly()
    gap = pd.Timestamp("2024-10-01")
    gapped = s.drop(gap)
    yoy = D._yoy(gapped)
    # 12 months after the gap has no partner -> absent, never a 13-month change.
    assert pd.Timestamp("2025-10-01") not in yoy.index
    # The month after the gap equals the true 12-month change.
    nov = pd.Timestamp("2025-11-01")
    assert yoy[nov] == pytest.approx((s[nov] / s[pd.Timestamp("2024-11-01")] - 1) * 100)
    for d in yoy.index:
        assert yoy[d] == pytest.approx((1.01 ** 12 - 1) * 100)


def test_gap_free_series_matches_pct_change_12():
    s = _monthly()
    expected = (s.pct_change(12) * 100).dropna()
    pd.testing.assert_series_equal(D._yoy(s), expected, check_names=False)


def test_no_module_uses_positional_yoy():
    # Code form only (`x.dropna().pct_change(`); docstrings quote it in backticks.
    pat = re.compile(r"\w\.dropna\(\)\.pct_change\(")
    offenders = [str(p.relative_to(REPO)) for p in REPO.rglob("*.py")
                 if "tests" not in p.parts and pat.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
