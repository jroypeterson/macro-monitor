"""poll-all must poll whenever it runs -- the ET wall-clock window is gone.

**Why (2026-09-16/17 outage).** GitHub's scheduler began creating this
account's scheduled runs 3-4h late and dropping most of them. `cmd_poll_all`
returned 0 without polling outside 08:25-11:00 / 13:55-14:35 ET, so every late
run exited green having done nothing: Retail Sales and Industrial Production
(09-16) and Initial Claims (09-17) were never posted. See
`plans/missed_releases_diagnosis_2026-09-17.md`.

Dedupe is NOT the clock's job -- it is the posts ledger's (PK (family_id,
period) + compute_diff). So these tests pin both halves: a late run polls, and
polling more often cannot double-post nor swallow a revision. The ledger is a
temp DB, every network/Slack/disk collaborator is stubbed, and `now` is frozen
so the tests are meaningful against the old clock gate (mutation check).
"""
from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import yaml

from macro_monitor import cli
from macro_monitor.posts_ledger import PostDecision, PostsLedger

ET = ZoneInfo("America/New_York")
REPO = Path(cli.__file__).parent
FAMILY = "retail_sales"


def _freeze(monkeypatch, hh: int, mm: int) -> None:
    """Freeze `datetime.now` for code that does `from datetime import datetime`
    at call time (as the old window gate did). Wed 2026-09-16 = release day."""
    frozen = _dt.datetime(2026, 9, 16, hh, mm, tzinfo=ET)

    class _Frozen(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)

    monkeypatch.setattr(_dt, "datetime", _Frozen)


@pytest.fixture
def harness(monkeypatch, tmp_path):
    """Stub every side effect of cmd_post_release; keep the REAL ledger logic
    (compute_diff / record_post) on a temp DB, since that is the dedupe."""
    import macro_monitor.charts.dashboard as dash
    import macro_monitor.collectors.fred as fred
    import macro_monitor.outputs as outputs
    import macro_monitor.posts_ledger as pl
    import macro_monitor.publishers.slack as slack
    import macro_monitor.release_runner as rr

    family = SimpleNamespace(
        tier="A",
        family_type="numeric",
        display_name="Retail Sales",
        charts=None,
        agency=SimpleNamespace(pdf_url_static=None),
        release_calendar_id=None,
        tier_b_gate=None,
    )
    monkeypatch.setattr(cli, "load_config", lambda path: {FAMILY: family})
    monkeypatch.setattr(cli, "validate_all_or_raise", lambda fams: None)

    state = {"value": 0.6, "published": [], "computed": 0}

    def fake_compute(fam, client):
        state["computed"] += 1
        return SimpleNamespace(
            period="2026-08",
            period_label="Aug 2026",
            is_stale=False,
            latest_observation_period="2026-08-01",
            expected_observation_period="2026-08-01",
            headline=[SimpleNamespace(id="RSAFS", primary=SimpleNamespace(value=state["value"]))],
            components=[],
        )

    monkeypatch.setattr(rr, "compute_release", fake_compute)
    monkeypatch.setattr(fred, "FREDClient", lambda: None)
    monkeypatch.setattr(
        outputs, "write_release_artifacts",
        lambda **kw: (REPO / "stub.json", REPO / "stub.html"),
    )

    def _no_dashboard(fams):
        raise RuntimeError("dashboard stubbed out in tests")

    monkeypatch.setattr(dash, "render_dashboard", _no_dashboard)

    db = tmp_path / "posts.db"
    monkeypatch.setattr(pl, "PostsLedger", lambda: PostsLedger(db))

    class FakePublisher:
        def __init__(self, dry_run):
            self.dry_run = dry_run

        def publish_release(self, *, result, chart_paths, agency_pdf_url, decision):
            state["published"].append(decision)
            return SimpleNamespace(main_channel="C_TEST", main_ts="1.0", chart_upload_errors=[])

    monkeypatch.setattr(slack, "SlackPublisher", FakePublisher)
    state["db"] = db
    return state


def _args() -> argparse.Namespace:
    return argparse.Namespace(tier="A", dry_run=False, config=None, skip_window_check=False)


@pytest.mark.parametrize("hh,mm", [(12, 30), (16, 0)])
def test_poll_all_polls_outside_old_window(harness, monkeypatch, hh, mm):
    """A 3-4h-late cron run must still post an owed release."""
    _freeze(monkeypatch, hh, mm)
    assert cli.cmd_poll_all(_args()) == 0
    assert harness["computed"] == 1, "poll-all returned without polling"
    assert harness["published"] == [PostDecision.NEW_PERIOD]


def test_poll_all_does_not_repost_same_period(harness, monkeypatch):
    """Idempotency lives in the ledger, not the clock: polling again with
    unchanged data must not post a second time."""
    _freeze(monkeypatch, 16, 0)
    assert cli.cmd_poll_all(_args()) == 0
    assert cli.cmd_poll_all(_args()) == 0
    assert harness["computed"] == 2
    assert harness["published"] == [PostDecision.NEW_PERIOD]


def test_poll_all_revised_headline_same_period_still_posts_revised(harness, monkeypatch):
    """Re-releases share a period key (GDP advance/second/third); a changed
    headline must take the REVISED path, never be deduped away."""
    _freeze(monkeypatch, 16, 0)
    assert cli.cmd_poll_all(_args()) == 0
    harness["value"] = 0.9
    assert cli.cmd_poll_all(_args()) == 0
    assert harness["published"] == [PostDecision.NEW_PERIOD, PostDecision.REVISED_HEADLINE]
    with PostsLedger(harness["db"]) as ledger:
        assert ledger.get(FAMILY, "2026-08").revision_count == 1


@pytest.mark.parametrize("wf", ["release_polling.yml", "reconciliation.yml"])
def test_posting_workflows_share_concurrency_group(wf):
    """Both lanes post to #macro-and-markets and commit state; with the clock
    gate gone, late runs can overlap. One queue, never cancelled mid-post."""
    doc = yaml.safe_load((REPO / ".github" / "workflows" / wf).read_text(encoding="utf-8"))
    conc = doc.get("concurrency")
    assert isinstance(conc, dict), f"{wf}: no top-level concurrency block"
    assert conc.get("group") == "macro-posts"
    assert conc.get("cancel-in-progress") is False


def test_fomc_statement_is_not_in_the_shared_group():
    """GitHub keeps one pending run per concurrency group; a poll queued behind a
    pending FOMC run would cancel it silently. FOMC commits no state, so it stays out."""
    from pathlib import Path
    wf = (Path(__file__).resolve().parents[1] / ".github" / "workflows" /
          "fomc_statement.yml").read_text(encoding="utf-8")
    assert "group: macro-posts" not in wf
