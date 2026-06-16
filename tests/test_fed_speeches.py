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
        url=url, stance=stance, summary="A summary.", speaker="Jane Powell",
        venue="Econ Club", worried_about=("sticky inflation",),
        sanguine_about=("anchored expectations",), drivers=("a", "b"), why="",
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
    assert "Worried" in body and "sticky inflation" in body
    assert "Sanguine" in body and "anchored expectations" in body


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
                sources=[], ledger=ledger, body_fetcher=fake_body_fetcher,
                prior_lookup=lambda s, d: None,
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
                sources=[], ledger=ledger, body_fetcher=boom,
                prior_lookup=lambda s, d: None,
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


def test_post_requires_slack_env_placeholder():
    pass


# ---------------------------------------------------------------------------
# Archive + single-URL ingest
# ---------------------------------------------------------------------------


def test_speaker_and_venue_fallbacks():
    # LLM gave neither -> fall back to RSS title surname + venue blurb.
    p = ResearchPost("fed", "Fed", "Waller, Policy Risks Have Changed",
                     "https://x/1", "Speech At the Economic Club of New York",
                     "2026-05-22T16:00:00+00:00")
    v = SpeechVerdict(url="https://x/1", stance="hawkish", summary="s")
    rec = fs.record_from(p, v, body="full body text")
    assert rec.speaker == "Waller"
    assert "Economic Club of New York" in rec.venue
    assert rec.full_text == "full body text"
    assert rec.speech_date == "2026-05-22"


def test_record_from_prefers_llm_fields():
    p = ResearchPost("fed", "Fed", "Waller, X", "https://x/1", "Speech At Y", "")
    v = SpeechVerdict(url="https://x/1", stance="dovish", summary="s",
                      speaker="Christopher Waller", venue="Jackson Hole",
                      worried_about=("inflation",), sanguine_about=("jobs",))
    rec = fs.record_from(p, v, "")
    assert rec.speaker == "Christopher Waller" and rec.venue == "Jackson Hole"
    assert rec.worried_about == ("inflation",) and rec.sanguine_about == ("jobs",)


def test_archive_payload_persists_to_store(tmp_path):
    from macro_monitor.schedulers.speech_store import SpeechStore

    posts = [_post(1)]
    payload = fs.SpeechDigestPayload(
        text="", blocks=[], new_posts=posts, errors=[],
        verdicts={posts[0].url: _verdict(posts[0].url)},
        bodies={posts[0].url: "the transcript"},
    )
    with SpeechStore(tmp_path / "fs.db") as store:
        n = fs.archive_payload(payload, store=store)
        assert n == 1
        rows = store.all_records()
        assert rows[0]["full_text"] == "the transcript"
        assert rows[0]["worried_about"] == ["sticky inflation"]
        # Idempotent re-archive (upsert) keeps count at 1.
        fs.archive_payload(payload, store=store)
        assert store.count() == 1


def test_archive_payload_noop_without_verdicts(tmp_path):
    from macro_monitor.schedulers.speech_store import SpeechStore

    payload = fs.SpeechDigestPayload(
        text="", blocks=[], new_posts=[_post(1)], errors=[], verdicts={}, bodies={}
    )
    with SpeechStore(tmp_path / "fs.db") as store:
        assert fs.archive_payload(payload, store=store) == 0


def test_ingest_url_scores_and_titles_from_llm():
    from unittest.mock import MagicMock

    client = MagicMock()
    resp = MagicMock()
    resp.content = [MagicMock(text=(
        '{"speaker": "Neel Kashkari", "venue": "Town Hall", "summary": "Cautious.", '
        '"worried_about": ["tariffs"], "sanguine_about": [], "stance": "hawkish", '
        '"drivers": []}'
    ))]
    client.messages.create.return_value = resp

    post, verdict, body = fs.ingest_url(
        "https://minneapolisfed.org/speech/2026/x",
        body_fetcher=lambda u: "speech body", client=client,
    )
    assert verdict.speaker == "Neel Kashkari"
    assert verdict.worried_about == ("tariffs",)
    assert body == "speech body"
    # Title was a URL slug -> upgraded from LLM-identified speaker/venue.
    assert "Neel Kashkari" in post.title


def test_stance_shift_line():
    assert fs._stance_shift_line("hawkish", None) is None
    up = fs._stance_shift_line("hawkish", {"stance": "neutral", "speech_date": "2026-05-01"})
    assert "more hawkish" in up and "2026-05-01" in up
    dn = fs._stance_shift_line("dovish", {"stance": "hawkish", "speech_date": "2026-05-01"})
    assert "more dovish" in dn
    same = fs._stance_shift_line("neutral", {"stance": "neutral", "speech_date": "2026-05-01"})
    assert "unchanged" in same


def test_render_blocks_shows_audience_and_shift():
    posts = [_post(1)]
    v = SpeechVerdict(url=posts[0].url, stance="hawkish", summary="s",
                      audience="congressional testimony — Senate Banking")
    priors = {posts[0].url: {"stance": "neutral", "speech_date": "2026-05-01"}}
    blocks = fs._render_blocks(posts, [], {posts[0].url: v}, priors)
    body = "".join(b["text"]["text"] for b in blocks if b.get("type") == "section")
    assert "congressional testimony" in body
    assert "more hawkish" in body


def test_build_speaker_report_timeline_and_shift(tmp_path):
    from datetime import date
    from unittest.mock import MagicMock

    from macro_monitor.schedulers.speech_store import SpeechRecord, SpeechStore

    client = MagicMock()
    resp = MagicMock()
    resp.content = [MagicMock(text="Waller drifted from dovish to hawkish over the spring.")]
    client.messages.create.return_value = resp

    with SpeechStore(tmp_path / "s.db") as store:
        store.upsert(SpeechRecord(url="u1", speaker="Christopher Waller",
                                  speech_date="2026-01-10", stance="dovish",
                                  summary="early", worried_about=("a",)))
        store.upsert(SpeechRecord(url="u2", speaker="Christopher Waller",
                                  speech_date="2026-05-10", stance="hawkish",
                                  summary="later", worried_about=("b",)))
        rpt = fs.build_speaker_report("waller", months=12, store=store,
                                      client=client, today=date(2026, 6, 1))
    assert "Christopher Waller" in rpt and "2 speech" in rpt
    assert rpt.index("2026-05-10") < rpt.index("2026-01-10")  # newest first
    assert "more hawkish" in rpt          # deterministic shift on latest vs prior
    assert "drifted from dovish" in rpt   # LLM evolution synthesis included


def test_build_speaker_report_no_data(tmp_path):
    from macro_monitor.schedulers.speech_store import SpeechStore
    with SpeechStore(tmp_path / "s.db") as store:
        assert "No archived speeches" in fs.build_speaker_report("nobody", store=store)


def test_discover_annual_speeches_parses_and_dedups():
    html = (
        '<a href="/newsevents/speech/waller20260130a.htm">a</a>'
        '<a href="/newsevents/speech/cook20260204a.htm">b</a>'
        '<a href="/newsevents/speech/waller20260130a.htm">dup</a>'
    )
    out = fs.discover_annual_speeches(2026, index_fetcher=lambda u: html)
    assert len(out) == 2  # deduped
    # newest date first
    assert out[0] == (
        "https://www.federalreserve.gov/newsevents/speech/cook20260204a.htm",
        "Cook", "2026-02-04",
    )
    assert out[1][1] == "Waller" and out[1][2] == "2026-01-30"


def test_backfill_year_archives_new_only_and_is_idempotent(tmp_path):
    from unittest.mock import MagicMock

    from macro_monitor.schedulers.speech_store import SpeechStore

    html = (
        '<a href="/newsevents/speech/waller20260130a.htm">a</a>'
        '<a href="/newsevents/speech/cook20260204a.htm">b</a>'
    )
    client = MagicMock()
    resp = MagicMock()
    resp.content = [MagicMock(text='{"speaker": "", "venue": "Y", "summary": "s", '
                             '"worried_about": [], "sanguine_about": [], '
                             '"stance": "neutral", "drivers": []}')]
    client.messages.create.return_value = resp

    with SpeechStore(tmp_path / "s.db") as store:
        n = fs.backfill_year(
            2026, store=store, index_fetcher=lambda u: html,
            body_fetcher=lambda u: "body", client=client, log=lambda *a: None,
        )
        assert n == 2
        # speaker falls back to the URL surname when the LLM returns blank
        rows = {r["url"].rsplit("/", 1)[-1]: r for r in store.all_records()}
        assert rows["cook20260204a.htm"]["speaker"] == "Cook"
        assert rows["cook20260204a.htm"]["speech_date"] == "2026-02-04"
        # Re-run archives nothing (idempotent).
        n2 = fs.backfill_year(
            2026, store=store, index_fetcher=lambda u: html,
            body_fetcher=lambda u: "body", client=client, log=lambda *a: None,
        )
        assert n2 == 0


def test_backfill_year_respects_limit(tmp_path):
    from unittest.mock import MagicMock
    from macro_monitor.schedulers.speech_store import SpeechStore

    html = "".join(
        f'<a href="/newsevents/speech/waller202601{d:02d}a.htm">x</a>' for d in range(1, 6)
    )
    client = MagicMock()
    resp = MagicMock()
    resp.content = [MagicMock(text='{"stance": "neutral", "summary": "s"}')]
    client.messages.create.return_value = resp
    with SpeechStore(tmp_path / "s.db") as store:
        n = fs.backfill_year(2026, store=store, index_fetcher=lambda u: html,
                             body_fetcher=lambda u: "b", client=client,
                             limit=2, log=lambda *a: None)
        assert n == 2 and store.count() == 2


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
