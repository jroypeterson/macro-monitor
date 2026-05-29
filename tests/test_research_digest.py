"""Tests for the Fed-research RSS collector + digest renderer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from macro_monitor.collectors.rss import (
    ResearchLedger,
    ResearchPost,
    ResearchSource,
    _normalize_summary,
    fetch_all,
    fetch_source,
    load_sources,
)
from macro_monitor.schedulers.research_digest import (
    DigestPayload,
    _render_blocks,
    _render_text,
    build_digest,
    record_posted,
)


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------


def test_load_sources_reads_yaml():
    """The shipped config should load cleanly into ResearchSource objects."""
    sources = load_sources()
    assert len(sources) >= 4
    ids = {s.id for s in sources}
    assert "nber" in ids
    assert "ny_fed_liberty_street" in ids
    for s in sources:
        assert s.url.startswith("http")
        assert s.max_items_per_run > 0


# ---------------------------------------------------------------------------
# Per-source fetch
# ---------------------------------------------------------------------------


def test_fetch_source_returns_empty_with_error_on_bad_url():
    """A broken URL should return (empty list, error message) — not raise."""
    src = ResearchSource(
        id="test",
        display_name="Test",
        url="http://this-domain-definitely-does-not-resolve.invalid/feed",
        max_items_per_run=5,
    )
    posts, err = fetch_source(src)
    assert posts == []
    assert err is not None


def test_fetch_all_continues_after_one_failure():
    """One broken source must not crash the others."""
    good = ResearchSource(
        id="good", display_name="Good", url="x", max_items_per_run=2
    )
    bad = ResearchSource(
        id="bad", display_name="Bad", url="y", max_items_per_run=2
    )

    fake_post = ResearchPost(
        source_id="good", source_display="Good",
        title="A paper", url="https://example.com/p1",
        summary="", published_at_iso="",
    )

    def fake_fetch(src):
        if src.id == "good":
            return [fake_post], None
        return [], "simulated failure"

    with patch("macro_monitor.collectors.rss.fetch_source", side_effect=fake_fetch):
        posts, errors = fetch_all([good, bad])
    assert len(posts) == 1
    assert posts[0].url == "https://example.com/p1"
    assert errors == [("bad", "simulated failure")]


# ---------------------------------------------------------------------------
# Dedupe ledger
# ---------------------------------------------------------------------------


def test_ledger_roundtrip(tmp_path: Path):
    ledger = ResearchLedger(tmp_path / "test.db")
    p = ResearchPost(
        source_id="nber", source_display="NBER",
        title="Sample paper", url="https://nber.org/p/1",
        summary="", published_at_iso="",
    )
    assert not ledger.already_posted(p.url)
    ledger.record(p)
    assert ledger.already_posted(p.url)
    assert ledger.count() == 1
    ledger.close()


def test_ledger_record_is_idempotent(tmp_path: Path):
    """Same URL recorded twice should still be a single row (INSERT OR IGNORE)."""
    ledger = ResearchLedger(tmp_path / "test.db")
    p = ResearchPost(
        source_id="nber", source_display="NBER",
        title="X", url="https://nber.org/p/1",
        summary="", published_at_iso="",
    )
    ledger.record(p)
    ledger.record(p)
    assert ledger.count() == 1
    ledger.close()


def test_filter_new_drops_already_posted(tmp_path: Path):
    ledger = ResearchLedger(tmp_path / "test.db")
    p1 = ResearchPost(
        source_id="nber", source_display="NBER",
        title="Old", url="https://nber.org/p/1",
        summary="", published_at_iso="",
    )
    p2 = ResearchPost(
        source_id="nber", source_display="NBER",
        title="New", url="https://nber.org/p/2",
        summary="", published_at_iso="",
    )
    ledger.record(p1)
    filtered = ledger.filter_new([p1, p2])
    assert filtered == [p2]
    ledger.close()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _sample_post(idx: int, source_id: str = "nber", source_display: str = "NBER") -> ResearchPost:
    return ResearchPost(
        source_id=source_id,
        source_display=source_display,
        title=f"Sample paper {idx}",
        url=f"https://example.com/p/{idx}",
        summary=f"Brief summary text for paper {idx}.",
        published_at_iso="",
    )


def test_render_text_with_zero_posts_says_so():
    text = _render_text([], [])
    assert "no new" in text.lower()


def test_render_text_groups_by_source():
    posts = [
        _sample_post(1, "nber", "NBER"),
        _sample_post(2, "nber", "NBER"),
        _sample_post(3, "ny_fed", "NY Fed Liberty Street"),
    ]
    text = _render_text(posts, [])
    assert "NEW MACRO RESEARCH (3)" in text
    assert "NBER:" in text
    assert "NY Fed Liberty Street:" in text


def test_render_blocks_with_zero_posts_returns_empty():
    """No posts → empty blocks → caller skips the Slack call entirely."""
    assert _render_blocks([], []) == []


def test_render_blocks_contains_header_and_source_section():
    posts = [_sample_post(1), _sample_post(2)]
    blocks = _render_blocks(posts, [])
    assert blocks[0]["type"] == "header"
    assert "NEW MACRO RESEARCH (2)" in blocks[0]["text"]["text"]
    # at least one section per source
    section_count = sum(1 for b in blocks if b["type"] == "section")
    assert section_count >= 1


def test_render_blocks_warns_on_errors():
    posts = [_sample_post(1)]
    blocks = _render_blocks(posts, errors=[("bad_source", "404")])
    contexts = [b for b in blocks if b["type"] == "context"]
    assert contexts
    assert "failed to fetch" in contexts[-1]["elements"][0]["text"]


def test_summary_html_stripped():
    """RSS entries often have HTML in their summary; we should strip it."""
    entry = {"summary": "<p>Hello <b>world</b></p>"}
    assert _normalize_summary(entry) == "Hello world"


# ---------------------------------------------------------------------------
# Keyword filtering
# ---------------------------------------------------------------------------


def test_matches_filters_empty_lists_keeps_everything():
    from macro_monitor.collectors.rss import _matches_filters

    assert _matches_filters("any title", "any summary", (), ()) is True


def test_matches_filters_include_drops_non_matching():
    from macro_monitor.collectors.rss import _matches_filters

    include = ("inflation", "fed")
    assert _matches_filters("Tesla shares rally", "...", include, ()) is False
    assert _matches_filters("Fed pauses rate hike", "...", include, ()) is True


def test_matches_filters_include_is_case_insensitive():
    from macro_monitor.collectors.rss import _matches_filters

    assert _matches_filters(
        "Inflation Persists in Eurozone", "", ("inflation",), ()
    ) is True


def test_matches_filters_exclude_overrides_include():
    """If exclude matches, item is dropped even if include also matches."""
    from macro_monitor.collectors.rss import _matches_filters

    include = ("rates",)
    exclude = ("ipo",)
    # Title mentions both — should be dropped
    assert _matches_filters("IPO priced amid rate cut", "", include, exclude) is False


def test_matches_filters_checks_both_title_and_summary():
    from macro_monitor.collectors.rss import _matches_filters

    # Title says nothing about macro, but summary does
    assert _matches_filters(
        "Bank earnings", "CPI ran hot this morning", ("cpi",), ()
    ) is True


def test_fetch_source_applies_keyword_filter():
    """fetch_source should drop items that don't match include_keywords
    BEFORE counting against max_items_per_run. Otherwise a filter on a
    feed where most items don't match would return zero items even when
    there are matches later in the feed."""
    from unittest.mock import patch
    from macro_monitor.collectors.rss import ResearchSource, fetch_source

    # 5 entries; only entries 2 and 4 match the include filter
    fake_feed_entries = [
        {"link": "https://x/1", "title": "Apple earnings beat", "summary": "Tim Cook discusses iPhone."},
        {"link": "https://x/2", "title": "Fed pauses rates", "summary": "Powell statement."},
        {"link": "https://x/3", "title": "M&A roundup", "summary": "Two deals announced."},
        {"link": "https://x/4", "title": "GDP growth slows", "summary": "Q1 reading was 1.6%."},
        {"link": "https://x/5", "title": "Tesla recall", "summary": "Steering issue identified."},
    ]
    fake_feed = type("Feed", (), {"entries": fake_feed_entries, "bozo": False,
                                  "feed": {"title": "Test"}, "bozo_exception": None})()

    src = ResearchSource(
        id="test", display_name="Test", url="x",
        max_items_per_run=5,
        include_keywords=("fed", "gdp", "inflation"),
    )

    with patch("macro_monitor.collectors.rss.feedparser.parse", return_value=fake_feed):
        posts, err = fetch_source(src)

    assert err is None
    titles = [p.title for p in posts]
    assert "Fed pauses rates" in titles
    assert "GDP growth slows" in titles
    assert "Apple earnings beat" not in titles
    assert "Tesla recall" not in titles
    assert len(posts) == 2


# ---------------------------------------------------------------------------
# Orchestration: build_digest end-to-end
# ---------------------------------------------------------------------------


def test_build_digest_filters_already_posted(tmp_path: Path):
    """If the ledger has a URL already, build_digest excludes it from
    new_posts so we don't repost."""
    ledger = ResearchLedger(tmp_path / "test.db")
    seen = _sample_post(1)
    ledger.record(seen)

    fresh = _sample_post(2)

    src = ResearchSource(
        id="nber", display_name="NBER", url="x", max_items_per_run=10
    )

    with patch(
        "macro_monitor.schedulers.research_digest.fetch_all",
        return_value=([seen, fresh], []),
    ):
        payload = build_digest(sources=[src], ledger=ledger)

    new_urls = {p.url for p in payload.new_posts}
    assert seen.url not in new_urls
    assert fresh.url in new_urls
    ledger.close()
