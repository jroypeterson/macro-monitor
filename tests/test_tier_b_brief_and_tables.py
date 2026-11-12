"""One-line Tier B posts, and the weekly / monthly release tables.

JP 2026-11-12:
  - every new Tier B print gets one succinct line with its tier and how
    unusual it was (full post only over the gate) -- EXCEPT gas prices and
    mortgage rates, which he already sees weekly on his price-alert chart;
  - a Sunday table of the week's releases with the tier noted;
  - a table of next month's Tier A releases on the last day of the month.

Background for the workflow tests: the Sunday preview skipped silently for
eleven weeks because an exact-hour guard met GitHub's late cron starts.
"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

import pytest

from macro_monitor import cli, fomc, tier_b_gate
from macro_monitor.collectors.fred import ReleaseDate
from macro_monitor.config import default_config_path, load_config
from macro_monitor.posts_ledger import PostDecision
from macro_monitor.publishers.slack import (
    build_brief_blocks,
    render_brief_text,
)
from macro_monitor.release_runner import ContextResult, ReleaseResult
from macro_monitor.schedulers import weekly_preview as wp

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Brief line
# --------------------------------------------------------------------------

def _result(z, kind="delta", tier="B"):
    ctx = ContextResult(
        anchor_series="S", anchor_transform="yoy_pct", trends=[], zscore=z,
        zscore_lookback_years=5, zscore_kind=kind,
    )
    return ReleaseResult(
        family_id="x", family_display_name="New Home Sales", period="2026-10",
        period_label="October 2026", headline=[], components=[], computed=[],
        context=ctx, source="fred", source_fetched_at="",
        latest_observation_period="2026-10", expected_observation_period="2026-10",
        is_stale=False, source_lag_minutes=None, tier=tier,
    )


def test_brief_line_states_tier_and_sigma_with_its_yardstick():
    line = render_brief_text(_result(-0.28), threshold=1.0)
    assert line == (
        "▫️ New Home Sales October 2026 [Tier B] · "
        "0.3σ move vs 5y history — not unusual"
    )


def test_brief_line_names_a_level_gate_as_level():
    assert "0.4σ level vs 5y history" in render_brief_text(_result(0.43, kind="level"), 1.0)


def test_brief_line_says_so_when_there_is_no_score():
    # The Existing Home Sales case: no score used to mean no post at all.
    line = render_brief_text(_result(None), threshold=1.0)
    assert "σ n/a — not enough history to score" in line
    assert "not unusual" not in line


def test_brief_blocks_are_one_section():
    blocks = build_brief_blocks(_result(0.5), 1.0)
    assert [b["type"] for b in blocks] == ["section"]
    assert "[Tier B]" in blocks[0]["text"]["text"]


# --------------------------------------------------------------------------
# Config: who gets the one-liner
# --------------------------------------------------------------------------

def test_only_gas_and_mortgage_rates_stay_silent_under_the_gate():
    families = load_config(default_config_path())
    silent = {
        fid for fid, f in families.items()
        if f.tier_b_gate is not None and f.tier_b_gate.below_threshold == "skip"
    }
    assert silent == {"gas_prices", "mortgage_rates"}


# --------------------------------------------------------------------------
# The seam: cmd_post_release under the gate
# --------------------------------------------------------------------------

class _Ledger:
    recorded: list[dict] = []
    decision = PostDecision.NEW_PERIOD

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def compute_diff(self, **kw):
        return argparse.Namespace(decision=type(self).decision, revision_count=0)

    def record_post(self, **kw):
        type(self).recorded.append(kw)


class _Publisher:
    calls: list[str] = []

    def __init__(self, dry_run=True):
        self.dry_run = dry_run

    def publish_brief(self, result, threshold=None):
        type(self).calls.append("brief")
        return argparse.Namespace(main_ts="111.222", main_channel="C1")

    def publish_release(self, **kw):
        type(self).calls.append("full")
        return argparse.Namespace(
            main_ts="333.444", main_channel="C1", chart_upload_errors=[]
        )


@pytest.fixture
def post_release(monkeypatch):
    """Drive the real cmd_post_release with FRED, artifacts, the ledger and
    Slack replaced -- the gate, the brief/skip branch and the ledger write
    are the real code."""
    import macro_monitor.charts.dashboard as dash_mod
    import macro_monitor.collectors.fred as fred_mod
    import macro_monitor.outputs as outputs_mod
    import macro_monitor.posts_ledger as ledger_mod
    import macro_monitor.publishers.slack as slack_mod
    import macro_monitor.release_runner as runner_mod

    families = load_config(default_config_path())
    _Ledger.recorded, _Publisher.calls = [], []
    _Ledger.decision = PostDecision.NEW_PERIOD
    state = {"z": 0.2}
    here = Path(cli.__file__).parent

    # cmd_post_release imports these lazily from their home modules, so the
    # doubles go there. Everything that touches FRED, disk or Slack is
    # replaced; nothing under outputs/ or state/ may be written by a test.
    monkeypatch.setattr(cli, "load_config", lambda path: families)
    monkeypatch.setattr(runner_mod, "compute_release", lambda family, client, **kw: _result(state["z"]))
    monkeypatch.setattr(fred_mod, "FREDClient", lambda *a, **k: object())
    monkeypatch.setattr(
        outputs_mod, "write_release_artifacts",
        lambda **kw: (here / "outputs" / "x.json", here / "outputs" / "x.html"),
    )
    monkeypatch.setattr(dash_mod, "render_dashboard", lambda fams: here / "outputs" / "d.html")
    monkeypatch.setattr(ledger_mod, "PostsLedger", _Ledger)
    monkeypatch.setattr(slack_mod, "SlackPublisher", _Publisher)

    def run(family, z=0.2, decision=PostDecision.NEW_PERIOD):
        state["z"] = z
        _Ledger.decision = decision
        families[family].charts = None  # no chart rendering in a unit test
        return cli.cmd_post_release(
            argparse.Namespace(family=family, dry_run=False, config=None)
        )

    return run


def _skip_if_harness_unfit(run, family):
    try:
        return run(family)
    except Exception as e:  # pragma: no cover - names the mismatch instead of a bare error
        pytest.fail(f"cmd_post_release harness no longer matches cli.py: {type(e).__name__}: {e}")


def test_under_the_gate_a_tier_b_print_posts_the_brief_line(post_release):
    assert _skip_if_harness_unfit(post_release, "new_home_sales") == 0
    assert _Publisher.calls == ["brief"]
    assert _Ledger.recorded[0]["slack_ts"] == "111.222"


def test_under_the_gate_gas_prices_stays_silent_but_is_recorded(post_release):
    assert post_release("gas_prices") == 0
    assert _Publisher.calls == []
    assert _Ledger.recorded[0]["slack_ts"] is None


def test_over_the_gate_still_gets_the_full_post(post_release):
    assert post_release("new_home_sales", z=1.6) == 0
    assert _Publisher.calls == ["full"]


def test_a_revision_under_the_gate_stays_silent(post_release):
    assert post_release("new_home_sales", decision=PostDecision.REVISED_HEADLINE) == 0
    assert _Publisher.calls == []
    assert _Ledger.recorded[0]["slack_ts"] is None


def test_unscored_family_posts_the_brief_line(post_release):
    assert post_release("existing_home_sales", z=None) == 0
    assert _Publisher.calls == ["brief"]


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

class _FakeFRED:
    """Every family releases on the same two dates."""

    def __init__(self, dates):
        self._dates = dates

    def get_release_dates(self, release_id, **kw):
        return [ReleaseDate(release_id=release_id, date=d) for d in self._dates]


def _table(blocks):
    tables = [b for b in blocks if b["type"] == "table"]
    assert len(tables) == 1, "Slack allows one table per message"
    assert blocks[-1]["type"] == "table", "the table must be the last block"
    return [[c["text"] for c in row] for row in tables[0]["rows"]]


def test_weekly_table_has_a_tier_column_covering_a_and_b():
    families = load_config(default_config_path())
    sunday = date(2026, 11, 15)
    post = wp.build_weekly_post(families, _FakeFRED([date(2026, 11, 17)]), today=sunday)
    rows = _table(post.blocks)
    assert rows[0] == ["Day", "ET", "Tier", "Release", "Covers", "Last"]
    assert {r[2] for r in rows[1:]} == {"A", "B"}
    assert all(r[0] == "Tue 11/17" for r in rows[1:])
    # Every cell is non-empty text (Slack rejects an empty cell).
    assert all(c.strip() for r in rows for c in r)
    # The fallback carries the same releases as a list, without a table.
    assert not [b for b in post.fallback_blocks if b["type"] == "table"]
    assert post.thread_blocks, "the 4-week lookahead rides in the thread"


def test_monthly_table_is_next_month_tier_a_only_plus_fomc():
    families = load_config(default_config_path())
    post = wp.build_monthly_post(
        families, _FakeFRED([date(2026, 7, 14), date(2026, 8, 3)]), today=date(2026, 6, 30)
    )
    assert post.blocks[0]["text"]["text"] == "🗓️ July 2026 — Tier A releases"
    rows = _table(post.blocks)
    assert rows[0] == ["Date", "ET", "Release"]
    names = {r[2].replace("⭐ ", "") for r in rows[1:]}
    tier_a = {f.display_name for f in wp.calendar_families(families).values() if f.tier == "A"}
    tier_b = {f.display_name for f in wp.calendar_families(families).values() if f.tier == "B"}
    fomc_rows = {n for n in names if "FOMC" in n}
    assert names - fomc_rows == tier_a
    assert not names & tier_b
    # August's date is outside the month and must not appear.
    assert all(r[0].endswith("7/14") or "FOMC" in r[2] for r in rows[1:])
    july_meetings = [m for m in fomc.all_meetings() if m.end.year == 2026 and m.end.month == 7]
    assert len(fomc_rows) == len(july_meetings)


@pytest.mark.parametrize(
    "day, expected",
    [
        (date(2026, 6, 30), True), (date(2026, 6, 29), False),
        (date(2026, 2, 28), True), (date(2028, 2, 28), False), (date(2028, 2, 29), True),
        (date(2026, 12, 31), True), (date(2026, 7, 30), False),
    ],
)
def test_last_day_of_month(day, expected):
    assert wp.is_last_day_of_month(day) is expected


def test_next_month_window_rolls_the_year():
    assert wp.next_month_window(date(2026, 12, 31)) == (date(2027, 1, 1), date(2027, 1, 31))


class _Slack:
    def __init__(self, reject_table):
        self.reject_table = reject_table
        self.sent = []

    def chat_postMessage(self, **kw):
        from slack_sdk.errors import SlackApiError

        has_table = any(b["type"] == "table" for b in kw["blocks"])
        if has_table and self.reject_table:
            raise SlackApiError("rejected", {"error": "invalid_blocks"})
        self.sent.append(kw)
        return {"ts": "1.0", "channel": kw["channel"]}


def test_a_rejected_table_falls_back_to_the_list_and_still_posts():
    families = load_config(default_config_path())
    post = wp.build_monthly_post(families, _FakeFRED([date(2026, 7, 14)]), today=date(2026, 6, 30))
    slack = _Slack(reject_table=True)
    ts, used_table = wp.post_with_table_fallback(slack, "C1", post)
    assert (ts, used_table) == ("1.0", False)
    assert len(slack.sent) == 1 and slack.sent[0]["blocks"] == post.fallback_blocks


def test_an_accepted_table_posts_once_then_threads_the_lookahead():
    families = load_config(default_config_path())
    post = wp.build_weekly_post(families, _FakeFRED([date(2026, 11, 17)]), today=date(2026, 11, 15))
    slack = _Slack(reject_table=False)
    _, used_table = wp.post_with_table_fallback(slack, "C1", post)
    assert used_table
    assert [m.get("thread_ts") for m in slack.sent] == [None, "1.0"]


# --------------------------------------------------------------------------
# Schedules: one cron line, no exact-hour guard
# --------------------------------------------------------------------------

def _live_yaml(name):
    text = (REPO / ".github" / "workflows" / name).read_text(encoding="utf-8")
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("#"))


_WORKFLOWS = sorted(p.name for p in (REPO / ".github" / "workflows").glob("*.yml"))


# Lanes that STILL carry the exact-hour guard and are therefore not posting
# (every scheduled run checked 2026-10-18..2026-11-12 skipped). Found by the
# test below on 2026-11-12; left in place because un-gating them resumes
# posting with a backlog and JP has not yet said where they should post.
# Fixing a lane means deleting it from this set -- the test fails otherwise.
_STILL_HOUR_GATED = {
    "fed_speeches.yml",
    "research_digest.yml",
    "global_macro.yml",
    "prediction_markets.yml",
}


def test_the_hour_gated_set_is_exactly_the_known_one():
    """GitHub starts scheduled runs hours late, so an exact-hour guard skips
    -- and reports success. It silenced the Sunday preview (11 weeks), the
    daily heartbeat and the 17:00 catch-up poll. Derived over every workflow
    file so a new lane cannot reintroduce it, and a fixed lane cannot stay
    listed as broken."""
    gated = {n for n in _WORKFLOWS if "date +%H" in _live_yaml(n)}
    assert gated == _STILL_HOUR_GATED


@pytest.mark.parametrize(
    "name", ["weekly_preview.yml", "monthly_preview.yml", "heartbeat.yml", "reconciliation.yml"]
)
def test_unguarded_posting_workflows_have_one_cron_line(name):
    crons = re.findall(r"^\s*- cron:", _live_yaml(name), flags=re.M)
    assert len(crons) == 1, "two lines would double-post without an hour guard"


def test_reminder_star_legend_only_when_a_release_is_starred():
    def legend(releases):
        blocks = wp._build_reminder_blocks(date(2026, 11, 10), releases)
        return blocks[-1]["elements"][0]["text"]

    def rel(priority):
        return wp.ScheduledRelease(
            family_id="x", display_name="X", tier="A", cadence="monthly",
            release_date=date(2026, 11, 10), release_time_et="08:30",
            fred_release_id=1, priority=priority,
        )

    assert "⭐" not in legend([rel(False)])
    assert "⭐" not in legend([])
    assert "⭐ = priority release" in legend([rel(True), rel(False)])
    assert "All tiers shown" in legend([rel(False)])
