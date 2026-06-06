"""Tests for the Slack publisher's basis-label disambiguation.

A bare "4.30%" in the channel is ambiguous — is it a YoY rate, a level, a
MoM change? `basis_label` appends an explicit basis so the reader always
knows. These tests lock the derived defaults + the per-series override and
prove the disambiguation shows up in the rendered headline line.
"""

from __future__ import annotations

from macro_monitor.publishers.slack import _format_headline_line, basis_label
from macro_monitor.release_runner import HeadlineSeriesResult, TransformedValue


def test_basis_label_derives_default_from_transform():
    assert basis_label("yoy_pct") == "YoY"
    assert basis_label("mom_pct") == "MoM"
    assert basis_label("annualized_mom") == "ann. rate"
    assert basis_label("mom_chg") == "MoM chg"
    assert basis_label("qoq_pct_saar") == "QoQ SAAR"
    assert basis_label("raw") == "(level)"


def test_basis_label_unknown_transform_falls_back_to_name():
    # No silent drop — unknown transform surfaces its own name as the basis.
    assert basis_label("wibble") == "wibble"


def test_basis_label_override_wins():
    # Per-series override always beats the derived default.
    assert basis_label("raw", "level") == "level"
    assert basis_label("raw", "rate") == "rate"
    assert basis_label("annualized_mom", "MoM annualized") == "MoM annualized"


def _headline(label, transform, value, *, basis=None, also=None, unit=None):
    return HeadlineSeriesResult(
        id="X",
        label=label,
        primary=TransformedValue(transform=transform, value=value),
        also_display=[
            TransformedValue(transform=t, value=v) for t, v in (also or [])
        ],
        prior_primary=None,
        display_unit=unit,
        basis=basis,
    )


def test_unemployment_rate_reads_as_level():
    h = _headline("Unemployment rate", "raw", 4.30, basis="level", unit="%")
    line = _format_headline_line(h, h.display_unit)
    assert line == "Unemployment rate: 4.30% level"


def test_payrolls_reads_change_with_yoy_in_parens():
    h = _headline(
        "Nonfarm payrolls",
        "mom_chg",
        172.0,
        basis="MoM chg",
        also=[("yoy_pct", 0.32)],
        unit="K",
    )
    line = _format_headline_line(h, h.display_unit)
    assert line == "Nonfarm payrolls: +172K MoM chg (+0.32% YoY)"


def test_default_basis_used_when_no_override():
    # A yoy_pct headline with no explicit basis still gets a basis label.
    h = _headline("Total comp", "yoy_pct", 3.50)
    line = _format_headline_line(h, h.display_unit)
    assert line == "Total comp: +3.50% YoY"
