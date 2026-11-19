"""Tests for the FOMC meeting calendar + blackout-window logic."""

from __future__ import annotations

from datetime import date, timedelta

from macro_monitor import fomc


def test_meetings_sorted_and_have_projection_flags():
    ms = fomc.all_meetings()
    assert ms == sorted(ms, key=lambda m: m.start)
    # 2026 SEP meetings are Mar/Jun/Sep/Dec.
    sep = {m.start.isoformat() for m in ms if m.projections}
    assert "2026-06-17" not in sep  # flagged by start, not end
    assert {"2026-03-17", "2026-06-16", "2026-09-15", "2026-12-08"} <= sep


def test_next_meeting():
    # Today mid-June 2026 -> next decision is the Jun 16-17 meeting (end >= today).
    m = fomc.next_meeting(date(2026, 6, 15))
    assert m.start == date(2026, 6, 16) and m.end == date(2026, 6, 17)
    # After the last known meeting -> None. Derived from the table, not a literal:
    # this used to assert `next_meeting(date(2027, 1, 1)) is None`, which pinned
    # the stale-calendar defect as expected behaviour.
    past = fomc.last_known_meeting().end + timedelta(days=1)
    assert fomc.next_meeting(past) is None
    assert fomc.calendar_exhausted(past) is True
    assert fomc.calendar_exhausted(date(2026, 11, 19)) is False


def test_2027_calendar_present():
    # Typed from federalreserve.gov fomccalendars.htm (read 2026-11-19).
    m = fomc.next_meeting(date(2027, 1, 1))
    assert m is not None and (m.start, m.end) == (date(2027, 1, 26), date(2027, 1, 27))
    ends_2027 = [m.end for m in fomc.all_meetings() if m.end.year == 2027]
    assert len(ends_2027) == 8 and ends_2027[-1] == date(2027, 11, 17)
    # Decision day is always the Wednesday of a Tue-Wed meeting.
    assert all(m.start.weekday() == 1 and m.end.weekday() == 2
               for m in fomc.all_meetings() if m.start.year >= 2027)


def test_in_blackout_january_2027():
    # Jan 26-27 2027 (Tue-Wed): blackout Sat 1/16 through Thu 1/28.
    assert fomc.in_blackout(date(2027, 1, 20)) is True
    assert fomc.in_blackout(date(2027, 1, 15)) is False


def test_week_ahead_exhausted_calendar_is_loud():
    past = fomc.last_known_meeting().end + timedelta(days=1)
    info = fomc.week_ahead(past, past + timedelta(days=6))
    assert info["this_week"] and "no meeting after" in info["this_week"][0]


def test_blackout_window_second_saturday_to_following_thursday():
    m = fomc.next_meeting(date(2026, 6, 15))  # Jun 16-17 (Tue-Wed)
    start, end = fomc.blackout_window(m)
    assert start == date(2026, 6, 6)    # second Saturday preceding
    assert end == date(2026, 6, 18)     # Thursday following the Wed decision


def test_in_blackout():
    assert fomc.in_blackout(date(2026, 6, 15)) is True    # inside Jun 6–18
    assert fomc.in_blackout(date(2026, 6, 19)) is False   # day after blackout ends
    assert fomc.in_blackout(date(2026, 6, 5)) is False     # day before it starts


def test_week_ahead_meeting_and_blackout_this_week():
    info = fomc.week_ahead(date(2026, 6, 15), date(2026, 6, 21))
    joined = " ".join(info["this_week"])
    assert "FOMC meeting" in joined
    assert "2:00pm ET" in joined
    assert "Summary of Economic Projections" in joined  # Jun is an SEP meeting
    assert "blackout" in joined.lower()
    assert "no Fed speeches until" in joined
    # Next-meeting line points to the FOLLOWING meeting (Jul 28-29), not this one.
    assert info["next_line"] and "7/28" in info["next_line"]


def test_week_ahead_quiet_week_only_next_line():
    # Mid-February 2026: no meeting (Jan done, Mar upcoming), not in blackout.
    info = fomc.week_ahead(date(2026, 2, 10), date(2026, 2, 15))
    assert info["this_week"] == []
    assert info["next_line"] and "3/17" in info["next_line"]
    assert "(SEP)" in info["next_line"]  # March is a projections meeting


def test_week_ahead_strategy_meeting_has_no_rate_decision():
    info = fomc.week_ahead(date(2027, 10, 25), date(2027, 10, 31))
    joined = " ".join(info["this_week"])
    assert "strategy meeting" in joined and "no policy decision" in joined
    assert "rate decision" not in joined
    before = fomc.week_ahead(date(2027, 9, 20), date(2027, 9, 26))
    assert "no policy decision" in (before["next_line"] or "")
