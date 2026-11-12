"""Sunday week-ahead preview.

Goal 1 of the project: "This Week" (Tier A + B, detailed) AND
"Looking Ahead — Next 4 Weeks" (Tier A only, compact) in a single
Slack post. Source: FRED /releases/dates for every scheduled family
(any tier with a release_calendar_id; see config.calendar_families).

Run via: `python -m macro_monitor.cli weekly-preview [--post]`
"""

from __future__ import annotations

import calendar as _calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import fomc
from ..collectors.fred import FREDClient, FREDError, ReleaseDate
from ..config import TIER_A_MANDATED_TOPICS, FamilyConfig, calendar_families

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
    # True when the family covers a TIER_A_MANDATED_TOPIC (consumer
    # spending / employment / real hourly earnings) — the releases JP cares
    # most about. Surfaced as a ⭐ on the preview line. Defaulted so older
    # construction sites / tests don't need to pass it.
    priority: bool = False

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

        is_priority = bool(set(family.topics) & TIER_A_MANDATED_TOPICS)
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
                        priority=is_priority,
                    )
                )

    out.sort(key=lambda r: (r.release_date, r.release_time_et))
    return out, failed


# ---------------------------------------------------------------------------
# "Period covered" derivation
#
# A future release's reference period can't be guessed from a fixed
# release-to-data lag — that lag varies by series (CPI/payrolls cover the
# prior month; trade balance / JOLTS / consumer credit lag two months). So
# instead of fabricating a period, we take each family's ACTUAL last-published
# period from outputs/latest/<id>.json and advance it exactly one cadence
# step. If a family has never published (no latest file) we omit the period
# and show cadence only — never a guess.
# ---------------------------------------------------------------------------


def _next_period_covered(period_key: str, cadence: str) -> str | None:
    """Advance a last-published `period_key` one cadence step and format it
    the same way `release_runner.period_label` does. Returns None for
    cadences without a period concept (e.g. per_meeting) or a malformed key.
    """
    try:
        if cadence == "monthly":
            y, m = (int(x) for x in period_key.split("-")[:2])
            m += 1
            if m == 13:
                m, y = 1, y + 1
            return f"{_calendar.month_name[m]} {y}"
        if cadence == "quarterly":
            y_str, q_str = period_key.split("-Q")
            y, q = int(y_str), int(q_str) + 1
            if q == 5:
                q, y = 1, y + 1
            return f"Q{q} {y}"
        if cadence == "weekly":
            d = date.fromisoformat(period_key) + timedelta(days=7)
            return f"Week ending {d.strftime('%b %d, %Y')}"
    except (ValueError, IndexError):
        return None
    return None


def _last_yoy_reading(headline: list[dict]) -> str | None:
    """Format the most recent YoY reading from a family's FIRST headline
    series (the topline metric). Checks the primary transform first, then
    `also_display`, for a `yoy_pct` value. Returns None when the headline
    carries no YoY at all — levels like the unemployment rate, weekly
    jobless claims, or a $ trade balance — so the caller shows no YoY
    rather than a misleading one.
    """
    if not headline:
        return None
    h0 = headline[0] or {}
    primary = h0.get("primary") or {}
    if primary.get("transform") == "yoy_pct" and primary.get("value") is not None:
        return f"{primary['value']:+.2f}% YoY"
    for d in h0.get("also_display") or []:
        if d.get("transform") == "yoy_pct" and d.get("value") is not None:
            return f"{d['value']:+.2f}% YoY"
    return None


def load_preview_extras(
    families: dict[str, FamilyConfig],
    outputs_dir=None,
) -> dict[str, dict]:
    """Map family `display_name` → `{'covers': <period label>, 'yoy':
    <last YoY reading>}` for the upcoming-release preview lines, in a single
    pass over outputs/latest/. Both keys are optional/omitted when not
    derivable:

      - `covers`: the last-published period advanced one cadence step (the
        honest, lag-agnostic "period this release will cover"). Omitted when
        the family has never published.
      - `yoy`: the most recent YoY reading from the first headline series.
        Omitted for level series with no YoY (unemployment rate, claims, the
        trade balance, …).

    Keyed on display_name (stable across the config key vs the slugified
    latest-file name). A family with neither piece is dropped entirely so the
    caller falls back to cadence-only — never a fabricated value.
    """
    import json
    from pathlib import Path

    if outputs_dir is None:
        outputs_dir = Path(__file__).resolve().parents[1] / "outputs"
    latest_dir = Path(outputs_dir) / "latest"
    if not latest_dir.is_dir():
        return {}

    cadence_by_name = {f.display_name: f.cadence for f in families.values()}
    out: dict[str, dict] = {}
    for jf in sorted(latest_dir.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = data.get("family_display_name")
        if not name or name not in cadence_by_name:
            continue
        extra: dict[str, str] = {}
        period = data.get("period")
        if period:
            label = _next_period_covered(period, cadence_by_name[name])
            if label:
                extra["covers"] = label
        yoy = _last_yoy_reading(data.get("headline") or [])
        if yoy:
            extra["yoy"] = yoy
        if extra:
            out[name] = extra
    return out


def build_preview_payload(
    families: dict[str, FamilyConfig],
    client: FREDClient,
    today: date | None = None,
    extras: dict[str, dict] | None = None,
) -> tuple[str, list[dict]]:
    """Build the week-ahead preview message: text + Block Kit blocks.

    Returns (text_fallback, blocks). The text fallback is also used for
    the dry-run preview. `extras` maps display_name → {'covers', 'yoy'}
    (see load_preview_extras); when None, only cadence is shown.
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

    fomc_info = fomc.week_ahead(today, this_week_end)
    text = _build_text(today, this_week_end, this_week, lookahead, failed, extras, fomc_info)
    blocks = _build_blocks(today, this_week_end, this_week, lookahead, lookahead_end, failed, extras, fomc_info)
    return text, blocks


def build_preview_payload_with_failures(
    families: dict[str, FamilyConfig],
    client: FREDClient,
    today: date | None = None,
    extras: dict[str, dict] | None = None,
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
    fomc_info = fomc.week_ahead(today, this_week_end)
    text = _build_text(today, this_week_end, this_week, lookahead, failed, extras, fomc_info)
    blocks = _build_blocks(today, this_week_end, this_week, lookahead, lookahead_end, failed, extras, fomc_info)
    return text, blocks, failed


def build_reminder_payload(
    families: dict[str, FamilyConfig],
    client: FREDClient,
    today: date | None = None,
    extras: dict[str, dict] | None = None,
) -> tuple[str, list[dict], list[str]]:
    """Day-before heads-up: every release (ALL tiers) scheduled for TOMORROW.

    Returns (text_fallback, blocks, failed_family_ids). Unlike the weekly
    preview's 4-week lookahead — which is Tier A only — this reminder shows
    every tier so a Tier B print (housing, durable goods, consumer credit,
    ADP, …) the user cares about isn't silently dropped the night before.
    `extras` maps display_name → {'covers', 'yoy'} (cadence is always shown;
    the period + last YoY only when derivable).
    """
    if today is None:
        today = datetime.now(ET).date()
    tomorrow = today + timedelta(days=1)

    releases, failed = fetch_scheduled_releases(
        families=families, client=client, start=tomorrow, end=tomorrow
    )

    text = _build_reminder_text(tomorrow, releases, failed, extras)
    blocks = _build_reminder_blocks(tomorrow, releases, failed, extras)
    return text, blocks, failed


def _build_reminder_text(
    day: date,
    releases: list[ScheduledRelease],
    failed: list[str] | None = None,
    extras: dict[str, dict] | None = None,
) -> str:
    weekday = day.strftime("%A")
    lines = [f"🔔 RELEASING TOMORROW ({weekday} {day.month}/{day.day}) — all tiers"]
    if not releases:
        lines.append("  (no scheduled macro releases tomorrow)")
    else:
        for r in releases:
            lines.append(f"  {_fmt_event_line(r, extras)}")
    if failed:
        lines.append("")
        lines.append(
            f"⚠️ {len(failed)} family/families' FRED calendar fetch failed "
            f"(see #status-reports)"
        )
    return "\n".join(lines)


def _build_reminder_blocks(
    day: date,
    releases: list[ScheduledRelease],
    failed: list[str] | None = None,
    extras: dict[str, dict] | None = None,
) -> list[dict]:
    blocks: list[dict] = []
    weekday = day.strftime("%A")
    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔔 Releasing tomorrow — {weekday} {day.month}/{day.day}",
                "emoji": True,
            },
        }
    )
    if not releases:
        body = "_(no scheduled macro releases tomorrow)_"
    else:
        body = "\n".join(f"• {_fmt_event_line(r, extras)}" for r in releases)
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body}})

    if failed:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"⚠️ {len(failed)} family/families' FRED calendar "
                            f"failed; see #status-reports."
                        ),
                    }
                ],
            }
        )
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "_⭐ = priority release (consumer spending / employment "
                        "/ real hourly earnings). All tiers shown. Each line: "
                        "cadence · period covered · last YoY (when known). "
                        "FOMC events surface in their own family._"
                    ),
                }
            ],
        }
    )
    return blocks


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _fmt_event_line(
    r: ScheduledRelease, extras: dict[str, dict] | None = None
) -> str:
    """One event line, e.g.:
    '⭐ Tue 5/29  8:30 ET — Retail Sales [Tier A] · monthly · covers May 2026 · last +4.87% YoY'.

    A leading ⭐ marks a priority release (consumer spending / employment /
    real hourly earnings — the topics JP cares most about). Cadence is
    always shown; the covered period and last YoY are appended when
    derivable for that family (see load_preview_extras).
    """
    weekday = r.release_date.strftime("%a")
    # Windows strftime doesn't support %-m / %-d; build manually.
    date_str = f"{r.release_date.month}/{r.release_date.day}"
    star = "⭐ " if r.priority else ""
    line = (
        f"{star}{weekday} {date_str}  {r.release_time_et} ET — "
        f"{r.display_name} [Tier {r.tier}] · {r.cadence}"
    )
    info = (extras or {}).get(r.display_name) or {}
    if info.get("covers"):
        line += f" · covers {info['covers']}"
    if info.get("yoy"):
        line += f" · last {info['yoy']}"
    return line


def _build_text(
    today: date,
    this_week_end: date,
    this_week: list[ScheduledRelease],
    lookahead: list[ScheduledRelease],
    failed: list[str] | None = None,
    extras: dict[str, dict] | None = None,
    fomc: dict | None = None,
) -> str:
    lines = []
    lines.append("📅 THIS WEEK in macro")
    for fl in (fomc or {}).get("this_week", []):
        lines.append(f"  {fl}")
    if not this_week:
        lines.append("  (no Tier A or B releases scheduled)")
    else:
        for r in this_week:
            lines.append(f"  {_fmt_event_line(r, extras)}")

    lines.append("")
    lines.append("🔭 LOOKING AHEAD — next 4 weeks (Tier A only)")
    if (fomc or {}).get("next_line"):
        lines.append(f"  {fomc['next_line']}")
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
    extras: dict[str, dict] | None = None,
    fomc: dict | None = None,
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

    # FOMC meeting / blackout block leads the week when relevant (most market-
    # moving thing of the week). Source: macro_monitor.fomc (fixed meeting
    # calendar + blackout rule), independent of the FRED release calendar.
    fomc_this_week = (fomc or {}).get("this_week", [])
    if fomc_this_week:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(fomc_this_week)},
            }
        )

    this_week_md = "\n".join(
        f"• {_fmt_event_line(r, extras)}" for r in this_week
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

    next_line = (fomc or {}).get("next_line")
    if next_line:
        lookahead_md = f"{next_line}\n{lookahead_md}"

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

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "_⭐ = priority release (consumer spending / employment / real hourly earnings). Tier A only in 4-week lookahead. FOMC events surface in their own family._"}]})

    return blocks


# ---------------------------------------------------------------------------
# Table posts: the Sunday week-ahead table and the month-ahead Tier A table
# (JP 2026-11-12: "a table of upcoming releases for the week with Tier A or B
# noted", and one for the upcoming month posted on the last day of the prior
# month).
#
# The table is a Block Kit `table` block. Every table post also carries a
# bullet-list FALLBACK, and `post_with_table_fallback` retries with it when
# Slack rejects the blocks -- the schedule must land even if the table does
# not. Slack places a table at the bottom of its message, so each table post
# is built with the table LAST and the 4-week lookahead goes in the thread.
# ---------------------------------------------------------------------------

_STAR_LEGEND = (
    "_⭐ = priority release (consumer spending / employment / real hourly earnings)._"
)


@dataclass(frozen=True)
class TablePost:
    text: str                      # notification / plain-text fallback
    blocks: list[dict]             # with the table block
    fallback_blocks: list[dict]    # same content as a bullet list
    failed: list[str]
    thread_text: str | None = None
    thread_blocks: list[dict] | None = None


def table_block(header: list[str], rows: list[list[str]]) -> dict:
    """A Block Kit table: first row is the header. Cells are plain text;
    an empty cell is sent as an en dash because Slack rejects empty text."""

    def cell(v: str) -> dict:
        return {"type": "raw_text", "text": v if v and v.strip() else "–"}

    return {
        "type": "table",
        "column_settings": [{"is_wrapped": True} for _ in header],
        "rows": [[cell(h) for h in header]] + [[cell(c) for c in r] for r in rows],
    }


def _day(d: date) -> str:
    return f"{d.strftime('%a')} {d.month}/{d.day}"


def _week_window(today: date) -> tuple[date, date, date]:
    """(this_week_end, lookahead_start, lookahead_end) -- the same windows the
    original preview used: today through Sunday, then the next 4 weeks."""
    days = 6 if today.weekday() == 6 else 6 - today.weekday()
    this_week_end = today + timedelta(days=days)
    lookahead_start = this_week_end + timedelta(days=1)
    return this_week_end, lookahead_start, lookahead_start + timedelta(days=27)


def _notes_block(notes: list[str]) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": n} for n in notes]}


def _failed_note(failed: list[str]) -> str:
    return f"⚠️ {len(failed)} FRED calendar fetch(es) failed; see #status-reports."


def build_weekly_post(
    families: dict[str, FamilyConfig],
    client: FREDClient,
    today: date | None = None,
    extras: dict[str, dict] | None = None,
) -> TablePost:
    """Week-ahead table (Tier A + B, tier in its own column); the 4-week
    Tier A lookahead rides in the thread."""
    if today is None:
        today = datetime.now(ET).date()
    this_week_end, lookahead_start, lookahead_end = _week_window(today)
    full_window, failed = fetch_scheduled_releases(
        families=families, client=client, start=today, end=lookahead_end
    )
    this_week = [r for r in full_window if today <= r.release_date <= this_week_end]
    lookahead = [r for r in full_window if lookahead_start <= r.release_date <= lookahead_end]
    fomc_info = fomc.week_ahead(today, this_week_end)

    head: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📅 THIS WEEK in macro — week of {today.month}/{today.day}",
                "emoji": True,
            },
        }
    ]
    if fomc_info.get("this_week"):
        head.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(fomc_info["this_week"])},
            }
        )
    notes: list[str] = []
    if any(r.priority for r in this_week):
        notes.append(_STAR_LEGEND)
    if failed:
        notes.append(_failed_note(failed))
    notes.append("_Next 4 weeks (Tier A) in the thread._")

    if this_week:
        rows = []
        for r in this_week:
            info = (extras or {}).get(r.display_name) or {}
            rows.append(
                [
                    _day(r.release_date),
                    r.release_time_et,
                    r.tier,
                    ("⭐ " if r.priority else "") + r.display_name,
                    info.get("covers", ""),
                    info.get("yoy", ""),
                ]
            )
        body = table_block(["Day", "ET", "Tier", "Release", "Covers", "Last"], rows)
        bullets = "\n".join(f"• {_fmt_event_line(r, extras)}" for r in this_week)
    else:
        bullets = "_(no Tier A or B releases scheduled)_"
        body = {"type": "section", "text": {"type": "mrkdwn", "text": bullets}}
    fallback_body = {"type": "section", "text": {"type": "mrkdwn", "text": bullets}}

    # Lookahead (thread): reuse the original renderer's lookahead half.
    old = _build_blocks(
        today, this_week_end, this_week, lookahead, lookahead_end, None, extras, fomc_info
    )
    cut = next(i for i, b in enumerate(old) if b.get("type") == "divider")
    thread_blocks = old[cut + 1 : cut + 3]   # lookahead header + section
    text = _build_text(today, this_week_end, this_week, lookahead, failed, extras, fomc_info)
    week_text, _, look_text = text.partition("\n\n")

    return TablePost(
        text=week_text,
        blocks=head + [_notes_block(notes), body],
        fallback_blocks=head + [fallback_body, _notes_block(notes)],
        failed=failed,
        thread_text=look_text or None,
        thread_blocks=thread_blocks,
    )


def next_month_window(today: date) -> tuple[date, date]:
    """First and last day of the calendar month after `today`'s."""
    y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return date(y, m, 1), date(y, m, _calendar.monthrange(y, m)[1])


def is_last_day_of_month(today: date) -> bool:
    return (today + timedelta(days=1)).day == 1


def build_monthly_post(
    families: dict[str, FamilyConfig],
    client: FREDClient,
    today: date | None = None,
) -> TablePost:
    """Month-ahead table: every Tier A release (plus FOMC decision days) in
    the calendar month after `today`'s. No "covers" column -- a period a
    month out would be a guess (see the note above _next_period_covered)."""
    if today is None:
        today = datetime.now(ET).date()
    first, last = next_month_window(today)
    label = f"{_calendar.month_name[first.month]} {first.year}"
    releases, failed = fetch_scheduled_releases(
        families=families, client=client, start=first, end=last
    )
    tier_a = [r for r in releases if r.tier == "A"]

    events: list[tuple[date, str, str]] = [
        (r.release_date, r.release_time_et, ("⭐ " if r.priority else "") + r.display_name)
        for r in tier_a
    ]
    for m in fomc.all_meetings():
        if first <= m.end <= last:
            sep = " + projections (dot plot)" if m.projections else ""
            events.append((m.end, "14:00", f"🏛️ FOMC rate decision{sep}"))
    events.sort(key=lambda e: (e[0], e[1]))

    title = f"🗓️ {label} — Tier A releases"
    head: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": title, "emoji": True}}
    ]
    notes: list[str] = []
    if any(r.priority for r in tier_a):
        notes.append(_STAR_LEGEND)
    if failed:
        notes.append(_failed_note(failed))
    notes.append("_Tier A only. Tier B is in the Sunday week-ahead table._")

    if events:
        body = table_block(
            ["Date", "ET", "Release"], [[_day(d), t, name] for d, t, name in events]
        )
        bullets = "\n".join(f"• {_day(d)}  {t} ET — {name}" for d, t, name in events)
    else:
        bullets = "_(no Tier A releases on the calendar yet)_"
        body = {"type": "section", "text": {"type": "mrkdwn", "text": bullets}}
    return TablePost(
        text=title + "\n" + bullets.replace("• ", "  "),
        blocks=head + [_notes_block(notes), body],
        fallback_blocks=head
        + [{"type": "section", "text": {"type": "mrkdwn", "text": bullets}}, _notes_block(notes)],
        failed=failed,
    )


_TABLE_REJECTIONS = {"invalid_blocks", "invalid_blocks_format", "invalid_attachments"}


def post_with_table_fallback(slack_client, channel: str, post: TablePost) -> tuple[str, bool]:
    """Post `post`; if Slack rejects the blocks, re-post the bullet-list
    fallback so the schedule still lands. Returns (ts, used_table). The
    thread part (if any) is best-effort: a lost lookahead must not fail a
    landed table."""
    import sys

    from slack_sdk.errors import SlackApiError

    used_table = True
    try:
        resp = slack_client.chat_postMessage(
            channel=channel, text=post.text, blocks=post.blocks
        )
    except SlackApiError as e:
        err = e.response.get("error")
        if err not in _TABLE_REJECTIONS:
            raise
        print(f"  ⚠️ Slack rejected the table ({err}); posting the list fallback.", file=sys.stderr)
        used_table = False
        resp = slack_client.chat_postMessage(
            channel=channel, text=post.text, blocks=post.fallback_blocks
        )
    ts = resp["ts"]
    if post.thread_blocks:
        try:
            slack_client.chat_postMessage(
                channel=channel,
                thread_ts=ts,
                text=post.thread_text or "Looking ahead",
                blocks=post.thread_blocks,
            )
        except SlackApiError as e:
            print(f"  ⚠️ lookahead thread failed: {e.response.get('error')}", file=sys.stderr)
    return ts, used_table
