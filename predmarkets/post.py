"""Deliver the prediction-market rundown: write the readable HTML panel and
post to Slack #prediction-markets (bot token, same app as the release poster)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import PREDMARKET_CHANNEL_ID

READABLE_DIR = Path(__file__).resolve().parent.parent / "readable" / "prediction_markets"


def write_readable(html: str) -> Path:
    READABLE_DIR.mkdir(parents=True, exist_ok=True)
    out = READABLE_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


def post_slack(blocks: list[dict], text: str, *, dry_run: bool = True,
               bot_token: str | None = None, channel_id: str | None = None) -> tuple[bool, str]:
    """Post the rundown to #prediction-markets. dry_run prints instead.

    Returns (ok, info). Live posting needs SLACK_BOT_TOKEN + the bot invited to
    the channel; if either is missing we degrade to a printed dry-run rather
    than crash (the readable panel is still written by the caller)."""
    bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
    channel_id = channel_id or PREDMARKET_CHANNEL_ID

    if dry_run or not bot_token:
        why = "dry-run" if dry_run else "SLACK_BOT_TOKEN unset — degraded to dry-run"
        print(f"\n=== #prediction-markets ({why}; channel {channel_id}) ===", file=sys.stderr)
        print(text, file=sys.stderr)
        return (False, why)

    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        return (False, "slack_sdk not installed")

    client = WebClient(token=bot_token)
    try:
        resp = client.chat_postMessage(channel=channel_id, text=text, blocks=blocks)
        return (True, f"posted ts={resp.get('ts')}")
    except SlackApiError as e:
        # not_in_channel = bot needs inviting; surface clearly, don't crash.
        return (False, f"Slack error: {e.response.get('error', e)}")
