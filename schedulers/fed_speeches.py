"""Fed-speeches digest orchestrator.

Flow (mirrors the research-digest lane):
  1. Load config/fed_speeches_sources.yaml (the Federal Reserve speeches RSS).
  2. Fetch with per-source graceful degradation.
  3. Filter out already-posted speech URLs via state/fed_speeches_posted.db.
  4. For each new speech: best-effort fetch the body, then Haiku summary +
     hawkish/dovish/neutral stance (one call per speech).
  5. If 1+ new: render a Block Kit digest + post to #macro.
  6. Record posted URLs to the ledger.
  7. Source-fetch errors surface to #status-reports (best-effort, via the CLI).

Run via: `python -m macro_monitor.cli fed-speeches [--post]`
GH Actions cron: a couple of times on business days via fed_speeches.yml.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..collectors.rss import (
    ResearchLedger,
    ResearchPost,
    ResearchSource,
    fetch_all,
    load_sources,
)
from ..scoring.speech_scorer import SpeechVerdict, score_speeches

DEFAULT_SPEECHES_SOURCES_PATH = (
    Path(__file__).parent.parent / "config" / "fed_speeches_sources.yaml"
)
SPEECH_DB_PATH = (
    Path(__file__).parent.parent / "state" / "fed_speeches_posted.db"
)


@dataclass(frozen=True)
class SpeechDigestPayload:
    """Composed Fed-speeches digest ready for the Slack publisher."""

    text: str
    blocks: list[dict]
    new_posts: list[ResearchPost]
    errors: list[tuple[str, str]]
    verdicts: dict[str, SpeechVerdict]  # {} when scoring skipped


def build_speech_digest(
    sources: list[ResearchSource] | None = None,
    ledger: ResearchLedger | None = None,
    skip_scoring: bool = False,
    body_fetcher=None,
) -> SpeechDigestPayload:
    """Pull the Fed speeches feed, dedupe, summarize+classify, render. The
    caller owns the Slack post. `skip_scoring=True` and an injectable
    `body_fetcher` are escape hatches for tests that don't open the network."""
    if sources is None:
        sources = load_sources(DEFAULT_SPEECHES_SOURCES_PATH)

    posts, errors = fetch_all(sources)

    own_ledger = ledger is None
    if own_ledger:
        ledger = ResearchLedger(SPEECH_DB_PATH)
    try:
        new_posts = ledger.filter_new(posts)
    finally:
        if own_ledger:
            ledger.close()

    verdicts: dict[str, SpeechVerdict] = {}
    if new_posts and not skip_scoring:
        if body_fetcher is None:
            body_fetcher = _fetch_speech_text
        bodies: dict[str, str] = {}
        for p in new_posts:
            try:
                bodies[p.url] = body_fetcher(p.url) or ""
            except Exception:  # noqa: BLE001 — body fetch is best-effort
                bodies[p.url] = ""
        verdicts = score_speeches(new_posts, bodies=bodies)

    text = _render_text(new_posts, errors, verdicts)
    blocks = _render_blocks(new_posts, errors, verdicts)
    return SpeechDigestPayload(
        text=text,
        blocks=blocks,
        new_posts=new_posts,
        errors=errors,
        verdicts=verdicts,
    )


# ---------------------------------------------------------------------------
# Body fetch (best-effort)
# ---------------------------------------------------------------------------


def _fetch_speech_text(url: str, timeout: int = 15) -> str:
    """Best-effort fetch + crude text-extract of a Fed speech page. Returns
    "" on any failure (the scorer then falls back to the RSS blurb). Never
    raises — body text is an enrichment, not a hard dependency."""
    if not url:
        return ""
    try:
        import requests

        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "macro-monitor/fed-speeches (+research)"},
        )
        resp.raise_for_status()
        html = resp.text
    except Exception:  # noqa: BLE001
        return ""

    # Drop scripts/styles, then strip tags and collapse whitespace.
    html = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_STANCE_BADGE = {
    "hawkish": "🦅 Hawkish",
    "dovish": "🕊️ Dovish",
    "neutral": "➖ Neutral",
}


def _stance_badge(stance: str) -> str:
    return _STANCE_BADGE.get(stance, _STANCE_BADGE["neutral"])


def _fmt_pub_date_portable(iso: str) -> str:
    """Render an ISO8601 timestamp as 'Jun 14' (Windows-safe). '' if missing."""
    if not iso:
        return ""
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    return f"{months[dt.month - 1]} {dt.day}"


def _md_escape(text: str) -> str:
    """Guard the Slack link delimiters so titles can't unbalance <…|…>."""
    return text.replace("<", "&lt;").replace(">", "&gt;").replace("|", "│")


def _stance_tally(verdicts: dict[str, SpeechVerdict]) -> str:
    """e.g. '🦅 2  🕊️ 1  ➖ 0' for the header sub-line."""
    counts = {s: 0 for s in ("hawkish", "dovish", "neutral")}
    for v in verdicts.values():
        counts[v.stance if v.stance in counts else "neutral"] += 1
    return f"🦅 {counts['hawkish']}  🕊️ {counts['dovish']}  ➖ {counts['neutral']}"


def _render_text(
    new_posts: list[ResearchPost],
    errors: list[tuple[str, str]],
    verdicts: dict[str, SpeechVerdict],
) -> str:
    """Plain-text fallback for the Slack `text` field."""
    if not new_posts:
        return "macro-monitor: no new Fed speeches today."
    lines = [f"🏛️ FED SPEECHES ({len(new_posts)})"]
    if verdicts:
        lines.append(_stance_tally(verdicts))
    for p in new_posts:
        v = verdicts.get(p.url)
        badge = f"[{_stance_badge(v.stance)}] " if v else ""
        pub = _fmt_pub_date_portable(p.published_at_iso)
        date_suffix = f" ({pub})" if pub else ""
        lines.append(f"\n• {badge}{p.title}{date_suffix}")
        if v and v.summary:
            lines.append(f"  {v.summary}")
        if v and v.drivers:
            lines.append(f"  drivers: {', '.join(v.drivers)}")
        lines.append(f"  {p.url}")
    if errors:
        lines.append(
            f"\n⚠️ {len(errors)} source(s) failed to fetch (see #status-reports)"
        )
    return "\n".join(lines)


def _render_blocks(
    new_posts: list[ResearchPost],
    errors: list[tuple[str, str]],
    verdicts: dict[str, SpeechVerdict],
) -> list[dict]:
    """Block Kit payload: header + stance tally, then one section per speech
    with a stance badge, title link, summary, and drivers."""
    if not new_posts:
        return []

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🏛️ Fed Speeches ({len(new_posts)})",
                "emoji": True,
            },
        }
    ]
    if verdicts:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Stance: {_stance_tally(verdicts)}"}
                ],
            }
        )
    blocks.append({"type": "divider"})

    for p in new_posts:
        v = verdicts.get(p.url)
        badge = _stance_badge(v.stance) if v else ""
        title_md = _md_escape(p.title)
        pub = _fmt_pub_date_portable(p.published_at_iso)
        head = f"`{badge}` <{p.url}|{title_md}>" if badge else f"<{p.url}|{title_md}>"
        if pub:
            head += f" _{pub}_"
        parts = [head]
        if v and v.summary:
            parts.append(_md_escape(v.summary))
        if v and v.drivers:
            parts.append("_drivers: " + _md_escape(", ".join(v.drivers)) + "_")
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(parts)},
            }
        )

    if errors:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"⚠️ {len(errors)} source(s) failed to fetch; "
                            "see `#status-reports`"
                        ),
                    }
                ],
            }
        )
    return blocks


# ---------------------------------------------------------------------------
# Slack publishing
# ---------------------------------------------------------------------------


def post_speeches_to_macro(payload: SpeechDigestPayload) -> tuple[bool, str]:
    """Publish the digest. Returns (ok, message). Skips entirely if no new
    speeches — the lane surfaces signal, not noise."""
    if not payload.new_posts:
        return True, "no new speeches; skipped post"

    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    channel_id = os.environ.get("SLACK_MACRO_CHANNEL_ID")
    if not bot_token or not channel_id:
        return False, "SLACK_BOT_TOKEN + SLACK_MACRO_CHANNEL_ID required"

    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    client = WebClient(token=bot_token)
    try:
        resp = client.chat_postMessage(
            channel=channel_id, text=payload.text, blocks=payload.blocks
        )
        return True, f"posted ts={resp['ts']}"
    except SlackApiError as e:
        return False, f"slack error: {e.response.get('error')}"


def record_posted(
    payload: SpeechDigestPayload, ledger: ResearchLedger | None = None
) -> None:
    """Mark each posted speech so the next run won't repost it."""
    own_ledger = ledger is None
    if own_ledger:
        ledger = ResearchLedger(SPEECH_DB_PATH)
    try:
        for p in payload.new_posts:
            ledger.record(p)
    finally:
        if own_ledger:
            ledger.close()
