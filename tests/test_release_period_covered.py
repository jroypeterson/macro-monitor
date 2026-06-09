"""Tests for the cadence + covered-period labels on upcoming-release lines.

Each scheduled-release line now carries the series' cadence (always) and
the period the next release is expected to cover (when derivable). The
covered period is NOT a guessed release-to-data lag — it advances the
family's actual last-published period one cadence step — so these tests
lock the period math, the line rendering, and the outputs/latest reader.
"""

from __future__ import annotations

import json
from datetime import date

from macro_monitor.schedulers.weekly_preview import (
    ScheduledRelease,
    _fmt_event_line,
    _next_period_covered,
    load_covered_periods,
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


# --- line rendering ------------------------------------------------------

def test_event_line_always_shows_cadence():
    line = _fmt_event_line(_rel("CPI", "monthly"))
    assert "· monthly" in line
    assert "covers" not in line  # no covered map → cadence only, no guess


def test_event_line_shows_covered_when_present():
    covered = {"CPI": "May 2026"}
    line = _fmt_event_line(_rel("CPI", "monthly"), covered)
    assert "· monthly · covers May 2026" in line


def test_event_line_omits_covered_when_family_absent():
    # A covered map that doesn't include this family → cadence only.
    line = _fmt_event_line(_rel("Trade Balance", "monthly"), {"CPI": "May 2026"})
    assert "· monthly" in line
    assert "covers" not in line


# --- outputs/latest reader ----------------------------------------------

def test_load_covered_periods_reads_and_advances(tmp_path):
    families = {"trade_balance": _FamStub("Trade Balance", "monthly")}
    latest = tmp_path / "latest"
    latest.mkdir()
    (latest / "trade_balance.json").write_text(
        json.dumps({"family_display_name": "Trade Balance", "period": "2026-03"}),
        encoding="utf-8",
    )
    out = load_covered_periods(families, outputs_dir=tmp_path)
    assert out == {"Trade Balance": "April 2026"}


def test_load_covered_periods_missing_dir_is_empty():
    families = {"x": _FamStub("X", "monthly")}
    assert load_covered_periods(families, outputs_dir="C:/nonexistent/path/xyz") == {}


def test_load_covered_periods_skips_unknown_family(tmp_path):
    # A latest file for a family not in config is ignored (no crash).
    families = {"cpi": _FamStub("CPI", "monthly")}
    latest = tmp_path / "latest"
    latest.mkdir()
    (latest / "ghost.json").write_text(
        json.dumps({"family_display_name": "Ghost Series", "period": "2026-03"}),
        encoding="utf-8",
    )
    assert load_covered_periods(families, outputs_dir=tmp_path) == {}


class _FamStub:
    """Minimal stand-in for FamilyConfig — load_covered_periods only reads
    .display_name and .cadence."""

    def __init__(self, display_name, cadence):
        self.display_name = display_name
        self.cadence = cadence
