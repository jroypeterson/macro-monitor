"""Tests for the factor period-return table (pure logic; no network)."""
from __future__ import annotations

import pytest

from macro_monitor.market import factor_returns as fr


def test_shift_month_crosses_year_boundaries():
    assert fr._shift_month(202605, -11) == 202506
    assert fr._shift_month(202601, -1) == 202512
    assert fr._shift_month(202612, 1) == 202701
    assert fr._shift_month(202603, 0) == 202603


def test_months_between_is_inclusive_across_years():
    assert fr._months_between(202511, 202602) == [202511, 202512, 202601, 202602]
    assert fr._months_between(202605, 202605) == [202605]


def test_cumulative_compounds_percent_returns():
    factors = {202601: {"HML": 10.0}, 202602: {"HML": 10.0}}
    # (1.10 * 1.10 - 1) * 100 == 21.0
    assert fr._cumulative(factors, "HML", [202601, 202602]) == pytest.approx(21.0)


def test_cumulative_skips_missing_and_returns_none_when_empty():
    factors = {202601: {"HML": 5.0}}
    # 202602 missing -> skipped, only 202601 counts
    assert fr._cumulative(factors, "HML", [202601, 202602]) == pytest.approx(5.0)
    assert fr._cumulative(factors, "HML", [209901]) is None


def test_period_months_qtd_ytd_trailing():
    p = fr._period_months(202605)  # May 2026 -> Q2
    assert p["QTD"] == [202604, 202605]
    assert p["2026 YTD"] == [202601, 202602, 202603, 202604, 202605]
    assert p["Trailing 12m"][0] == 202506 and p["Trailing 12m"][-1] == 202605
    assert p["Latest mo"] == [202605]


def test_compute_table_covers_all_factor_rows():
    # Two synthetic months so every factor has data.
    rec = {"Mkt-RF": 1.0, "SMB": 1.0, "HML": 1.0, "RMW": 1.0,
           "CMA": 1.0, "RF": 0.3, "Mom": 1.0}
    factors = {202601: dict(rec), 202602: dict(rec)}
    table = fr.compute_table(factors)
    assert table["latest"] == 202602
    labels = {label for _key, label, _vals in table["rows"]}
    assert "Momentum (UMD)" in labels and "Value (HML)" in labels
    # 7 factor rows (FF5 + momentum + RF)
    assert len(table["rows"]) == 7


def test_render_markdown_has_header_and_rows():
    factors = {202601: {"Mkt-RF": 2.0, "SMB": 0.0, "HML": 0.0, "RMW": 0.0,
                        "CMA": 0.0, "RF": 0.3, "Mom": 0.0}}
    md = fr.render_markdown(fr.compute_table(factors))
    assert "# Fundamental factor performance" in md
    assert "| Factor |" in md
    assert "Market (excess)" in md


def test_compute_table_raises_on_empty():
    with pytest.raises(RuntimeError):
        fr.compute_table({})


@pytest.mark.skipif(
    not (fr._LATEST / fr._FF5).exists(),
    reason="mirrored Ken French files not present (data/latest is gitignored)",
)
def test_real_parser_reads_recent_months():
    factors = fr.load_factors()
    assert factors, "expected parsed factor data"
    # The mirror should carry recent months with the core columns populated.
    latest = max(factors)
    assert latest >= 202512
    row = factors[latest]
    assert "Mkt-RF" in row and "Mom" in row
