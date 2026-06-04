"""Sunday week-ahead preview.

Goal 1 of the project: "This Week" (Tier A + B, detailed) AND
"Looking Ahead — Next 4 Weeks" (Tier A only, compact) in a single
Slack post. Source: FRED /releases/dates for every scheduled family
(any tier with a release_calendar_id; see config.calendar_families).

Run via: `python -m macro_monitor.cli weekly-preview [--post]`
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..collectors.fred import FREDClient, FREDError, ReleaseDate
from ..config import FamilyConfig, calendar_families

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class ScheduledRelease:
    """One scheduled release event."""

    family_id: str
    display_name: str
    tier: str
    cadence: str
    release_date: date
    release_time_et: str   # e.g. "08:30"
    fred_release_id: int

    def datetime_et(self) -> datetime:
        h, m = self.release_time_et.split(":")
        return datetime.combine(self.release_date, time(int(h), int(m)), tzinfo=ET)


def fetch_scheduled_releases(
    families: dict[str, FamilyConfig],
    client: FREDClient,
    start: date,
    end: date,
) -> tuple[list[ScheduledRelease], list[str]]:
    """Pull the release calendar for every numeric family with a
    `release_calendar_id`. Returns (releases, failed_family_ids).

    Graceful degradation per family: if FRED 504s on one family's
    calendar (this happens — see release_id=10/CPI), the rest still
    succeed and we report the failures to #status-reports.

    Event families (FOMC) don't have FRED data series and are handled
    separately — they're skipped here for v1.
    """
    out: list[ScheduledRelease] = []
    failed: list[str] = []

    from datetime import date as _date_cls
    today = _date_cls.today()

    # Shared family scope with the annual HTML grid (config.calendar_families):
    # both the Google Calendar backfill (which calls this) and the HTML must
    # see the same set, so they can never silently diverge.
    for family_id, family in calendar_families(families).items():
        try:
            dates = client.get_release_dates(
                release_id=family.release_calendar_id,
                realtime_start=today.isoformat(),
                realtime_end=end.isoformat(),
                include_release_dates_with_no_data=True,
            )
        except FREDError as exc:
            failed.append(f"{family_id} (rel_id={family.release_calendar_id}): {exc}")
            continue

        for rd in dates:
            if start <= rd.date <= end:
                out.append(
                    ScheduledRelease(
                        family_id=family_id,
                        display_name=family.display_name,
                        tier=family.tier,
                        cadence=family.cadence,
                        release_date=rd.date,
                        release_time_et=family.release_time_et,
                        fred_release_id=family.release_calendar_id,
                    )
                )

    out.sort(key=lambda r: (r.release_date, r.release_time_et))
    return out, failed


def build_preview_payload(
    families: dict[str, FamilyConfig],
    client: FREDClient,
    today: date | None = None,
) -> tuple[str, list[dict]]:
    """Build the week-ahead preview message: text + Block Kit blocks.

    Returns (text_fallback, blocks). The text fallback is also used for
    the dry-run preview.
    """
    if today is None:
        today = datetime.now(ET).date()

    # "This week" = today through Sunday
    days_to_sunday = 6 - today.weekday()
    if today.weekday() == 6:  # Sunday — call it the start of "this week"
        this_week_end = today + timedelta(days=6)
    else:
        this_week_end = today + timedelta(days=days_to_sunday)

    # "Next 4 weeks" = day after this_week_end through +28
    lookahead_start = this_week_end + timedelta(days=1)
    lookahead_end = lookahead_start + timedelta(days=27)  # 4 weeks = 28 days

    full_window, failed = fetch_scheduled_releases(
        families=families, client=client, start=today, end=lookahead_end
    )
    this_week = [r for r in full_window if today <= r.release_date <= this_week_end]
    lookahead = [r for r in full_window if lookahead_start <= r.release_date <= lookahead_end]

    text = _build_text(today, this_week_end, this_week, lookahead, failed)
    blocks = _build_blocks(today, this_week_end, this_week, lookahead, lookahead_end, failed)
    return text, blocks


def build_preview_payload_with_failures(
    families: dict[str, FamilyConfig],
    client: FREDClient,
    today: date | None = None,
) -> tuple[str, list[dict], list[str]]:
    """Same as build_preview_payload but also returns the list of families
    whose FRED calendar fetch failed (so the CLI can surface to
    #status-reports)."""
    if today is None:
        today = datetime.now(ET).date()
    days_to_sunday = 6 - today.weekday()
    if today.weekday() == 6:
        this_week_end = today + timedelta(days=6)
    else:
        this_week_end = today + timedelta(days=days_to_sunday)
    lookahead_start = this_week_end + timedelta(days=1)
    lookahead_end = lookahead_start + timedelta(days=27)

    full_window, failed = fetch_scheduled_releases(
        families=families, client=client, start=today, end=lookahead_end
    )
    this_week = [r for r in full_window if today <= r.release_date <= this_week_end]
    lookahead = [r for r in full_window if lookahead_start <= r.release_date <= lookahead_end]
    text = _build_text(today, this_week_end, this_week, lookahead, failed)
    blocks = _build_blocks(today, this_week_end, this_week, lookahead, lookahead_end, failed)
    return text, blocks, failed


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _fmt_event_line(r: ScheduledRelease) -> str:
    """One event line: 'Tue 5/29 8:30 ET — CPI [Tier A]'."""
    weekday = r.release_date.strftime("%a")
    # Windows strftime doesn't support %-m / %-d; build manually.
    date_str = f"{r.release_date.month}/{r.release_date.day}"
    return (
        f"{weekday} {date_str}  {r.release_time_et} ET — "
        f"{r.display_name} [Tier {r.tier}]"
    )


def _build_text(
    today: date,
    this_week_end: date,
    this_week: list[ScheduledRelease],
    lookahead: list[ScheduledRelease],
    failed: list[str] | None = None,
) -> str:
    lines = []
    lines.append("📅 THIS WEEK in macro")
    if not this_week:
        lines.append("  (no Tier A or B releases scheduled)")
    else:
        for r in this_week:
            lines.append(f"  {_fmt_event_line(r)}")

    lines.append("")
    lines.append("🔭 LOOKING AHEAD — next 4 weeks (Tier A only)")
    if not lookahead:
        lines.append("  (no Tier A releases scheduled)")
    else:
        from itertools import groupby

        lookahead_a = [r for r in lookahead if r.tier == "A"]
        for _wk, group in groupby(
            lookahead_a, key=lambda r: r.release_date.isocalendar()[1]
        ):
            grp = list(group)
            week_start = min(r.release_date for r in grp)
            wk_label = f"Wk of {week_start.month}/{week_start.day}"
            names = " · ".join(
                f"{r.display_name} ({r.release_date.strftime('%a')} "
                f"{r.release_date.month}/{r.release_date.day})"
                for r in grp
            )
            lines.append(f"  {wk_label}  — {names}")

    if failed:
        lines.append("")
        lines.append(f"⚠️ {len(failed)} family/families' FRED calendar fetch failed (see #status-reports)")

    return "\n".join(lines)


def _build_blocks(
    today: date,
    this_week_end: date,
    this_week: list[ScheduledRelease],
    lookahead: list[ScheduledRelease],
    lookahead_end: date,
    failed: list[str] | None = None,
) -> list[dict]:
    blocks: list[dict] = []

    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📅 THIS WEEK in macro — week of {today.month}/{today.day}",
                "emoji": True,
            },
        }
    )

    this_week_md = "\n".join(
        f"• {_fmt_event_line(r)}" for r in this_week
    ) or "_(no Tier A or B releases scheduled)_"
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": this_week_md},
        }
    )

    # Lookahead heading + content
    blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔭 LOOKING AHEAD — through {lookahead_end.month}/{lookahead_end.day}",
                "emoji": True,
            },
        }
    )

    from itertools import groupby

    lookahead_a = [r for r in lookahead if r.tier == "A"]
    if not lookahead_a:
        lookahead_md = "_(no Tier A releases scheduled)_"
    else:
        lines = []
        for _wk, group in groupby(
            lookahead_a, key=lambda r: r.release_date.isocalendar()[1]
        ):
            grp = list(group)
            week_start = min(r.release_date for r in grp)
            wk_label = f"*Wk of {week_start.month}/{week_start.day}*"
            names = " · ".join(
                f"{r.display_name} ({r.release_date.strftime('%a')} {r.release_date.month}/{r.release_date.day})"
                for r in grp
            )
            lines.append(f"{wk_label} — {names}")
        lookahead_md = "\n".join(lines)

    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": lookahead_md},
        }
    )

    if failed:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"⚠️ {len(failed)} family/families' FRED calendar failed; see #status-reports.",
                    }
                ],
            }
        )

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "_Tier A only in 4-week lookahead. FOMC events surface in their own family._"}]})

    return blocks
