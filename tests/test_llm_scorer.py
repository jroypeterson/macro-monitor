"""Tests for the LLM-backed read-worthiness scorer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from macro_monitor.collectors.rss import ResearchPost
from macro_monitor.scoring.llm_scorer import (
    ScoreVerdict,
    _build_prompt,
    _fallback_verdicts,
    _parse_verdicts,
    score_posts,
)


def _post(idx: int, title: str = "Sample", source: str = "NBER") -> ResearchPost:
    return ResearchPost(
        source_id="nber",
        source_display=source,
        title=title,
        url=f"https://x/{idx}",
        summary=f"summary {idx}",
        published_at_iso="",
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def test_build_prompt_numbers_items_1_indexed():
    posts = [_post(1, "Fed cuts rates"), _post(2, "GDP slowed")]
    prompt = _build_prompt(posts)
    assert "[1] Source:" in prompt
    assert "[2] Source:" in prompt
    assert "Fed cuts rates" in prompt
    assert "GDP slowed" in prompt


def test_build_prompt_truncates_long_summaries():
    long_summary = "lorem ipsum " * 100
    p = ResearchPost(
        source_id="x", source_display="X", title="t", url="u",
        summary=long_summary, published_at_iso="",
    )
    prompt = _build_prompt([p])
    # Should truncate before 1000 chars worth of summary
    assert long_summary not in prompt


def test_build_prompt_handles_missing_summary():
    p = ResearchPost(
        source_id="x", source_display="X", title="t", url="u",
        summary="", published_at_iso="",
    )
    prompt = _build_prompt([p])
    assert "[1] Source: X | Title: t" in prompt
    # No "Summary:" key when summary is empty
    assert "| Summary:" not in prompt.split("\n[1]")[1].split("\n")[0]


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def test_parse_verdicts_basic():
    posts = [_post(1, "Fed paper"), _post(2, "Sports news")]
    raw = (
        '[{"i": 1, "is_macro": true, "score": 8, "why": "Fed analysis"}, '
        '{"i": 2, "is_macro": false, "score": 0, "why": "Sports"}]'
    )
    out = _parse_verdicts(raw, posts)
    assert out["https://x/1"].is_macro is True
    assert out["https://x/1"].score == 8
    assert out["https://x/2"].is_macro is False
    assert out["https://x/2"].score == 0


def test_parse_verdicts_strips_markdown_fence():
    posts = [_post(1)]
    raw = '```json\n[{"i":1,"is_macro":true,"score":5,"why":"ok"}]\n```'
    out = _parse_verdicts(raw, posts)
    assert out["https://x/1"].score == 5


def test_parse_verdicts_extracts_json_from_prose():
    posts = [_post(1)]
    raw = (
        "Sure, here you go:\n"
        '[{"i":1,"is_macro":true,"score":7,"why":"good"}]\n'
        "Let me know if you need more."
    )
    out = _parse_verdicts(raw, posts)
    assert out["https://x/1"].score == 7


def test_parse_verdicts_clamps_score_to_0_10():
    posts = [_post(1), _post(2)]
    raw = '[{"i":1,"is_macro":true,"score":99},{"i":2,"is_macro":true,"score":-3}]'
    out = _parse_verdicts(raw, posts)
    assert out["https://x/1"].score == 10
    assert out["https://x/2"].score == 0


def test_parse_verdicts_fills_missing_index_with_default():
    """LLM dropped item 2 from its response — we should default to
    permissive (is_macro=True, score=5) rather than silently lose it."""
    posts = [_post(1), _post(2)]
    raw = '[{"i":1,"is_macro":true,"score":8,"why":"good"}]'
    out = _parse_verdicts(raw, posts)
    assert out["https://x/2"].is_macro is True  # default
    assert out["https://x/2"].score == 5


def test_parse_verdicts_handles_string_score():
    """LLM may return score as string '7' instead of int 7."""
    posts = [_post(1)]
    raw = '[{"i":1,"is_macro":true,"score":"7","why":"ok"}]'
    out = _parse_verdicts(raw, posts)
    assert out["https://x/1"].score == 7


# ---------------------------------------------------------------------------
# score_posts end-to-end (mocked client)
# ---------------------------------------------------------------------------


def test_score_posts_returns_empty_dict_for_empty_input():
    assert score_posts([]) == {}


def test_score_posts_mocks_client_and_parses():
    posts = [_post(1, "Fed paper"), _post(2, "Soccer match")]
    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(text=(
        '[{"i":1,"is_macro":true,"score":9,"why":"Major Fed analysis"},'
        '{"i":2,"is_macro":false,"score":0,"why":"Sports, not macro"}]'
    ))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    out = score_posts(posts, client=mock_client)

    assert out["https://x/1"].is_macro is True
    assert out["https://x/1"].score == 9
    assert out["https://x/2"].is_macro is False
    mock_client.messages.create.assert_called_once()


def test_score_posts_falls_back_on_api_error():
    """An API error should never empty the digest — return permissive
    verdicts so all items pass through with default score=5."""
    posts = [_post(1), _post(2)]
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("boom")

    out = score_posts(posts, client=mock_client)

    assert len(out) == 2
    for v in out.values():
        assert v.is_macro is True
        assert v.score == 5
        assert "fallback" in v.why


def test_score_posts_falls_back_on_parse_error():
    posts = [_post(1)]
    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(text="this is not JSON at all")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    out = score_posts(posts, client=mock_client)

    assert out["https://x/1"].is_macro is True
    assert out["https://x/1"].score == 5
    assert "fallback" in out["https://x/1"].why


# ---------------------------------------------------------------------------
# Digest integration: drop non-macro + sort by score
# ---------------------------------------------------------------------------


def test_build_digest_drops_non_macro_items(tmp_path):
    """End-to-end: non-macro verdict should land in dropped_non_macro,
    not new_posts."""
    from macro_monitor.collectors.rss import ResearchLedger, ResearchSource
    from macro_monitor.schedulers.research_digest import build_digest

    ledger = ResearchLedger(tmp_path / "ledger.db")

    macro_post = _post(1, "CPI rises 0.3% MoM")
    non_macro_post = _post(2, "Local school board election")

    fake_verdicts = {
        macro_post.url: ScoreVerdict(macro_post.url, True, 8, "CPI"),
        non_macro_post.url: ScoreVerdict(non_macro_post.url, False, 0, "politics"),
    }

    src = ResearchSource(id="x", display_name="X", url="x", max_items_per_run=10)

    with patch(
        "macro_monitor.schedulers.research_digest.fetch_all",
        return_value=([macro_post, non_macro_post], []),
    ), patch(
        "macro_monitor.schedulers.research_digest.score_posts",
        return_value=fake_verdicts,
    ):
        payload = build_digest(sources=[src], ledger=ledger, skip_gmail=True)

    assert [p.url for p in payload.new_posts] == [macro_post.url]
    assert [p.url for p in payload.dropped_non_macro] == [non_macro_post.url]
    ledger.close()


def test_render_sorts_within_source_by_score(tmp_path):
    """Within a source, items should be sorted by score desc."""
    from macro_monitor.collectors.rss import ResearchLedger, ResearchSource
    from macro_monitor.schedulers.research_digest import build_digest

    ledger = ResearchLedger(tmp_path / "ledger.db")

    low = _post(1, "Low-signal item")
    high = _post(2, "High-signal item")

    fake_verdicts = {
        low.url: ScoreVerdict(low.url, True, 3, "noise"),
        high.url: ScoreVerdict(high.url, True, 9, "great"),
    }

    src = ResearchSource(id="x", display_name="X", url="x", max_items_per_run=10)

    with patch(
        "macro_monitor.schedulers.research_digest.fetch_all",
        return_value=([low, high], []),  # low comes first
    ), patch(
        "macro_monitor.schedulers.research_digest.score_posts",
        return_value=fake_verdicts,
    ):
        payload = build_digest(sources=[src], ledger=ledger, skip_gmail=True)

    # high-score item should appear before low-score in rendered text
    high_idx = payload.text.index("High-signal item")
    low_idx = payload.text.index("Low-signal item")
    assert high_idx < low_idx
    ledger.close()


def test_render_includes_score_badge():
    """Both text + blocks should carry the score badge when verdicts exist."""
    from macro_monitor.schedulers.research_digest import _render_blocks, _render_text

    posts = [_post(1, "Fed pauses")]
    verdicts = {posts[0].url: ScoreVerdict(posts[0].url, True, 8, "important")}

    text = _render_text(posts, [], verdicts)
    assert "8/10" in text

    blocks = _render_blocks(posts, [], verdicts)
    section_text = blocks[1]["text"]["text"]
    assert "8/10" in section_text


def test_render_no_badge_when_verdicts_missing():
    """Render should still work when verdicts dict is None (e.g. scoring
    was skipped or the LLM call errored before producing any output)."""
    from macro_monitor.schedulers.research_digest import _render_blocks, _render_text

    posts = [_post(1, "Some title")]
    text = _render_text(posts, [], None)
    assert "Some title" in text
    assert "10" not in text  # no score badge

    blocks = _render_blocks(posts, [], None)
    section_text = blocks[1]["text"]["text"]
    assert "Some title" in section_text


# ---------------------------------------------------------------------------
# Fallback helper
# ---------------------------------------------------------------------------


def test_fallback_verdicts_permissive():
    posts = [_post(1), _post(2)]
    out = _fallback_verdicts(posts, "test reason")
    assert len(out) == 2
    for v in out.values():
        assert v.is_macro is True
        assert v.score == 5
        assert "test reason" in v.why


# ---------------------------------------------------------------------------
# Top picks (curated header section)
# ---------------------------------------------------------------------------


def test_top_picks_returns_high_scorers_first():
    from macro_monitor.schedulers.research_digest import _top_picks

    posts = [_post(1, "low"), _post(2, "high"), _post(3, "mid")]
    verdicts = {
        posts[0].url: ScoreVerdict(posts[0].url, True, 4, ""),
        posts[1].url: ScoreVerdict(posts[1].url, True, 9, ""),
        posts[2].url: ScoreVerdict(posts[2].url, True, 7, ""),
    }
    picks = _top_picks(posts, verdicts)
    assert [p.title for p in picks] == ["high", "mid"]


def test_top_picks_threshold_drops_below_7():
    """Items below the score threshold should NOT appear when at least
    one item passes the threshold."""
    from macro_monitor.schedulers.research_digest import _top_picks

    posts = [_post(1), _post(2), _post(3)]
    verdicts = {
        posts[0].url: ScoreVerdict(posts[0].url, True, 6, ""),
        posts[1].url: ScoreVerdict(posts[1].url, True, 7, ""),
        posts[2].url: ScoreVerdict(posts[2].url, True, 8, ""),
    }
    picks = _top_picks(posts, verdicts)
    # Only 8 and 7 should appear; 6 is below threshold and >= 1 item passed
    assert len(picks) == 2
    scores = [verdicts[p.url].score for p in picks]
    assert scores == [8, 7]


def test_top_picks_fallback_floor_when_nothing_hits_threshold():
    """If ZERO items hit the >=7 threshold, fall back to top-3 by score
    so the section isn't blank."""
    from macro_monitor.schedulers.research_digest import _top_picks

    posts = [_post(1), _post(2), _post(3), _post(4)]
    verdicts = {
        posts[0].url: ScoreVerdict(posts[0].url, True, 6, ""),
        posts[1].url: ScoreVerdict(posts[1].url, True, 5, ""),
        posts[2].url: ScoreVerdict(posts[2].url, True, 4, ""),
        posts[3].url: ScoreVerdict(posts[3].url, True, 3, ""),
    }
    picks = _top_picks(posts, verdicts)
    assert len(picks) == 3
    scores = [verdicts[p.url].score for p in picks]
    assert scores == [6, 5, 4]


def test_top_picks_caps_at_max():
    """Even on a heavy day with many high-scorers, cap at TOP_PICKS_CAP."""
    from macro_monitor.schedulers.research_digest import (
        TOP_PICKS_CAP,
        _top_picks,
    )

    posts = [_post(i) for i in range(15)]
    verdicts = {
        p.url: ScoreVerdict(p.url, True, 8, "")
        for p in posts
    }
    picks = _top_picks(posts, verdicts)
    assert len(picks) == TOP_PICKS_CAP


def test_top_picks_empty_when_no_verdicts():
    from macro_monitor.schedulers.research_digest import _top_picks

    posts = [_post(1)]
    assert _top_picks(posts, {}) == []


def test_render_text_includes_top_picks_section():
    from macro_monitor.schedulers.research_digest import _render_text

    posts = [_post(1, "Mid item"), _post(2, "Hot item")]
    verdicts = {
        posts[0].url: ScoreVerdict(posts[0].url, True, 6, ""),
        posts[1].url: ScoreVerdict(posts[1].url, True, 9, ""),
    }
    text = _render_text(posts, [], verdicts)
    assert "TOP PICKS" in text
    assert "FULL DIGEST" in text
    # Hot item should appear in top picks BEFORE the full digest section
    top_idx = text.index("TOP PICKS")
    full_idx = text.index("FULL DIGEST")
    hot_first_idx = text.index("Hot item")
    assert top_idx < hot_first_idx < full_idx


def test_render_blocks_includes_top_picks_section():
    from macro_monitor.schedulers.research_digest import _render_blocks

    posts = [_post(1, "Hot item")]
    verdicts = {posts[0].url: ScoreVerdict(posts[0].url, True, 9, "great")}
    blocks = _render_blocks(posts, [], verdicts)
    # header + top-picks section + divider + source section
    section_texts = [
        b["text"]["text"]
        for b in blocks
        if b.get("type") == "section"
    ]
    assert any("TOP PICKS" in t for t in section_texts)
    assert any(b.get("type") == "divider" for b in blocks)
