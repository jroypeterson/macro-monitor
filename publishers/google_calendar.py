"""Google Calendar publisher — creates release events on the dedicated
calendars in floridabusinessman@gmail.com. Scope is every family with a
FRED release_calendar_id (all tiers); see config.calendar_families.

Routing by tier:
  - Tier A   -> GOOGLE_CALENDAR_ID       (the "Tier 1" macro calendar)
  - Tier B/C -> GOOGLE_CALENDAR_ID_OTHER (the "other" macro calendar)
If GOOGLE_CALENDAR_ID_OTHER is unset, every tier goes to GOOGLE_CALENDAR_ID
(the original single-calendar behaviour). When it IS set, non-Tier-A
events are also deleted from the Tier A calendar so events created before
the split don't linger there.

Auth: SERVICE ACCOUNT (shared with earnings-agent). NOT user OAuth.
The calendar is shared with the earnings-agent service account at
"Make changes to events"; credentials.json is reused.

Idempotency: each event gets a stable client-generated `id` derived from
(family_id, release_date) so re-running the backfill won't create
duplicates. Uses calendar.events().insert with the supplied id; falls
back to .update if the id already exists.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..config import FamilyConfig

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class CalendarEvent:
    """One scheduled event to push into Google Calendar."""

    family_id: str
    display_name: str
    tier: str
    release_date: date
    release_time_et: str
    fred_release_id: int
    google_event_id: str  # stable, deterministic — for idempotent upsert
    cadence: str = ""  # weekly / monthly / quarterly / per_meeting


_FREQUENCY = {"per_meeting": "Per FOMC meeting"}


def frequency_label(cadence: str) -> str:
    """'monthly' -> 'Monthly'; '' -> ''."""
    return _FREQUENCY.get(cadence, cadence.replace("_", " ").capitalize())


def _execute(request, tries: int = 6):
    """Execute with exponential backoff on Google's rate-limit and 5xx
    responses — a full backfill is 2-3 calls per event and trips the
    per-calendar limit ("Rate Limit Exceeded", HTTP 403) without it."""
    import time as _time

    for n in range(tries):
        try:
            return request.execute()
        except Exception as e:  # noqa: BLE001
            status = getattr(getattr(e, "resp", None), "status", None)
            limited = status == 429 or (status == 403 and "ateLimitExceeded" in str(e))
            if n == tries - 1 or not (limited or (status or 0) >= 500):
                raise
            _time.sleep(min(2 ** n, 30))


def _stable_event_id(family_id: str, release_date: date) -> str:
    """Google Calendar accepts user-provided event IDs (max 1024 chars,
    base32hex lowercase). We hash (family_id, release_date) so re-running
    the backfill is idempotent."""
    raw = f"mm-{family_id}-{release_date.isoformat()}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    # Calendar event IDs must be base32hex (0-9, a-v) and 5-1024 chars.
    # Hex digest is 40 chars all in [0-9a-f] which is a strict subset, so safe.
    return f"mm{digest}"


def build_events_from_schedule(
    families: dict[str, FamilyConfig], scheduled_releases
) -> list[CalendarEvent]:
    """Convert a list of ScheduledRelease (from the weekly_preview module)
    into CalendarEvent objects ready to push to Google Calendar."""
    out: list[CalendarEvent] = []
    for r in scheduled_releases:
        out.append(
            CalendarEvent(
                family_id=r.family_id,
                display_name=r.display_name,
                tier=r.tier,
                release_date=r.release_date,
                release_time_et=r.release_time_et,
                fred_release_id=r.fred_release_id,
                google_event_id=_stable_event_id(r.family_id, r.release_date),
                cadence=r.cadence,
            )
        )
    return out


class GoogleCalendarPublisher:
    def __init__(
        self,
        *,
        calendar_id: str | None = None,
        other_calendar_id: str | None = None,
        credentials_path: str | None = None,
        dry_run: bool = True,
    ):
        self.calendar_id = calendar_id or os.environ.get("GOOGLE_CALENDAR_ID")
        self.other_calendar_id = (
            other_calendar_id or os.environ.get("GOOGLE_CALENDAR_ID_OTHER") or None
        )
        # Allow quoted paths in .env
        cp = credentials_path or os.environ.get("GOOGLE_CREDENTIALS_PATH")
        if cp:
            cp = cp.strip().strip('"').strip("'")
        self.credentials_path = cp
        self.dry_run = dry_run

        if not self.dry_run:
            if not self.calendar_id:
                raise RuntimeError(
                    "GOOGLE_CALENDAR_ID required for live publish; set in .env"
                )
            if not self.credentials_path or not Path(self.credentials_path).exists():
                raise RuntimeError(
                    f"GOOGLE_CREDENTIALS_PATH missing or file not found: "
                    f"{self.credentials_path!r}"
                )

    def _service(self):
        """Build a google-api-python-client Calendar service using the
        shared service-account credentials. Imported lazily so dry-runs
        don't require the google libs to be importable on import."""
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            self.credentials_path,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def calendar_for(self, ev: CalendarEvent) -> str | None:
        """Tier A -> main calendar; everything else -> the "other" calendar
        when configured, else the main calendar."""
        if ev.tier == "A" or not self.other_calendar_id:
            return self.calendar_id
        return self.other_calendar_id

    def upsert_events(self, events: list[CalendarEvent]) -> dict[str, int]:
        """Upsert events into the calendar(s). Returns counts dict:
          {"created": N, "updated": M, "removed": R, "skipped": K, "errors": [...]}
        """
        if self.dry_run:
            return {
                "created": 0, "updated": 0, "removed": 0,
                "skipped": len(events), "errors": [],
            }

        svc = self._service()
        counts = {"created": 0, "updated": 0, "removed": 0, "skipped": 0, "errors": []}

        for ev in events:
            body = self._event_body(ev)
            target = self.calendar_for(ev)
            if target != self.calendar_id:
                # Clear any pre-split copy off the Tier A calendar. A 404/410
                # just means it was never there or is already deleted.
                try:
                    _execute(svc.events().delete(
                        calendarId=self.calendar_id, eventId=ev.google_event_id
                    ))
                    counts["removed"] += 1
                except Exception as e:  # noqa: BLE001
                    if not any(c in str(e) for c in ("404", "410")):
                        counts["errors"].append(
                            f"{ev.family_id} {ev.release_date} (remove from tier A): {e}"
                        )
            try:
                _execute(svc.events().insert(calendarId=target, body=body))
                counts["created"] += 1
            except Exception as e:  # noqa: BLE001
                # If the event id collides (already exists), update.
                if "already exists" in str(e).lower() or "409" in str(e):
                    try:
                        _execute(svc.events().update(
                            calendarId=target,
                            eventId=ev.google_event_id,
                            body=body,
                        ))
                        counts["updated"] += 1
                    except Exception as e2:  # noqa: BLE001
                        counts["errors"].append(f"{ev.family_id} {ev.release_date}: {e2}")
                else:
                    counts["errors"].append(f"{ev.family_id} {ev.release_date}: {e}")

        return counts

    def _event_body(self, ev: CalendarEvent) -> dict[str, Any]:
        h, m = ev.release_time_et.split(":")
        start_et = datetime.combine(
            ev.release_date, time(int(h), int(m)), tzinfo=ET
        )
        # 1-hour block — most releases are point-in-time but a window in
        # calendar reads clearer.
        end_et = start_et + timedelta(hours=1)
        return {
            "id": ev.google_event_id,
            "summary": f"📊 {ev.display_name}",
            "description": (
                (f"Frequency: {frequency_label(ev.cadence)}\n" if ev.cadence else "")
                + f"Macro release scheduled by FRED (Tier {ev.tier}).\n"
                f"FRED release_id: {ev.fred_release_id}\n"
                f"family_id: {ev.family_id}\n"
                f"\nManaged by macro_monitor — events with id prefix `mm` are "
                f"auto-managed; manual edits may be overwritten on next backfill."
            ),
            "start": {"dateTime": start_et.isoformat(), "timeZone": "America/New_York"},
            "end": {"dateTime": end_et.isoformat(), "timeZone": "America/New_York"},
            "reminders": {"useDefault": False, "overrides": []},  # don't ping
            "transparency": "transparent",  # don't block as busy
        }
