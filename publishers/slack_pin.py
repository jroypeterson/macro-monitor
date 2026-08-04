"""Retire a superseded pinned card and pin the new one.

VENDORED ON PURPOSE, not imported from `_shared/`. These lanes run in GitHub Actions
where `<workspace>/_shared/` is not checked out, so a sys.path shim would work on the
laptop and go silently inert in CI -- which for a pin means "the stale card stays up
and nobody notices". Canonical copy + rationale:
`portfolio_daily/scripts/post_pm_overview.py`.

Requires ClaudeBot scopes `pins:read` + `pins:write` (added 2026-08-04, board #258).

THE SAFETY PROPERTY THAT MATTERS: `retire_own_pins` only ever unpins a message the BOT
wrote whose text matches the card being replaced. A pin a human put up, or another
bot's, is left alone -- "tidy up the old one" must never quietly become "removed
something someone chose to keep".
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request


def _call(token: str, method: str, payload: dict | None = None, get: bool = False):
    if get:
        url = f"https://slack.com/api/{method}?" + urllib.parse.urlencode(payload or {})
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}"}, method="GET")
    else:
        req = urllib.request.Request(
            f"https://slack.com/api/{method}",
            data=json.dumps(payload or {}).encode(),
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def retire_own_pins(token: str, channel: str, fallback_text: str) -> int:
    """Unpin this card's previous copies. Returns how many were retired.

    Call BEFORE posting the replacement: if the post then fails, the channel is left
    with no pin rather than two pinned cards that disagree with each other.
    """
    try:
        listing = _call(token, "pins.list", {"channel": channel}, get=True)
    except Exception as e:  # noqa: BLE001 - tidying must never block publishing
        print(f"[pin] pins.list failed ({e}); not retiring anything", file=sys.stderr)
        return 0
    n = 0
    for item in listing.get("items", []):
        msg = item.get("message") or {}
        if not msg.get("bot_id") or (msg.get("text") or "") != fallback_text:
            continue          # someone else's pin, or a different card - leave it
        res = _call(token, "pins.remove",
                    {"channel": channel, "timestamp": msg.get("ts")})
        if res.get("ok"):
            n += 1
        else:
            print(f"[pin] could not unpin {msg.get('ts')}: {res.get('error')}",
                  file=sys.stderr)
    return n


def pin(token: str, channel: str, ts: str) -> bool:
    """Pin a message. NON-FATAL on failure: the card has already landed in the
    channel, and failing the run here would discard work that succeeded."""
    try:
        res = _call(token, "pins.add", {"channel": channel, "timestamp": ts})
    except Exception as e:  # noqa: BLE001
        print(f"[pin] pins.add raised ({e}) - pin by hand", file=sys.stderr)
        return False
    if res.get("ok") or res.get("error") == "already_pinned":
        return True
    print(f"[pin] pins.add failed: {res.get('error')} - pin by hand", file=sys.stderr)
    return False
