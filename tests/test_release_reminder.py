"""Tests for the day-before release reminder (all tiers).

The weekly preview's 4-week lookahead is Tier A only; this reminder must
show EVERY tier scheduled for tomorrow so a Tier B print isn't dropped the
night before. Uses a stub FRED client so no network is touched.
"""

from __future__ import annotations

from datetime import date, timedelta

from macro_monitor.collectors.fred import ReleaseDate
from macro_monitor.config import default_config_path, load_config
from macro_monitor.schedulers.weekly_preview import build_reminder_payload


class _StubFRED:
    """Returns a release on `release_day` for the given release_ids, nothing
    else. Honors the realtime window so tomorrow-only scoping is exercised."""

    def __init__(self, release_day: date, release_ids: set[int]):
        self.release_day = release_day
        self.release_ids = release_ids

    def get_release_dates(
        self,
        release_id,
        realtime_start=None,
        realtime_end=None,
        include_release_dates_with_no_data=False,
    ):
        if release_id in self.release_ids:
            return [ReleaseDate(release_id=release_id, date=self.release_day)]
        return []


def test_reminder_lists_tomorrow_all_tiers():
    families = load_config(default_config_path())
    today = date(2026, 6, 8)
    tomorrow = today + timedelta(days=1)

    # Schedule one Tier A (payrolls, rel_id=50) and one Tier B
    # (housing, rel_id=17) for tomorrow.
    stub = _StubFRED(tomorrow, {50, 17})
    text, blocks, failed = build_reminder_payload(
        families=families, client=stub, today=today
    )

    assert not failed
    assert "RELEASING TOMORROW" in text
    # Tier A AND Tier B both appear — the whole point of this command.
    assert "Employment Situation" in text
    assert "[Tier A]" in text
    assert "Housing Starts & Permits" in text
    assert "[Tier B]" in text
    # Block Kit header + a section body at minimum.
    assert blocks[0]["type"] == "header"
    assert any(b["type"] == "section" for b in blocks)


def test_reminder_handles_empty_day():
    families = load_config(default_config_path())
    today = date(2026, 6, 8)
    stub = _StubFRED(today + timedelta(days=1), set())  # nothing scheduled
    text, blocks, failed = build_reminder_payload(
        families=families, client=stub, today=today
    )
    assert "no scheduled macro releases tomorrow" in text
    assert blocks[0]["type"] == "header"
