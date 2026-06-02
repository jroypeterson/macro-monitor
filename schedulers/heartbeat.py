"""Tier B heartbeat to #status-reports.

Posts a daily "UP" message with project state per HEALTH_REPORTING.md:
  - macro-monitor UP
  - last release post: <ts> (<family> <period>)
  - total families tracked
  - posts-ledger entry count
  - last weekly preview run (if state tracked)
  - stale series count

Uses the SLACK_WEBHOOK_STATUS_REPORTS webhook (NOT the bot token) per the
shared per-project convention. Block Kit required (per the
feedback_slack_block_kit_required memory).
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..config import FamilyConfig
from ..outputs import outputs_root
from ..posts_ledger import DEFAULT_DB_PATH

ET = ZoneInfo("America/New_York")
PROJECT_NAME = "macro-monitor"


@dataclass(frozen=True)
class HeartbeatState:
    posts_total: int
    families_tracked: int
    last_post_ts_utc: str | None
    last_post_family_id: str | None
    last_post_period: str | None
    stale_families: list[str]
    outputs_total: int


def collect_state(
    families: dict[str, FamilyConfig], db_path: Path = DEFAULT_DB_PATH
) -> HeartbeatState:
    """Read the posts ledger + outputs/latest/ to assemble what the heartbeat
    needs. Read-only — no side effects on disk."""

    # Posts-ledger query
    posts_total = 0
    last_post = None
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            posts_total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            row = conn.execute(
                "SELECT family_id, period, posted_at FROM posts "
                "ORDER BY posted_at DESC LIMIT 1"
            ).fetchone()
            if row:
                last_post = (row["family_id"], row["period"], row["posted_at"])
        finally:
            conn.close()

    # Outputs / staleness scan
    stale_families: list[str] = []
    outputs_total = 0
    latest_dir = outputs_root() / "latest"
    if latest_dir.exists():
        for jf in latest_dir.glob("*.json"):
            outputs_total += 1
            try:
                payload = json.loads(jf.read_text(encoding="utf-8"))
                if payload.get("is_stale"):
                    stale_families.append(payload.get("family_id", jf.stem))
            except (json.JSONDecodeError, OSError):
                # Corrupt JSON shouldn't kill the heartbeat
                pass

    return HeartbeatState(
        posts_total=posts_total,
        families_tracked=len(families),
        last_post_ts_utc=last_post[2] if last_post else None,
        last_post_family_id=last_post[0] if last_post else None,
        last_post_period=last_post[1] if last_post else None,
        stale_families=stale_families,
        outputs_total=outputs_total,
    )


def build_heartbeat_blocks(state: HeartbeatState) -> tuple[str, list[dict]]:
    """Return (text fallback, Block Kit blocks) for the heartbeat post."""
    now_et = datetime.now(ET)
    now_str = now_et.strftime("%a %b %d %H:%M ET")

    last_post_str = "no posts yet"
    if state.last_post_ts_utc:
        try:
            dt = datetime.fromisoformat(state.last_post_ts_utc).astimezone(ET)
            last_post_str = (
                f"{dt.strftime('%a %b %d %H:%M ET')} — "
                f"{state.last_post_family_id} {state.last_post_period}"
            )
        except ValueError:
            last_post_str = state.last_post_ts_utc

    stale_line = ""
    if state.stale_families:
        stale_line = f"⚠️ stale: {len(state.stale_families)} family/families ({', '.join(state.stale_families)})"
    else:
        stale_line = "✅ no stale series"

    text = (
        f"{PROJECT_NAME} UP — {now_str}\n"
        f"  last post: {last_post_str}\n"
        f"  families tracked: {state.families_tracked} "
        f"(ledger entries: {state.posts_total})\n"
        f"  {stale_line}"
    )

    # Block Kit (per the feedback_slack_block_kit_required memory) —
    # plain text payload won't render with formatting in #status-reports.
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{PROJECT_NAME}* UP — _{now_str}_\n"
                    f"• Last post: `{last_post_str}`\n"
                    f"• Families tracked: *{state.families_tracked}*  "
                    f"(ledger entries: {state.posts_total}, "
                    f"outputs/latest: {state.outputs_total})\n"
                    f"• {stale_line}"
                ),
            },
        }
    ]
    return text, blocks


def send_heartbeat(blocks: list[dict], text: str) -> tuple[bool, str]:
    """Post the heartbeat to #status-reports via webhook. Returns
    (ok, message). Best-effort — failures only print to stderr (we don't
    want a heartbeat failure to escalate by, e.g., trying to send the
    failure via the same webhook)."""
    webhook = os.environ.get("SLACK_WEBHOOK_STATUS_REPORTS")
    if not webhook:
        return False, "SLACK_WEBHOOK_STATUS_REPORTS not set"
    from ..publishers.slack import requests_post_with_retry

    try:
        # Retry-with-backoff for transient-network resilience.
        resp = requests_post_with_retry(
            webhook,
            label="heartbeat",
            json={"text": text, "blocks": blocks},
            timeout=10,
        )
        if resp.status_code >= 200 and resp.status_code < 300:
            return True, f"posted ({resp.status_code})"
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return False, f"exception: {e}"
