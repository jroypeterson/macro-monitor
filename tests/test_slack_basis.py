"""Tests for the Slack publisher's basis-label disambiguation.

A bare "4.30%" in the channel is ambiguous — is it a YoY rate, a level, a
MoM change? `basis_label` appends an explicit basis so the reader always
knows. These tests lock the derived defaults + the per-series override and
prove the disambiguation shows up in the rendered headline line.
"""

from __future__ import annotations

from macro_monitor.publishers.slack import (
    _format_headline_line,
    _format_healthcare_components,
    basis_label,
)
from macro_monitor.release_runner import (
    ComponentSeriesResult,
    ComputedSeriesResult,
    HeadlineSeriesResult,
    ReleaseResult,
    TransformedValue,
)


def _hc_result():
    """A minimal ReleaseResult carrying one computed + one component HC series."""
    computed = ComputedSeriesResult(
        id="HC_TOTAL", label="Health Care employment (NAICS 621+622+623)",
        method="sum", inputs=[],
        transformed=TransformedValue(transform="yoy_pct", value=3.10),
        also_display=[], prior_primary=None, tags=["healthcare"],
    )
    component = ComponentSeriesResult(
        id="HOSP", label="Hospitals",
        transformed=TransformedValue(transform="yoy_pct", value=2.40),
        tags=["healthcare"],
    )
    return ReleaseResult(
        family_id="x", family_display_name="X", period="2026-04", period_label="April 2026",
        headline=[], components=[component], computed=[computed], context=None,
        source="fred", source_fetched_at="", latest_observation_period="2026-04",
        expected_observation_period="2026-04", is_stale=False, source_lag_minutes=None,
    )


def test_healthcare_context_lines_carry_basis_label():
    lines = _format_healthcare_components(_hc_result())
    # Every HC-context line now states its period — no bare unlabeled percent.
    assert lines[0] == "Health Care employment (NAICS 621+622+623): +3.10% YoY"
    assert lines[1] == "  ↳ Hospitals: +2.40% YoY"
    assert all("YoY" in ln for ln in lines)


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


# --- yoy_chg level-change context (fixing the "bare level" series) --------

def test_yoy_chg_basis_label():
    assert basis_label("yoy_chg") == "YoY chg"


def test_yoy_chg_is_signed():
    from macro_monitor.publishers.slack import _fmt_transformed
    pos = TransformedValue(transform="yoy_chg", value=0.20)
    neg = TransformedValue(transform="yoy_chg", value=-0.30)
    assert _fmt_transformed(pos, None) == "+0.2"
    assert _fmt_transformed(neg, None) == "-0.3"
    # pp display unit (latent capability for a primary on a rate series)
    assert _fmt_transformed(TransformedValue(transform="yoy_chg", value=0.2), "pp") == "+0.20pp"


def test_rate_level_series_carries_change_context():
    # Unemployment rate is a level; it now reads with pp-change context in
    # parens instead of a bare "4.30% level".
    h = _headline(
        "Unemployment rate", "raw", 4.30, basis="level", unit="%",
        also=[("mom_chg", -0.10), ("yoy_chg", 0.20)],
    )
    line = _format_headline_line(h, h.display_unit)
    assert line == "Unemployment rate: 4.30% level (-0.1 MoM chg, +0.2 YoY chg)"


def test_index_level_series_carries_yoy_and_mom():
    h = _headline(
        "Consumer Sentiment Index", "raw", 49.80, basis="level",
        also=[("yoy_pct", -8.30), ("mom_chg", 1.2)],
    )
    line = _format_headline_line(h, h.display_unit)
    assert line == "Consumer Sentiment Index: 49.80 level (-8.30% YoY, +1.2 MoM chg)"


# --- prior line: self-dating + prior YoY (JP ask 2026-06-19) --------------

from macro_monitor.publishers.slack import _format_prior_line  # noqa: E402


def _result_with(headlines):
    return ReleaseResult(
        family_id="x", family_display_name="Retail Sales", period="2026-05",
        period_label="May 2026", headline=headlines, components=[], computed=[],
        context=None, source="fred", source_fetched_at="",
        latest_observation_period="2026-05", expected_observation_period="2026-05",
        is_stale=False, source_lag_minutes=None,
    )


def test_prior_line_states_period_and_yoy_for_non_yoy_headline():
    # Retail Sales: headline is MoM; prior must state the period it covered AND
    # carry the prior period's YoY even though YoY isn't the headline transform.
    h = HeadlineSeriesResult(
        id="RS", label="Retail trade + food services",
        primary=TransformedValue(transform="mom_pct", value=0.88),
        also_display=[TransformedValue(transform="yoy_pct", value=6.88)],
        prior_primary=TransformedValue(transform="mom_pct", value=0.40),
        prior_period_label="April 2026",
        prior_yoy=TransformedValue(transform="yoy_pct", value=5.20),
    )
    line = _format_prior_line(_result_with([h]), {"RS": None})
    assert line == (
        "Prior (April 2026): Retail trade + food services +0.40% MoM (+5.20% YoY)"
    )


def test_prior_line_no_duplicate_yoy_when_headline_is_yoy():
    # CPI headline is already YoY → prior_primary IS the YoY, so no parenthetical.
    h = HeadlineSeriesResult(
        id="CPI", label="CPI",
        primary=TransformedValue(transform="yoy_pct", value=3.40),
        also_display=[],
        prior_primary=TransformedValue(transform="yoy_pct", value=3.10),
        prior_period_label="April 2026",
        prior_yoy=None,
    )
    line = _format_prior_line(_result_with([h]), {"CPI": None})
    assert line == "Prior (April 2026): CPI +3.10% YoY"


def test_prior_line_none_when_no_prior():
    h = HeadlineSeriesResult(
        id="X", label="X",
        primary=TransformedValue(transform="mom_pct", value=1.0),
        also_display=[], prior_primary=None,
    )
    assert _format_prior_line(_result_with([h]), {"X": None}) is None
