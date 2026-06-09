"""Tests for the cadence + covered-period + last-YoY labels on
upcoming-release lines.

Each scheduled-release line now carries the series' cadence (always), the
period the next release is expected to cover, and the last YoY reading
(both when derivable). The covered period is NOT a guessed release-to-data
lag — it advances the family's actual last-published period one cadence
step; the YoY is read from the last-published headline — so these tests
lock the period math, the YoY extraction, the line rendering, and the
outputs/latest reader.
"""

from __future__ import annotations

import json
from datetime import date

from macro_monitor.schedulers.weekly_preview import (
    ScheduledRelease,
    _fmt_event_line,
    _last_yoy_reading,
    _next_period_covered,
    load_preview_extras,
)


def _rel(display_name, cadence, *, tier="A", d=date(2026, 6, 10)):
    return ScheduledRelease(
        family_id=display_name.lower().replace(" ", "_"),
        display_name=display_name,
        tier=tier,
        cadence=cadence,
        release_date=d,
        release_time_et="08:30",
        fred_release_id=1,
    )


# --- period advancement --------------------------------------------------

def test_next_period_monthly_advances_one_month():
    # Last published March → next release covers April.
    assert _next_period_covered("2026-03", "monthly") == "April 2026"


def test_next_period_monthly_year_rollover():
    assert _next_period_covered("2026-12", "monthly") == "January 2027"


def test_next_period_quarterly_advances_one_quarter():
    assert _next_period_covered("2026-Q1", "quarterly") == "Q2 2026"


def test_next_period_quarterly_year_rollover():
    assert _next_period_covered("2026-Q4", "quarterly") == "Q1 2027"


def test_next_period_weekly_advances_seven_days():
    assert _next_period_covered("2026-05-30", "weekly") == "Week ending Jun 06, 2026"


def test_next_period_unknown_cadence_returns_none():
    assert _next_period_covered("2026-06-10", "per_meeting") is None


def test_next_period_malformed_key_returns_none():
    assert _next_period_covered("garbage", "monthly") is None


# --- last YoY extraction -------------------------------------------------

def test_last_yoy_from_also_display():
    # CPI: primary is annualized_mom, YoY lives in also_display.
    headline = [
        {
            "primary": {"transform": "annualized_mom", "value": 7.95},
            "also_display": [
                {"transform": "yoy_pct", "value": 3.7792},
                {"transform": "mom_pct", "value": 0.64},
            ],
        }
    ]
    assert _last_yoy_reading(headline) == "+3.78% YoY"


def test_last_yoy_from_primary_transform():
    headline = [{"primary": {"transform": "yoy_pct", "value": -1.234}}]
    assert _last_yoy_reading(headline) == "-1.23% YoY"


def test_last_yoy_none_for_level_series():
    # Unemployment rate / claims / trade balance: no YoY anywhere.
    headline = [
        {
            "primary": {"transform": "raw", "value": 4.30},
            "also_display": [{"transform": "mom_chg", "value": 0.1}],
        }
    ]
    assert _last_yoy_reading(headline) is None


def test_last_yoy_empty_headline():
    assert _last_yoy_reading([]) is None


# --- line rendering ------------------------------------------------------

def test_event_line_always_shows_cadence():
    line = _fmt_event_line(_rel("CPI", "monthly"))
    assert "· monthly" in line
    assert "covers" not in line  # no extras → cadence only, no guess
    assert "last" not in line


def test_event_line_shows_covered_and_yoy_when_present():
    extras = {"CPI": {"covers": "May 2026", "yoy": "+3.78% YoY"}}
    line = _fmt_event_line(_rel("CPI", "monthly"), extras)
    assert "· monthly · covers May 2026 · last +3.78% YoY" in line


def test_event_line_covered_without_yoy():
    # A level series may have covers but no yoy.
    extras = {"Trade Balance": {"covers": "April 2026"}}
    line = _fmt_event_line(_rel("Trade Balance", "monthly"), extras)
    assert "· covers April 2026" in line
    assert "last" not in line


def test_event_line_omits_all_when_family_absent():
    line = _fmt_event_line(_rel("Trade Balance", "monthly"), {"CPI": {"covers": "May 2026"}})
    assert "· monthly" in line
    assert "covers" not in line
    assert "last" not in line


# --- outputs/latest reader ----------------------------------------------

def test_load_preview_extras_reads_period_and_yoy(tmp_path):
    families = {"cpi": _FamStub("CPI", "monthly")}
    latest = tmp_path / "latest"
    latest.mkdir()
    (latest / "cpi.json").write_text(
        json.dumps(
            {
                "family_display_name": "CPI",
                "period": "2026-04",
                "headline": [
                    {
                        "primary": {"transform": "annualized_mom", "value": 7.95},
                        "also_display": [{"transform": "yoy_pct", "value": 3.7792}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = load_preview_extras(families, outputs_dir=tmp_path)
    assert out == {"CPI": {"covers": "May 2026", "yoy": "+3.78% YoY"}}


def test_load_preview_extras_period_only_for_level_series(tmp_path):
    families = {"trade_balance": _FamStub("Trade Balance", "monthly")}
    latest = tmp_path / "latest"
    latest.mkdir()
    (latest / "trade_balance.json").write_text(
        json.dumps({"family_display_name": "Trade Balance", "period": "2026-03"}),
        encoding="utf-8",
    )
    out = load_preview_extras(families, outputs_dir=tmp_path)
    assert out == {"Trade Balance": {"covers": "April 2026"}}


def test_load_preview_extras_missing_dir_is_empty():
    families = {"x": _FamStub("X", "monthly")}
    assert load_preview_extras(families, outputs_dir="C:/nonexistent/path/xyz") == {}


def test_load_preview_extras_skips_unknown_family(tmp_path):
    # A latest file for a family not in config is ignored (no crash).
    families = {"cpi": _FamStub("CPI", "monthly")}
    latest = tmp_path / "latest"
    latest.mkdir()
    (latest / "ghost.json").write_text(
        json.dumps({"family_display_name": "Ghost Series", "period": "2026-03"}),
        encoding="utf-8",
    )
    assert load_preview_extras(families, outputs_dir=tmp_path) == {}


class _FamStub:
    """Minimal stand-in for FamilyConfig — load_covered_periods only reads
    .display_name and .cadence."""

    def __init__(self, display_name, cadence):
        self.display_name = display_name
        self.cadence = cadence
