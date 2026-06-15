"""Tests for the Fed-speeches digest lane."""

from __future__ import annotations

from unittest.mock import patch

from macro_monitor.collectors.rss import ResearchLedger, ResearchPost
from macro_monitor.scoring.speech_scorer import SpeechVerdict
from macro_monitor.schedulers import fed_speeches as fs


def _post(idx: int = 1, title: str | None = None) -> ResearchPost:
    return ResearchPost(
        source_id="fed_board_speeches",
        source_display="Federal Reserve — Speeches",
        title=title or f"Powell, Speech {idx}",
        url=f"https://www.federalreserve.gov/speech/{idx}.htm",
        summary=f"At venue {idx}",
        published_at_iso="2026-06-06T16:00:00+00:00",
    )


def _verdict(url: str, stance: str = "hawkish") -> SpeechVerdict:
    return SpeechVerdict(
        url=url, stance=stance, summary="A summary.", drivers=("a", "b"), why=""
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_loads_fed_speeches_source():
    from macro_monitor.collectors.rss import load_sources

    sources = load_sources(fs.DEFAULT_SPEECHES_SOURCES_PATH)
    assert len(sources) >= 1
    src = sources[0]
    assert src.id == "fed_board_speeches"
    assert "federalreserve.gov/feeds/speeches.xml" in src.url
    assert src.stale_after_days >= 30  # speeches are sporadic


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_stance_badge():
    assert "Hawkish" in fs._stance_badge("hawkish")
    assert "Dovish" in fs._stance_badge("dovish")
    assert "Neutral" in fs._stance_badge("neutral")
    assert "Neutral" in fs._stance_badge("bogus")  # unknown → neutral


def test_render_blocks_empty():
    assert fs._render_blocks([], [], {}) == []


def test_render_text_empty():
    assert "no new Fed speeches" in fs._render_text([], [], {})


def test_render_blocks_has_header_badge_and_sections():
    posts = [_post(1), _post(2)]
    verdicts = {posts[0].url: _verdict(posts[0].url, "hawkish"),
                posts[1].url: _verdict(posts[1].url, "dovish")}
    blocks = fs._render_blocks(posts, [], verdicts)
    assert blocks[0]["type"] == "header"
    assert "Fed Speeches (2)" in blocks[0]["text"]["text"]
    # stance tally context block present
    assert any(b["type"] == "context" for b in blocks)
    body = "".join(
        b["text"]["text"] for b in blocks if b.get("type") == "section"
    )
    assert "Hawkish" in body and "Dovish" in body
    assert "A summary." in body
    assert "drivers:" in body


def test_render_text_includes_summary_and_url():
    posts = [_post(1)]
    verdicts = {posts[0].url: _verdict(posts[0].url, "neutral")}
    text = fs._render_text(posts, [], verdicts)
    assert "A summary." in text
    assert posts[0].url in text


def test_render_blocks_surfaces_errors():
    posts = [_post(1)]
    blocks = fs._render_blocks(posts, [("fed_board_speeches", "boom")], {})
    assert any(
        b["type"] == "context" and "failed to fetch" in b["elements"][0]["text"]
        for b in blocks
    )


# ---------------------------------------------------------------------------
# build_speech_digest
# ---------------------------------------------------------------------------


def test_build_digest_dedupes_and_can_skip_scoring(tmp_path):
    posts = [_post(1), _post(2)]
    ledger = ResearchLedger(tmp_path / "speeches.db")
    try:
        with patch.object(fs, "fetch_all", return_value=(posts, [])):
            payload = fs.build_speech_digest(
                sources=[], ledger=ledger, skip_scoring=True
            )
        assert len(payload.new_posts) == 2
        assert payload.verdicts == {}  # scoring skipped
        # Record them, then a second run sees nothing new.
        fs.record_posted(payload, ledger=ledger)
        with patch.object(fs, "fetch_all", return_value=(posts, [])):
            payload2 = fs.build_speech_digest(
                sources=[], ledger=ledger, skip_scoring=True
            )
        assert payload2.new_posts == []
        assert payload2.blocks == []
    finally:
        ledger.close()


def test_build_digest_scores_with_injected_body_fetcher(tmp_path):
    posts = [_post(1)]
    ledger = ResearchLedger(tmp_path / "speeches.db")
    captured = {}

    def fake_body_fetcher(url):
        captured["url"] = url
        return "the speech body"

    def fake_score(p_list, bodies=None, client=None):
        captured["bodies"] = bodies
        return {p.url: _verdict(p.url, "dovish") for p in p_list}

    try:
        with patch.object(fs, "fetch_all", return_value=(posts, [])), \
                patch.object(fs, "score_speeches", side_effect=fake_score):
            payload = fs.build_speech_digest(
                sources=[], ledger=ledger, body_fetcher=fake_body_fetcher
            )
        assert captured["url"] == posts[0].url
        assert captured["bodies"][posts[0].url] == "the speech body"
        assert payload.verdicts[posts[0].url].stance == "dovish"
        assert payload.blocks[0]["type"] == "header"
    finally:
        ledger.close()


def test_build_digest_body_fetcher_failure_is_nonfatal(tmp_path):
    posts = [_post(1)]
    ledger = ResearchLedger(tmp_path / "speeches.db")

    def boom(url):
        raise RuntimeError("network down")

    def fake_score(p_list, bodies=None, client=None):
        # body fell back to "" — must still be scored
        assert bodies[p_list[0].url] == ""
        return {p.url: _verdict(p.url) for p in p_list}

    try:
        with patch.object(fs, "fetch_all", return_value=(posts, [])), \
                patch.object(fs, "score_speeches", side_effect=fake_score):
            payload = fs.build_speech_digest(
                sources=[], ledger=ledger, body_fetcher=boom
            )
        assert len(payload.new_posts) == 1
    finally:
        ledger.close()


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------


def test_post_skips_when_no_new_posts():
    payload = fs.SpeechDigestPayload(
        text="", blocks=[], new_posts=[], errors=[], verdicts={}
    )
    ok, msg = fs.post_speeches_to_macro(payload)
    assert ok is True
    assert "skipped" in msg


def test_post_requires_slack_env(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_MACRO_CHANNEL_ID", raising=False)
    payload = fs.SpeechDigestPayload(
        text="t", blocks=[{"type": "divider"}], new_posts=[_post(1)],
        errors=[], verdicts={},
    )
    ok, msg = fs.post_speeches_to_macro(payload)
    assert ok is False
    assert "SLACK_BOT_TOKEN" in msg
