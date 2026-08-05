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

from ..collectors.gmail import (
    GmailSender,
    fetch_all_senders,
    gmail_url_from_dedupe_key,
    load_gmail_senders,
)
from ..collectors.rss import (
    ResearchLedger,
    ResearchPost,
    ResearchSource,
    fetch_all,
    load_sources,
)
from ..scoring.llm_scorer import ScoreVerdict, score_posts


@dataclass(frozen=True)
class DigestPayload:
    """Composed digest ready for the Slack publisher."""

    text: str
    blocks: list[dict]
    new_posts: list[ResearchPost]
    errors: list[tuple[str, str]]
    # Filled by build_digest after scoring. Empty {} = scoring skipped.
    verdicts: dict[str, ScoreVerdict]
    # Items the LLM rejected as non-macro — kept for inspection/logging.
    dropped_non_macro: list[ResearchPost]


def build_digest(
    sources: list[ResearchSource] | None = None,
    gmail_senders: list[GmailSender] | None = None,
    ledger: ResearchLedger | None = None,
    skip_gmail: bool = False,
    skip_scoring: bool = False,
) -> DigestPayload:
    """Pull RSS + Gmail sources, dedupe, score, render. Caller owns the
    Slack post. `skip_gmail=True` / `skip_scoring=True` are escape
    hatches for unit tests that don't want to open the network."""
    if sources is None:
        sources = load_sources()

    rss_posts, errors = fetch_all(sources)
    posts: list[ResearchPost] = list(rss_posts)

    if not skip_gmail:
        if gmail_senders is None:
            gmail_senders = load_gmail_senders()
        if gmail_senders:
            gmail_posts, gmail_errors = fetch_all_senders(gmail_senders)
            posts.extend(gmail_posts)
            errors.extend(gmail_errors)

    own_ledger = ledger is None
    if own_ledger:
        ledger = ResearchLedger()
    try:
        candidate_posts = ledger.filter_new(posts)
    finally:
        if own_ledger:
            ledger.close()

    # Score and drop non-macro before rendering. Scoring is a single
    # batched LLM call; on any failure it returns permissive verdicts so
    # we never silently empty the digest.
    verdicts: dict[str, ScoreVerdict] = {}
    dropped: list[ResearchPost] = []
    new_posts = candidate_posts
    if candidate_posts and not skip_scoring:
        verdicts = score_posts(candidate_posts)
        kept: list[ResearchPost] = []
        for p in candidate_posts:
            v = verdicts.get(p.url)
            if v is None or v.is_macro:
                kept.append(p)
            else:
                dropped.append(p)
        new_posts = kept

    text = _render_text(new_posts, errors, verdicts)
    blocks = _render_blocks(new_posts, errors, verdicts)
    return DigestPayload(
        text=text,
        blocks=blocks,
        new_posts=new_posts,
        errors=errors,
        verdicts=verdicts,
        dropped_non_macro=dropped,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _group_by_source(
    posts: list[ResearchPost],
    verdicts: dict[str, ScoreVerdict] | None = None,
) -> dict[str, list[ResearchPost]]:
    """Preserve YAML source order in the rendered output. Within each
    source, sort by LLM read-worthiness score desc when verdicts are
    available — so the best item per source appears on top."""
    seen_order = []
    grouped: dict[str, list[ResearchPost]] = defaultdict(list)
    for p in posts:
        if p.source_display not in grouped:
            seen_order.append(p.source_display)
        grouped[p.source_display].append(p)

    if verdicts:
        def _score(p: ResearchPost) -> int:
            v = verdicts.get(p.url)
            return v.score if v else 0
        for name in seen_order:
            grouped[name].sort(key=_score, reverse=True)

    return {name: grouped[name] for name in seen_order}


def _score_badge(score: int) -> str:
    """Visual prefix for the score. Used in both text + blocks."""
    if score >= 9:
        return f"🔥 {score}/10"
    if score >= 7:
        return f"⭐ {score}/10"
    if score >= 5:
        return f"• {score}/10"
    return f"○ {score}/10"


TOP_PICKS_THRESHOLD = 7
TOP_PICKS_CAP = 7
TOP_PICKS_FALLBACK_FLOOR = 3  # if NOTHING hits the threshold, take top-3 by score


def _top_picks(
    posts: list[ResearchPost],
    verdicts: dict[str, ScoreVerdict],
) -> list[ResearchPost]:
    """Curated top-N across all sources, sorted by score desc.
    Default: every item with score >= TOP_PICKS_THRESHOLD, capped at
    TOP_PICKS_CAP. If a thin day produces zero items >= threshold, fall
    back to the top TOP_PICKS_FALLBACK_FLOOR by score so the section
    isn't blank."""
    if not posts or not verdicts:
        return []
    scored = [
        (verdicts[p.url].score if p.url in verdicts else 0, p)
        for p in posts
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    picks = [p for s, p in scored if s >= TOP_PICKS_THRESHOLD][:TOP_PICKS_CAP]
    if not picks:
        picks = [p for s, p in scored[:TOP_PICKS_FALLBACK_FLOOR]]
    return picks


def _fmt_pub_date(iso: str) -> str:
    """Render an ISO8601 timestamp as 'May 28' (or '' if missing/invalid)."""
    if not iso:
        return ""
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return dt.strftime("%b %-d") if hasattr(dt, "strftime") else ""


def _fmt_pub_date_portable(iso: str) -> str:
    """Windows strftime doesn't accept %-d. Build the format manually."""
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


def _render_text(
    new_posts: list[ResearchPost],
    errors: list[tuple[str, str]],
    verdicts: dict[str, ScoreVerdict] | None = None,
) -> str:
    """Plain-text fallback for the Slack `text` field."""
    if not new_posts:
        return "macro-monitor: no new Fed/macro research today."
    lines = [f"🏛️ NEW MACRO RESEARCH ({len(new_posts)})"]

    grouped = _group_by_source(new_posts, verdicts)

    # Curated top picks (cross-source, by score)
    picks = _top_picks(new_posts, verdicts or {})
    if picks:
        lines.append(f"\n🔥 TOP PICKS (curated, top {len(picks)}):")
        for p in picks:
            v = verdicts.get(p.url) if verdicts else None
            badge = f"[{_score_badge(v.score)}] " if v else ""
            lines.append(f"  • {badge}{p.title}  —  {p.source_display}")

    # Table of contents — sources + counts
    lines.append(f"\n📋 TABLE OF CONTENTS:")
    for source_name, posts in grouped.items():
        is_gmail = any(p.url.startswith("gmail-msg:") for p in posts)
        suffix = " 📧" if is_gmail else ""
        lines.append(f"  • {source_name} ({len(posts)}){suffix}")
    lines.append("\n— FULL DIGEST —")

    for source_name, posts in grouped.items():
        is_gmail = any(p.url.startswith("gmail-msg:") for p in posts)
        label = source_name + (" (Gmail)" if is_gmail else "")
        lines.append(f"\n{label}:")
        for p in posts:
            pub = _fmt_pub_date_portable(p.published_at_iso)
            date_suffix = f" ({pub})" if pub else ""
            display_url = (
                gmail_url_from_dedupe_key(p.url)
                if p.url.startswith("gmail-msg:")
                else p.url
            )
            v = verdicts.get(p.url) if verdicts else None
            badge = f"[{_score_badge(v.score)}] " if v else ""
            lines.append(f"  • {badge}{p.title}{date_suffix}")
            lines.append(f"    {display_url}")
    if errors:
        lines.append(f"\n⚠️ {len(errors)} source(s) failed to fetch (see #status-reports)")
    return "\n".join(lines)


def _render_blocks(
    new_posts: list[ResearchPost],
    errors: list[tuple[str, str]],
    verdicts: dict[str, ScoreVerdict] | None = None,
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

    grouped = _group_by_source(new_posts, verdicts)

    # Curated top picks (cross-source, by score) — block right under the header
    picks = _top_picks(new_posts, verdicts or {})
    if picks:
        pick_lines = [f"*🔥 TOP PICKS (curated, top {len(picks)}):*"]
        for p in picks:
            v = verdicts.get(p.url) if verdicts else None
            badge = f"`{_score_badge(v.score)}` " if v else ""
            title_md = _md_escape(p.title)
            url_md = (
                gmail_url_from_dedupe_key(p.url)
                if p.url.startswith("gmail-msg:")
                else p.url
            )
            source_md = _md_escape(p.source_display)
            pick_lines.append(
                f"{badge}<{url_md}|{title_md}>  —  _{source_md}_"
            )
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(pick_lines)},
            }
        )

    # Table of contents — sources + item counts
    toc_lines = ["*📋 TABLE OF CONTENTS:*"]
    for source_name, posts in grouped.items():
        is_gmail = any(p.url.startswith("gmail-msg:") for p in posts)
        suffix = " 📧" if is_gmail else ""
        toc_lines.append(f"• {_md_escape(source_name)} ({len(posts)}){suffix}")
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(toc_lines)},
        }
    )
    blocks.append({"type": "divider"})

    for source_name, posts in grouped.items():
        # Source subhead + bulleted entries
        is_gmail_source = any(p.url.startswith("gmail-msg:") for p in posts)
        source_label = source_name + (" 📧" if is_gmail_source else "")
        lines = [f"*{_md_escape(source_label)}*"]
        for p in posts:
            title_md = _md_escape(p.title)
            # Gmail posts carry "gmail-msg:<id>" as the dedupe key; swap
            # in the browser URL for the click-through.
            url_md = (
                gmail_url_from_dedupe_key(p.url)
                if p.url.startswith("gmail-msg:")
                else p.url
            )
            v = verdicts.get(p.url) if verdicts else None
            badge = f"`{_score_badge(v.score)}` " if v else ""
            entry = f"{badge}<{url_md}|{title_md}>"
            pub = _fmt_pub_date_portable(p.published_at_iso)
            if pub:
                entry += f" _{pub}_"
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

    # Guarded: blocks are built in a loop over new research posts, so the count
    # scales with the day's volume and can cross Slack's 50-block ceiling exactly
    # when the digest is most worth reading (#268). Splits into threaded
    # continuations rather than truncating, which would silently drop posts.
    from ..publishers.guarded_post import post_guarded

    client = WebClient(token=bot_token)
    return post_guarded(client, channel_id, payload.text, payload.blocks)


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
