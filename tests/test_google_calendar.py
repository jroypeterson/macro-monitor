"""Google Calendar publisher: event body contract and the backfill's exit code."""
import argparse
from datetime import date

import pytest

from macro_monitor import cli
from macro_monitor.config import default_config_path, load_config
from macro_monitor.publishers import google_calendar as G
from macro_monitor.schedulers.weekly_preview import ScheduledRelease


@pytest.fixture(scope="module")
def families():
    return load_config(default_config_path())


def _release(fid, fam):
    return ScheduledRelease(
        family_id=fid, display_name=fam.display_name, tier=fam.tier,
        cadence=fam.cadence, release_date=date(2026, 11, 12),
        release_time_et=fam.release_time_et, fred_release_id=fam.release_calendar_id or 0,
    )


def test_body_leads_with_frequency_then_the_healthcare_read(families):
    ev = G.build_events_from_schedule(families, [_release("cpi", families["cpi"])])[0]
    lines = G.GoogleCalendarPublisher()._event_body(ev)["description"].splitlines()
    assert lines[0] == "Frequency: Monthly"
    assert lines[1].startswith("Healthcare read: ") and "Medical care services" in lines[1]


def test_a_family_with_no_healthcare_series_gets_no_healthcare_line(families):
    fid = next(k for k, f in families.items()
               if f.release_calendar_id and not G.healthcare_labels(f))
    ev = G.build_events_from_schedule(families, [_release(fid, families[fid])])[0]
    assert "Healthcare read" not in G.GoogleCalendarPublisher()._event_body(ev)["description"]


def _run_backfill(monkeypatch, families, errors):
    """Drive cmd_backfill_calendar with FRED and Google stubbed out."""
    import macro_monitor.collectors.fred as fred
    import macro_monitor.schedulers.weekly_preview as wp

    monkeypatch.setattr(fred, "FREDClient", lambda: None)
    monkeypatch.setattr(wp, "fetch_scheduled_releases",
                        lambda **kw: ([_release("cpi", families["cpi"])], []))
    monkeypatch.setattr(G.GoogleCalendarPublisher, "__init__",
                        lambda self, **kw: setattr(self, "dry_run", False))
    monkeypatch.setattr(G.GoogleCalendarPublisher, "upsert_events",
                        lambda self, evs: {"created": 0, "updated": len(evs) - len(errors),
                                           "removed": 0, "skipped": 0, "errors": errors})
    alerts = []
    monkeypatch.setattr(cli, "_alert_status_reports_about_calendar",
                        lambda *a: alerts.append(a))
    rc = cli.cmd_backfill_calendar(argparse.Namespace(config=None, days=90, dry_run=False))
    return rc, alerts


def test_a_partial_sync_exits_nonzero_and_alerts(monkeypatch, families):
    """2026-10-12: two scheduled runs went green with 40 and 50 of 84 writes failed."""
    rc, alerts = _run_backfill(monkeypatch, families, ["cpi 2026-11-12: Rate Limit Exceeded"])
    assert rc == 1 and len(alerts) == 1


def test_a_clean_sync_exits_zero_without_alerting(monkeypatch, families):
    rc, alerts = _run_backfill(monkeypatch, families, [])
    assert rc == 0 and alerts == []
