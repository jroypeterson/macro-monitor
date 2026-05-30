"""Unit tests for replay-day's family-selection helper.

The full `cmd_replay_day` does live FRED fetches + chart rendering (covered
by the manual dry-run entry point); here we pin down the pure selection
logic with a fake FRED client so the date-matching can't silently regress.
"""

from __future__ import annotations

from datetime import date

from macro_monitor.cli import families_releasing_on
from macro_monitor.collectors.fred import FREDError, ReleaseDate
from macro_monitor.config import default_config_path, load_config


def _families():
    return load_config(default_config_path())


class _FakeClient:
    """Returns a release on `realtime_start` for the given release_ids only."""

    def __init__(self, releasing_ids, raise_for_ids=()):
        self.releasing_ids = set(releasing_ids)
        self.raise_for_ids = set(raise_for_ids)

    def get_release_dates(
        self,
        release_id,
        realtime_start,
        realtime_end,
        include_release_dates_with_no_data=False,
    ):
        if release_id in self.raise_for_ids:
            raise FREDError("simulated 504")
        if release_id in self.releasing_ids:
            return [ReleaseDate(release_id=release_id, date=date.fromisoformat(realtime_start))]
        return []


def test_selects_only_families_releasing_that_day():
    families = _families()
    # CPI is release_calendar_id 10; nothing else releases this day.
    matched, failed = families_releasing_on(
        date(2026, 5, 12), families, _FakeClient(releasing_ids={10})
    )
    assert matched == ["cpi"]
    assert failed == []


def test_no_releases_returns_empty():
    families = _families()
    matched, failed = families_releasing_on(
        date(2026, 5, 13), families, _FakeClient(releasing_ids=set())
    )
    assert matched == []
    assert failed == []


def test_calendar_failure_is_collected_not_raised():
    families = _families()
    # PPI is release_calendar_id 46; simulate its calendar 504-ing.
    matched, failed = families_releasing_on(
        date(2026, 5, 13), families, _FakeClient(releasing_ids={10}, raise_for_ids={46})
    )
    assert matched == ["cpi"]
    assert len(failed) == 1
    assert failed[0].startswith("ppi (rel_id=46)")


def test_result_is_sorted():
    families = _families()
    # claims=180, payrolls=50 both "release"; result must be alphabetical.
    matched, _ = families_releasing_on(
        date(2026, 5, 8), families, _FakeClient(releasing_ids={180, 50})
    )
    assert matched == sorted(matched)
    assert set(matched) == {"claims", "payrolls"}
