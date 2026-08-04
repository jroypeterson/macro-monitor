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
import re
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


def retire_own_pins(token: str, channel: str, fallback_text: str,
                    marker: str | None = None) -> int:
    """Unpin this card's previous copies. Returns how many were retired.

    Call BEFORE posting the replacement: if the post then fails, the channel is left
    with no pin rather than two pinned cards that disagree with each other.

    PASS A `marker`. Matching on `fallback_text` alone was the first design and it is
    subtly broken: the moment a card's TITLE changes -- which is exactly what happens
    when a generator is improved -- the old copy no longer matches, is never retired,
    and quietly accumulates. Observed live on 2026-08-04: #13f ended up with a June and
    an August card pinned together, and #macro-and-markets with three.

    A `marker` is a stable string the generator always embeds (its own module path is
    ideal -- it never changes when the wording does). Any BOT-authored pinned message
    containing it is ours and is retired. Human pins never contain it, so the safety
    property that mattered is preserved.
    """
    try:
        listing = _call(token, "pins.list", {"channel": channel}, get=True)
    except Exception as e:  # noqa: BLE001 - tidying must never block publishing
        print(f"[pin] pins.list failed ({e}); not retiring anything", file=sys.stderr)
        return 0
    n = 0
    for item in listing.get("items", []):
        msg = item.get("message") or {}
        if not msg.get("bot_id"):
            continue          # a human's pin - never touch it
        if marker:
            blob = json.dumps(msg.get("blocks") or [], ensure_ascii=False)
            if marker not in blob and marker not in (msg.get("text") or ""):
                continue      # another lane's card in the same channel
        elif (msg.get("text") or "") != fallback_text:
            continue
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

def pin_is_current(token: str, channel: str, fallback_text: str,
                   blocks: list) -> bool:
    """True when the pinned card is byte-identical to the one we would post.

    THIS IS WHAT MAKES A SCHEDULED SWEEP SAFE. These cards derive every number from
    live config, so re-posting is harmless in content -- but a weekly repost would put
    a fresh message in every channel every week regardless of whether anything changed,
    which is noise, and noise is how a channel stops being read.

    Comparing first means the sweep is SILENT unless the config actually drifted. On a
    quiet week nothing is posted, nothing is unpinned, and the pin keeps its original
    date -- which is itself useful information ("this has been true since June").

    Any doubt resolves to False (i.e. do refresh): a spurious repost is a cosmetic
    cost, whereas wrongly concluding "still current" leaves a stale card asserting an
    old threshold, which is the failure the whole exercise exists to prevent.
    """
    try:
        listing = _call(token, "pins.list", {"channel": channel}, get=True)
    except Exception as e:  # noqa: BLE001
        print(f"[pin] pins.list failed ({e}); assuming a refresh is needed",
              file=sys.stderr)
        return False
    for item in listing.get("items", []):
        msg = item.get("message") or {}
        if not msg.get("bot_id") or (msg.get("text") or "") != fallback_text:
            continue
        return _canon(token, msg.get("blocks")) == _canon(token, blocks)
    return False   # no pin of ours at all -> definitely needs one

_CHAN_CACHE: dict = {}


def _expand_mentions(token: str, text: str) -> str:
    """Turn `<#C123>` / `<#C123|name>` back into `#name`.

    Slack rewrites what you post before storing it, in at least three ways, all found
    the hard way while making a change-detector stop reporting false positives:
      1. channel names -> `<#C0BKUQUPYS0>` mentions (handled here)
      2. `&` -> `&amp;`, `<` -> `&lt;`, `>` -> `&gt;` (handled here)
      3. `block_id` on every block, `verbatim: false` on every text object (handled by
         _canon's whitelist)

    SLACK REWRITES CHANNEL NAMES ON STORAGE. Post a card saying `#portfolio-management`
    and Slack stores `<#C0BKUQUPYS0>`, so a byte comparison against the stored message
    NEVER matches for any card that names a channel -- which made a change-detector
    report "changed" on every single run.

    Resolved rather than blanked on purpose: replacing every mention with a neutral
    placeholder would also hide a REAL change, e.g. a card whose routing moved from
    one channel to another. Expanding to the actual name keeps that detectable.
    """
    def repl(m):
        cid, name = m.group(1), m.group(2)
        if name:
            return "#" + name
        if cid not in _CHAN_CACHE:
            try:
                info = _call(token, "conversations.info", {"channel": cid}, get=True)
                _CHAN_CACHE[cid] = (info.get("channel") or {}).get("name") or cid
            except Exception:  # noqa: BLE001
                _CHAN_CACHE[cid] = cid
        return "#" + _CHAN_CACHE[cid]
    out = re.sub(r"<#([A-Z0-9]+)(?:\|([^>]*))?>", repl, text or "")
    # Slack also HTML-escapes &, < and > on storage, so "A & B" comes back as
    # "A &amp; B". Normalise both sides or any card containing an ampersand looks
    # changed forever.
    return (out.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))


def _canon(token: str, blocks: list) -> str:
    """Canonical form of a block list, for comparing what we would post against what
    Slack stored.

    WHITELISTS the keys we author rather than blacklisting the ones Slack adds. Slack
    decorates stored blocks with its own fields -- `block_id` on every block and
    `verbatim: false` on every text object were both found the hard way -- and a
    blacklist is a losing game: the next field Slack adds silently makes every card
    look changed, and the sweep starts reposting weekly again for no reason.
    """
    def text_obj(t):
        if not isinstance(t, dict):
            return t
        return {"type": t.get("type"),
                "text": _expand_mentions(token, t.get("text", ""))}

    out = []
    for b in blocks or []:
        b = b or {}
        keep = {"type": b.get("type")}
        if isinstance(b.get("text"), dict):
            keep["text"] = text_obj(b["text"])
        if b.get("fields"):
            keep["fields"] = [text_obj(f) for f in b["fields"]]
        if b.get("elements"):
            keep["elements"] = [text_obj(e) for e in b["elements"]]
        out.append(keep)
    return json.dumps(out, sort_keys=True, ensure_ascii=False)
