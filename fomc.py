"""FOMC meeting calendar + communications-blackout logic for the week-ahead.

The Fed does NOT publish a forward schedule of individual speeches (they're
announced days ahead), but FOMC meeting dates are set a year+ in advance, and
the communications-blackout window around each meeting is a fixed rule:

  "The blackout period begins the second Saturday preceding an FOMC meeting and
   ends the Thursday following a meeting."  — Fed media policy

During blackout, officials don't speak on policy — so the week-ahead can tell
JP both "FOMC meets this week (decision Wed 2pm ET)" and "Fed in blackout, no
speeches until Friday."

Meeting dates are hardcoded (stable once announced; source: federalreserve.gov
/monetarypolicy/fomccalendars.htm). Add future years to MEETINGS as the Fed
publishes them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

_WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _wd(d: date) -> str:
    return _WD[d.weekday()]


def _md(d: date) -> str:
    return f"{d.month}/{d.day}"


@dataclass(frozen=True)
class FOMCMeeting:
    start: date          # first day of the 2-day meeting
    end: date            # decision day — statement at 2:00pm ET
    projections: bool    # SEP / dot-plot meeting (quarterly: Mar/Jun/Sep/Dec)

    def label(self) -> str:
        return f"{_md(self.start)}–{_md(self.end)}"


def _m(start: str, end: str, projections: bool) -> FOMCMeeting:
    return FOMCMeeting(date.fromisoformat(start), date.fromisoformat(end), projections)


# Source: federalreserve.gov FOMC calendars. Decision = second day, 2pm ET.
MEETINGS: list[FOMCMeeting] = [
    # 2026
    _m("2026-01-27", "2026-01-28", False),
    _m("2026-03-17", "2026-03-18", True),
    _m("2026-04-28", "2026-04-29", False),
    _m("2026-06-16", "2026-06-17", True),
    _m("2026-07-28", "2026-07-29", False),
    _m("2026-09-15", "2026-09-16", True),
    _m("2026-10-27", "2026-10-28", False),
    _m("2026-12-08", "2026-12-09", True),
    # 2027 dates not yet published by the Fed — add here when released.
]


def all_meetings() -> list[FOMCMeeting]:
    return sorted(MEETINGS, key=lambda m: m.start)


def next_meeting(today: date) -> FOMCMeeting | None:
    """First meeting whose decision day is on/after `today` (None past the
    known schedule)."""
    for m in all_meetings():
        if m.end >= today:
            return m
    return None


def meeting_after(meeting: FOMCMeeting) -> FOMCMeeting | None:
    for m in all_meetings():
        if m.start > meeting.start:
            return m
    return None


def blackout_window(meeting: FOMCMeeting) -> tuple[date, date]:
    """(start, end) of the communications blackout: second Saturday preceding
    the meeting through the Thursday following it (inclusive)."""
    wd = meeting.start.weekday()
    days_back_to_sat = (wd - 5) % 7 or 7      # most recent Saturday strictly before
    first_preceding_sat = meeting.start - timedelta(days=days_back_to_sat)
    start = first_preceding_sat - timedelta(days=7)  # the SECOND preceding Saturday
    end_wd = meeting.end.weekday()
    days_fwd_to_thu = (3 - end_wd) % 7 or 7   # Thursday strictly after the decision day
    end = meeting.end + timedelta(days=days_fwd_to_thu)
    return start, end


def in_blackout(today: date) -> bool:
    m = next_meeting(today)
    if m is None:
        return False
    start, end = blackout_window(m)
    return start <= today <= end


def week_ahead(today: date, week_end: date) -> dict:
    """Return FOMC lines for the week-ahead preview covering [today, week_end].

    {
      "this_week": [str, ...],   # meeting + blackout lines relevant this week
      "next_line": str | None,   # "Next FOMC: Tue 7/28–7/29" for the lookahead
    }
    """
    res: dict = {"this_week": [], "next_line": None}
    m = next_meeting(today)
    if m is None:
        return res

    # Meeting overlapping this week?
    meeting_this_week = m.start <= week_end and m.end >= today
    if meeting_this_week:
        sep = " + Summary of Economic Projections (dot plot)" if m.projections else ""
        res["this_week"].append(
            f"🏛️ *FOMC meeting* {_wd(m.start)} {_md(m.start)}–{_wd(m.end)} {_md(m.end)} "
            f"— rate decision {_wd(m.end)} {_md(m.end)} 2:00pm ET{sep}"
        )

    # Blackout overlapping this week?
    bstart, bend = blackout_window(m)
    if bstart <= week_end and bend >= today:
        if bstart <= today <= bend:
            resume = bend + timedelta(days=1)
            res["this_week"].append(
                f"🤫 Fed communications *blackout* in effect through {_wd(bend)} {_md(bend)} "
                f"— no Fed speeches until {_wd(resume)} {_md(resume)}"
            )
        elif today < bstart <= week_end:
            res["this_week"].append(
                f"🤫 Fed *blackout* begins {_wd(bstart)} {_md(bstart)} "
                f"— Fed speeches pause until after the decision"
            )

    # Next-meeting line for the lookahead. If this week's meeting is the next
    # one, point at the meeting AFTER it so the lookahead isn't redundant.
    nxt = meeting_after(m) if meeting_this_week else m
    if nxt is not None:
        sep = " (SEP)" if nxt.projections else ""
        res["next_line"] = (
            f"🏛️ Next FOMC meeting: {_wd(nxt.start)} {_md(nxt.start)}–{_md(nxt.end)}{sep}"
        )
    return res
