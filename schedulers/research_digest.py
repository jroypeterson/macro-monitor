"""Daily Fed-research digest orchestrator (Phase 2).

Flow:
  1. Load config/fed_research_sources.yaml
  2. Fetch all sources with per-source graceful degradation
  3. Filter out already-posted URLs via state/research_posted.db
  4. If 1+ new items: render Block Kit digest + post to #macro
  5. Record posted URLs to ledger
  6. Errors surface to #status-reports (best-effort)

Run via: `python -m macro_monitor.cli research-digest [--post]`
GH Actions cron: daily 08:00 ET via research_digest.yml workflow.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass

from ..collectors.rss import (
    ResearchLedger,
    ResearchPost,
    ResearchSource,
    fetch_all,
    load_sources,
)


@dataclass(frozen=True)
class DigestPayload:
    """Composed digest ready for the Slack publisher."""

    text: str
    blocks: list[dict]
    new_posts: list[ResearchPost]
    errors: list[tuple[str, str]]


def build_digest(
    sources: list[ResearchSource] | None = None,
    ledger: ResearchLedger | None = None,
) -> DigestPayload:
    """Pull all sources, dedupe, render. Caller owns the Slack post."""
    if sources is None:
        sources = load_sources()
    posts, errors = fetch_all(sources)

    own_ledger = ledger is None
    if own_ledger:
        ledger = ResearchLedger()
    try:
        new_posts = ledger.filter_new(posts)
    finally:
        if own_ledger:
            ledger.close()

    text = _render_text(new_posts, errors)
    blocks = _render_blocks(new_posts, errors)
    return DigestPayload(
        text=text,
        blocks=blocks,
        new_posts=new_posts,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _group_by_source(posts: list[ResearchPost]) -> dict[str, list[ResearchPost]]:
    """Preserve YAML source order in the rendered output."""
    seen_order = []
    grouped: dict[str, list[ResearchPost]] = defaultdict(list)
    for p in posts:
        if p.source_display not in grouped:
            seen_order.append(p.source_display)
        grouped[p.source_display].append(p)
    # Re-sort to preserve insertion order from `seen_order`
    return {name: grouped[name] for name in seen_order}


def _render_text(
    new_posts: list[ResearchPost], errors: list[tuple[str, str]]
) -> str:
    """Plain-text fallback for the Slack `text` field."""
    if not new_posts:
        return "macro-monitor: no new Fed/macro research today."
    lines = [f"🏛️ NEW MACRO RESEARCH ({len(new_posts)})"]
    for source_name, posts in _group_by_source(new_posts).items():
        lines.append(f"\n{source_name}:")
        for p in posts:
            lines.append(f"  • {p.title}")
            lines.append(f"    {p.url}")
    if errors:
        lines.append(f"\n⚠️ {len(errors)} source(s) failed to fetch (see #status-reports)")
    return "\n".join(lines)


def _render_blocks(
    new_posts: list[ResearchPost], errors: list[tuple[str, str]]
) -> list[dict]:
    """Block Kit payload per the v5 plan §6 format:

      🏛️ NEW MACRO RESEARCH (3)
      NY Fed Liberty Street — "Why Are Job Openings Falling?" [link]
      NBER WP — "Inflation Persistence Across Goods" [link]
      ...
    """
    if not new_posts:
        return []

    blocks: list[dict] = []
    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🏛️ NEW MACRO RESEARCH ({len(new_posts)})",
                "emoji": True,
            },
        }
    )

    for source_name, posts in _group_by_source(new_posts).items():
        # Source subhead + bulleted entries
        lines = [f"*{_md_escape(source_name)}*"]
        for p in posts:
            # <url|title> renders as a Slack hyperlink
            title_md = _md_escape(p.title)
            url_md = p.url  # Slack handles raw URL inside <…|…>
            entry = f"• <{url_md}|{title_md}>"
            if p.summary:
                excerpt = _md_escape(p.summary[:140].rstrip())
                if len(p.summary) > 140:
                    excerpt += "…"
                entry += f"\n  _{excerpt}_"
            lines.append(entry)
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(lines)},
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


def _md_escape(text: str) -> str:
    """Slack mrkdwn doesn't need much escaping — just guard the link
    delimiters that would unbalance the <…|…> syntax."""
    return text.replace("<", "&lt;").replace(">", "&gt;").replace("|", "│")


# ---------------------------------------------------------------------------
# Slack publishing
# ---------------------------------------------------------------------------


def post_to_macro(payload: DigestPayload) -> tuple[bool, str]:
    """Publish the digest. Returns (ok, message). Skips entirely if no
    new posts — the digest's job is to surface signal, not noise."""
    if not payload.new_posts:
        return True, "no new research; skipped post"

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


def record_posted(payload: DigestPayload, ledger: ResearchLedger | None = None) -> None:
    """Mark each post in the digest as posted so we don't re-post next run."""
    own_ledger = ledger is None
    if own_ledger:
        ledger = ResearchLedger()
    try:
        for p in payload.new_posts:
            ledger.record(p)
    finally:
        if own_ledger:
            ledger.close()
