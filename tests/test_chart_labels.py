"""Point-label formatting for time-series charts.

The value labels on the curve must show meaningful significant figures — an
index reading like UMich 52.7 should NOT round to a bare "53" — and percents
get one decimal. Locks `_fmt_point_value` (the "denote significant figures"
fix) + that label_extremes adds peak/trough annotations.
"""

from __future__ import annotations

import pandas as pd

from macro_monitor.charts.timeseries import _fmt_point_value, _render_line_into


def test_raw_index_keeps_a_decimal():
    # UMich-scale: keep the decimal rather than rounding to an integer.
    assert _fmt_point_value(52.7, "raw") == "52.7"
    assert _fmt_point_value(6.52, "raw") == "6.5"   # mortgage-rate scale


def test_raw_large_count_drops_decimals_and_commas():
    assert _fmt_point_value(224500.0, "raw") == "224,500"


def test_percent_transforms_get_one_decimal():
    assert _fmt_point_value(3.78, "yoy_pct") == "3.8%"
    assert _fmt_point_value(-1.43, "qoq_pct_saar") == "-1.4%"
    assert _fmt_point_value(2.1, "yoy_pct_weekly") == "2.1%"


class _FakeSeriesRef:
    def __init__(self, sid, transform, label):
        self.id, self.transform, self.label = sid, transform, label


def test_label_extremes_annotates_peak_and_trough():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    idx = pd.date_range("2020-01-01", periods=24, freq="MS")
    vals = [50, 55, 60, 100, 70, 40, 45, 52, 58, 62, 30, 48,
            51, 53, 57, 61, 49, 47, 44, 46, 54, 56, 59, 52.7]
    series = {"X": pd.Series(vals, index=idx, dtype=float)}
    refs = [_FakeSeriesRef("X", "raw", "X")]

    fig, ax = plt.subplots()
    _render_line_into(refs, True, series, idx.min(), idx.max(), ax, label_extremes=True)
    texts = {t.get_text() for t in ax.texts}
    plt.close(fig)
    # latest (52.7), peak (100) and trough (30) all labeled with sig-figs.
    assert "52.7" in texts          # highlight_latest
    assert "100.0" in texts or "100" in texts  # peak
    assert "30.0" in texts          # trough
