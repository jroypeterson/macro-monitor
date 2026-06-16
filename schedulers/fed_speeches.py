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
from ..scoring.speech_scorer import SpeechVerdict, score_speech, score_speeches
from .speech_store import SpeechRecord, SpeechStore, export_markdown

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
    bodies: dict[str, str] = None  # {url: full_text}; filled when scoring runs


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
    bodies: dict[str, str] = {}
    if new_posts and not skip_scoring:
        if body_fetcher is None:
            body_fetcher = _fetch_speech_text
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
        bodies=bodies,
    )


# ---------------------------------------------------------------------------
# Body fetch (best-effort)
# ---------------------------------------------------------------------------


def _extract_title(html: str) -> str:
    """Pull a clean title from a Fed speech page (<title>, sans the boilerplate
    ' - Federal Reserve Board' suffix). "" if absent."""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not m:
        return ""
    t = re.sub(r"\s+", " ", m.group(1)).strip()
    for suffix in (" - Federal Reserve Board", " | Federal Reserve Board"):
        if t.endswith(suffix):
            t = t[: -len(suffix)].strip()
    return t


def _fetch_speech_page(url: str, timeout: int = 15) -> tuple[str, str]:
    """Best-effort fetch of a Fed speech page → (title, plain_text). Returns
    ("", "") on any failure. Never raises — body text is an enrichment."""
    if not url:
        return "", ""
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
        return "", ""

    title = _extract_title(html)
    # Drop scripts/styles, then strip tags and collapse whitespace.
    html = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


def _fetch_speech_text(url: str, timeout: int = 15) -> str:
    """Body-only convenience wrapper around _fetch_speech_page."""
    return _fetch_speech_page(url, timeout)[1]


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
        if v and v.worried_about:
            lines.append(f"  Worried: {'; '.join(v.worried_about)}")
        if v and v.sanguine_about:
            lines.append(f"  Sanguine: {'; '.join(v.sanguine_about)}")
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
        if v and v.worried_about:
            parts.append("⚠️ *Worried:* " + _md_escape("; ".join(v.worried_about)))
        if v and v.sanguine_about:
            parts.append("✅ *Sanguine:* " + _md_escape("; ".join(v.sanguine_about)))
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


# ---------------------------------------------------------------------------
# Archive (queryable content store) + single-URL ingest
# ---------------------------------------------------------------------------


def _speaker_from_title(title: str) -> str:
    """Fed Board RSS titles are 'Lastname, Speech Title' — grab the surname as
    a fallback when the LLM didn't identify the speaker."""
    if "," in title:
        head = title.split(",", 1)[0].strip()
        # Guard against false positives (a comma mid-title) — surnames are short.
        if head and len(head.split()) <= 3:
            return head
    return ""


def _venue_from_summary(summary: str) -> str:
    """RSS summaries read 'Speech At <venue>...' / 'At <venue>...' — strip the
    lead-in so the bare venue remains as a fallback."""
    s = (summary or "").strip()
    for prefix in ("Speech At ", "Speech at ", "At ", "Remarks At ", "Remarks at "):
        if s.startswith(prefix):
            return s[len(prefix):].strip()
    return s


def record_from(
    post: ResearchPost,
    verdict: SpeechVerdict,
    body: str,
    speaker_fallback: str = "",
) -> SpeechRecord:
    """Compose an archive record from a scored speech (LLM fields preferred,
    RSS-/URL-derived fallbacks for speaker/venue)."""
    speaker = verdict.speaker or _speaker_from_title(post.title) or speaker_fallback
    venue = verdict.venue or _venue_from_summary(post.summary)
    return SpeechRecord(
        url=post.url,
        speaker=speaker,
        venue=venue,
        title=post.title,
        source=post.source_display,
        speech_date=(post.published_at_iso or "").split("T", 1)[0],
        stance=verdict.stance,
        summary=verdict.summary,
        worried_about=verdict.worried_about,
        sanguine_about=verdict.sanguine_about,
        drivers=verdict.drivers,
        full_text=body or post.summary or "",
    )


def archive_payload(
    payload: SpeechDigestPayload, store: SpeechStore | None = None
) -> int:
    """Persist each scored speech in the payload to the content store. Idempotent
    (upsert by url). Returns the number archived. No-op if nothing was scored."""
    if not payload.verdicts:
        return 0
    own = store is None
    if own:
        store = SpeechStore()
    try:
        n = 0
        bodies = payload.bodies or {}
        for p in payload.new_posts:
            v = payload.verdicts.get(p.url)
            if v is None:
                continue
            store.upsert(record_from(p, v, bodies.get(p.url, "")))
            n += 1
        return n
    finally:
        if own:
            store.close()


def export_library(store: SpeechStore | None = None, out_path=None):
    """Regenerate the human-readable markdown library from the store."""
    own = store is None
    if own:
        store = SpeechStore()
    try:
        records = store.all_records()
    finally:
        if own:
            store.close()
    return export_markdown(records, out_path) if out_path else export_markdown(records)


_ANNUAL_INDEX = "https://www.federalreserve.gov/newsevents/speech/{year}-speeches.htm"
_SPEECH_URL_RE = re.compile(r"/newsevents/speech/([a-z]+)(\d{4})(\d{2})(\d{2})[a-z]?\.htm")


def discover_annual_speeches(year: int, index_fetcher=None) -> list[tuple[str, str, str]]:
    """Scrape the Federal Reserve Board's annual speeches index for `year`.
    Returns [(absolute_url, speaker_hint, iso_date), ...], newest first, deduped.
    The URL slug encodes the speaker surname + date, so both are exact even
    before the LLM reads the body. `index_fetcher(url)->html` is injectable."""
    url = _ANNUAL_INDEX.format(year=year)
    if index_fetcher is None:
        def index_fetcher(u):
            import requests
            r = requests.get(
                u, timeout=20,
                headers={"User-Agent": "macro-monitor/fed-speeches (+research)"},
            )
            r.raise_for_status()
            return r.text
    html = index_fetcher(url)

    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for m in _SPEECH_URL_RE.finditer(html):
        path = m.group(0)
        if path in seen:
            continue
        seen.add(path)
        speaker = m.group(1).capitalize()
        iso = f"{m.group(2)}-{m.group(3)}-{m.group(4)}"
        out.append(("https://www.federalreserve.gov" + path, speaker, iso))
    # Newest date first.
    out.sort(key=lambda t: t[2], reverse=True)
    return out


def backfill_year(
    year: int,
    store: SpeechStore | None = None,
    body_fetcher=None,
    index_fetcher=None,
    client=None,
    limit: int | None = None,
    log=print,
) -> int:
    """Archive every Board speech from `year` not already in the store. Each
    page is fetched once (title + body), summarized (worried/sanguine/stance),
    and upserted. Idempotent — re-runs skip already-archived URLs. Returns the
    number newly archived; regenerates the readable library when it owns the
    store."""
    own = store is None
    if own:
        store = SpeechStore()
    try:
        entries = discover_annual_speeches(year, index_fetcher=index_fetcher)
        todo = [e for e in entries if not store.has(e[0])]
        if limit is not None:
            todo = todo[:limit]
        log(f"  {len(entries)} {year} speeches found; {len(todo)} to archive "
            f"({len(entries) - len(todo)} already present).")
        n = 0
        for url, speaker_hint, iso in todo:
            if body_fetcher is None:
                title, body = _fetch_speech_page(url)
            else:
                title, body = "", (body_fetcher(url) or "")
            post = ResearchPost(
                source_id="fed_board_speeches",
                source_display="Federal Reserve — Speeches",
                title=title or f"{speaker_hint} speech {iso}",
                url=url,
                summary="",
                published_at_iso=iso,
            )
            verdict = score_speech(post, body, client=client)
            store.upsert(record_from(post, verdict, body, speaker_fallback=speaker_hint))
            n += 1
            log(f"    [{n}/{len(todo)}] {iso} {verdict.speaker or speaker_hint} "
                f"· {verdict.stance}")
        if own:
            export_library(store=store)
        return n
    finally:
        if own:
            store.close()


def ingest_url(
    url: str,
    title: str | None = None,
    source: str = "manual",
    body_fetcher=None,
    client=None,
) -> tuple[ResearchPost, SpeechVerdict, str]:
    """Fetch + score a single speech by URL (for off-feed / outside-venue talks).
    Returns (post, verdict, body). The body fetch + LLM call are best-effort —
    a fetch miss still yields a (neutral) verdict so nothing silently drops."""
    if body_fetcher is None:
        body_fetcher = _fetch_speech_text
    try:
        body = body_fetcher(url) or ""
    except Exception:  # noqa: BLE001
        body = ""
    post = ResearchPost(
        source_id=source,
        source_display=source,
        title=(title or "").strip() or url.rsplit("/", 1)[-1],
        url=url,
        summary="",
        published_at_iso="",
    )
    verdict = score_speech(post, body, client=client)
    # If the title was a URL slug, upgrade it from what the LLM identified.
    if not title and (verdict.speaker or verdict.venue):
        nicer = " — ".join(x for x in [verdict.speaker, verdict.venue] if x)
        if nicer:
            post = ResearchPost(
                source_id=post.source_id, source_display=post.source_display,
                title=nicer, url=post.url, summary=post.summary,
                published_at_iso=post.published_at_iso,
            )
    return post, verdict, body
