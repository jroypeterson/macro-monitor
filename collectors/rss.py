"""RSS collector for the Fed/macro research digest (Phase 2).

Reads config/fed_research_sources.yaml, polls each feed via feedparser,
and returns deduplicated ResearchPost entries. Per-source graceful
degradation: a single bad feed surfaces a warning but doesn't kill the
batch.

Dedupe lives in state/research_posted.db (single SQLite table keyed by
URL) so re-runs don't re-post the same papers.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

DEFAULT_DB_PATH = Path(__file__).parent.parent / "state" / "research_posted.db"
DEFAULT_SOURCES_PATH = (
    Path(__file__).parent.parent / "config" / "fed_research_sources.yaml"
)


@dataclass(frozen=True)
class ResearchSource:
    id: str
    display_name: str
    url: str
    max_items_per_run: int = 5
    # Optional keyword filtering applied to title + summary.
    # include_keywords: if non-empty, item must contain at least one (any-match)
    # exclude_keywords: if non-empty, item dropped if it contains any
    # Both matches are case-insensitive substring matches.
    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchPost:
    """One research item — paper, blog post, working paper."""

    source_id: str
    source_display: str
    title: str
    url: str
    summary: str             # plain text (HTML stripped); may be empty
    published_at_iso: str    # ISO8601 UTC; "" if feed doesn't include it


def load_sources(path: Path | str = DEFAULT_SOURCES_PATH) -> list[ResearchSource]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [
        ResearchSource(
            id=s["id"],
            display_name=s["display_name"],
            url=s["url"],
            max_items_per_run=s.get("max_items_per_run", 5),
            include_keywords=tuple(s.get("include_keywords") or ()),
            exclude_keywords=tuple(s.get("exclude_keywords") or ()),
        )
        for s in raw.get("sources", [])
    ]


def _matches_filters(
    title: str,
    summary: str,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
) -> bool:
    """Apply optional keyword filters. Returns True if the item should be
    kept. Empty include list = no allowlist; empty exclude list = no
    blocklist. All matches are case-insensitive substring matches against
    title + summary combined."""
    haystack = f"{title} {summary}".lower()

    if exclude and any(kw.lower() in haystack for kw in exclude):
        return False

    if include and not any(kw.lower() in haystack for kw in include):
        return False

    return True


def fetch_source(source: ResearchSource) -> tuple[list[ResearchPost], str | None]:
    """Pull entries from one RSS source. Returns (posts, error_msg). If
    error_msg is non-None, the caller should surface to #status-reports
    but continue with other sources.
    """
    try:
        feed = feedparser.parse(source.url)
    except Exception as e:  # noqa: BLE001
        return [], f"feedparser raised {type(e).__name__}: {e}"

    if feed.bozo and not feed.entries:
        # Hard parse error AND empty result → real failure
        msg = str(feed.bozo_exception) if feed.bozo_exception else "parse error"
        return [], f"feed parse error: {msg}"

    posts: list[ResearchPost] = []
    # Iterate the whole feed (not just first N) so the keyword filter
    # picks the first N MATCHING items, not the first N items overall.
    for entry in feed.entries:
        if len(posts) >= source.max_items_per_run:
            break
        url = entry.get("link") or ""
        if not url:
            continue
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        summary = _normalize_summary(entry)
        if not _matches_filters(
            title, summary, source.include_keywords, source.exclude_keywords
        ):
            continue
        published = _normalize_published(entry)
        posts.append(
            ResearchPost(
                source_id=source.id,
                source_display=source.display_name,
                title=title,
                url=url,
                summary=summary,
                published_at_iso=published,
            )
        )
    return posts, None


def fetch_all(
    sources: list[ResearchSource],
) -> tuple[list[ResearchPost], list[tuple[str, str]]]:
    """Iterate sources with per-source graceful degradation. Returns
    (all_posts, [(source_id, error_msg), ...])."""
    posts: list[ResearchPost] = []
    errors: list[tuple[str, str]] = []
    for src in sources:
        items, err = fetch_source(src)
        posts.extend(items)
        if err:
            errors.append((src.id, err))
    return posts, errors


# ---------------------------------------------------------------------------
# Dedupe ledger
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS posted_research (
    url           TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL,
    title         TEXT NOT NULL,
    posted_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_posted_at
    ON posted_research(posted_at_utc);
"""


class ResearchLedger:
    """Records which research-paper URLs we've already posted so the daily
    digest doesn't repost them."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ResearchLedger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def already_posted(self, url: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM posted_research WHERE url = ?", (url,)
        ).fetchone()
        return row is not None

    def record(self, post: ResearchPost) -> None:
        """Idempotent record — INSERT OR IGNORE so we never error on dup."""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO posted_research (
                    url, source_id, title, posted_at_utc
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    post.url,
                    post.source_id,
                    post.title[:500],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM posted_research"
        ).fetchone()[0]

    def filter_new(self, posts: list[ResearchPost]) -> list[ResearchPost]:
        """Return the subset of `posts` that aren't already in the ledger."""
        return [p for p in posts if not self.already_posted(p.url)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_summary(entry: dict) -> str:
    """Strip HTML to plain text, truncate."""
    summary = entry.get("summary") or entry.get("description") or ""
    # crude HTML strip — feedparser already lowercases tag names
    import re
    text = re.sub(r"<[^>]+>", "", summary)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


def _normalize_published(entry: dict) -> str:
    """Convert published_parsed (time.struct_time) to ISO8601 UTC."""
    pp = entry.get("published_parsed") or entry.get("updated_parsed")
    if pp is None:
        return ""
    try:
        # struct_time → datetime
        ts = time.mktime(pp)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (OSError, ValueError, OverflowError):
        return ""
