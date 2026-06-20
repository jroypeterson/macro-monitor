"""Tests for the FactSet Earnings Insight forward-consensus parser.

Locks the regex extraction against FactSet's actual report phrasings, the
Friday-URL date logic, and the quarter→timestamp mapping. No network/PDF I/O.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from macro_monitor.market import factset_forward as FF

# Verbatim phrasings from the 2026-06-12 Earnings Insight.
_SAMPLE = (
    "Earnings Growth: For Q2 2026, the estimated (year-over-year) earnings growth "
    "rate for the S&P 500 is 21.9%. ... Looking ahead, For Q3 2026 and Q4 2026, "
    "analysts are calling for earnings growth rates of 25.3% and 22.8%. For CY 2026, "
    "analysts are predicting (year-over-year) earnings growth of 23.2%. For CY 2027, "
    "analysts are projecting earnings growth of 16.2% and revenue growth of 7.6%. "
    "The forward 12-month P/E ratio is 20.1 (based on Wednesday's closing price)."
)


def test_parse_forward_text_extracts_quarters_cy_and_pe():
    out = FF.parse_forward_text(_SAMPLE)
    assert out["quarters"] == {"Q2 2026": 21.9, "Q3 2026": 25.3, "Q4 2026": 22.8}
    assert out["cy"] == {"2026": 23.2, "2027": 16.2}
    assert out["forward_pe"] == 20.1


def test_parse_forward_text_handles_line_wrapped_whitespace():
    # Real PDF text comes with newlines/double spaces mid-sentence.
    wrapped = _SAMPLE.replace(". ", ".\n  ").replace(", ", ",\n")
    out = FF.parse_forward_text(wrapped)
    assert out["quarters"]["Q3 2026"] == 25.3
    assert out["cy"]["2026"] == 23.2


def test_parse_forward_text_raises_on_format_change():
    with pytest.raises(ValueError):
        FF.parse_forward_text("Some unrelated report text with no growth figures.")


def test_recent_fridays_most_recent_first():
    # 2026-06-19 is a Friday → it's first, then weekly back.
    fr = FF.recent_fridays(date(2026, 6, 19), n=3)
    assert fr == [date(2026, 6, 19), date(2026, 6, 12), date(2026, 6, 5)]
    assert all(d.weekday() == 4 for d in fr)


def test_recent_fridays_from_midweek_walks_back_to_prior_friday():
    # Wednesday 2026-06-17 → most recent Friday is 2026-06-12.
    assert FF.recent_fridays(date(2026, 6, 17), n=1) == [date(2026, 6, 12)]


def test_quarter_to_ts_and_series():
    assert FF.quarter_to_ts("Q2 2026") == pd.Timestamp("2026-06-30")
    s = FF.forward_quarterly_series({"quarters": {"Q4 2026": 22.8, "Q2 2026": 21.9}})
    # sorted ascending by quarter-end date
    assert list(s.index) == [pd.Timestamp("2026-06-30"), pd.Timestamp("2026-12-31")]
    assert list(s.values) == [21.9, 22.8]
