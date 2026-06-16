"""Tests for the Fed-speech summarizer + hawkish/dovish/neutral classifier."""

from __future__ import annotations

from unittest.mock import MagicMock

from macro_monitor.collectors.rss import ResearchPost
from macro_monitor.scoring.speech_scorer import (
    STANCES,
    SpeechVerdict,
    _build_speech_prompt,
    _fallback_verdict,
    _parse_speech_verdict,
    score_speech,
    score_speeches,
)


def _post(idx: int = 1, title: str = "Powell, Economic Outlook") -> ResearchPost:
    return ResearchPost(
        source_id="fed_board_speeches",
        source_display="Federal Reserve — Speeches",
        title=title,
        url=f"https://www.federalreserve.gov/speech/{idx}.htm",
        summary=f"Speech at venue {idx}",
        published_at_iso="2026-06-06T16:00:00+00:00",
    )


def _mock_client(text: str) -> MagicMock:
    client = MagicMock()
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    client.messages.create.return_value = resp
    return client


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def test_build_prompt_includes_title_and_body():
    p = _post(title="Bowman, Monetary Policy")
    prompt = _build_speech_prompt(p, body="The committee should remain patient on cuts.")
    assert "Bowman, Monetary Policy" in prompt
    assert "remain patient on cuts" in prompt
    assert "hawkish" in prompt and "dovish" in prompt and "neutral" in prompt


def test_build_prompt_prefers_body_over_summary():
    p = _post()  # summary = "Speech at venue 1"
    prompt = _build_speech_prompt(p, body="Inflation remains too high.")
    assert "Inflation remains too high." in prompt
    assert "Speech text:" in prompt  # body-present header


def test_build_prompt_falls_back_to_summary_when_no_body():
    p = ResearchPost(
        source_id="x", source_display="X", title="t", url="u",
        summary="A blurb about rates", published_at_iso="",
    )
    prompt = _build_speech_prompt(p, body="")
    assert "A blurb about rates" in prompt
    assert "full text unavailable" in prompt


def test_build_prompt_truncates_long_body():
    long_body = "inflation " * 2000  # ~20k chars
    p = _post()
    prompt = _build_speech_prompt(p, body=long_body)
    assert long_body not in prompt  # capped at MAX_BODY_CHARS


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_valid_json():
    raw = (
        '{"summary": "Disinflation stalled; no hurry to cut.", '
        '"stance": "hawkish", "drivers": ["sticky inflation", "firm labor"]}'
    )
    v = _parse_speech_verdict(raw, _post())
    assert v.stance == "hawkish"
    assert "Disinflation stalled" in v.summary
    assert v.drivers == ("sticky inflation", "firm labor")


def test_parse_extracts_worried_sanguine_speaker_venue():
    raw = (
        '{"speaker": "Christopher Waller", "venue": "Economic Club of NY", '
        '"summary": "Cautious on cuts.", "worried_about": ["sticky inflation", '
        '"tariff pass-through"], "sanguine_about": ["expectations anchored"], '
        '"stance": "hawkish", "drivers": ["no hurry"]}'
    )
    v = _parse_speech_verdict(raw, _post())
    assert v.speaker == "Christopher Waller"
    assert v.venue == "Economic Club of NY"
    assert v.worried_about == ("sticky inflation", "tariff pass-through")
    assert v.sanguine_about == ("expectations anchored",)


def test_parse_caps_worried_at_four():
    raw = ('{"summary": "x", "stance": "neutral", '
           '"worried_about": ["a","b","c","d","e","f"]}')
    v = _parse_speech_verdict(raw, _post())
    assert len(v.worried_about) == 4


def test_parse_strips_code_fences():
    raw = '```json\n{"summary": "Cuts coming.", "stance": "dovish", "drivers": []}\n```'
    v = _parse_speech_verdict(raw, _post())
    assert v.stance == "dovish"
    assert v.summary == "Cuts coming."


def test_parse_handles_prose_wrapped_json():
    raw = 'Here is my read:\n{"summary": "Balanced.", "stance": "neutral"}\nThanks!'
    v = _parse_speech_verdict(raw, _post())
    assert v.stance == "neutral"
    assert v.summary == "Balanced."


def test_parse_unknown_stance_defaults_neutral():
    raw = '{"summary": "x", "stance": "super-hawkish", "drivers": []}'
    v = _parse_speech_verdict(raw, _post())
    assert v.stance == "neutral"


def test_parse_caps_drivers_at_three():
    raw = '{"summary": "x", "stance": "hawkish", "drivers": ["a","b","c","d","e"]}'
    v = _parse_speech_verdict(raw, _post())
    assert len(v.drivers) == 3


def test_parse_non_object_raises():
    import pytest

    with pytest.raises(Exception):
        _parse_speech_verdict("[1, 2, 3]", _post())


# ---------------------------------------------------------------------------
# Scoring + fallback
# ---------------------------------------------------------------------------


def test_score_speech_happy_path():
    client = _mock_client(
        '{"summary": "Hawkish read.", "stance": "hawkish", "drivers": ["x"]}'
    )
    v = score_speech(_post(), body="some text", client=client)
    assert v.stance == "hawkish"
    assert v.summary == "Hawkish read."


def test_score_speech_falls_back_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    v = score_speech(_post(), client=client)
    assert v.stance == "neutral"
    assert v.summary == ""
    assert "fallback" in v.why


def test_score_speech_falls_back_on_bad_json():
    client = _mock_client("not json at all")
    v = score_speech(_post(), client=client)
    assert v.stance == "neutral"
    assert "fallback" in v.why


def test_score_speeches_one_verdict_per_post():
    client = _mock_client('{"summary": "s", "stance": "dovish", "drivers": []}')
    posts = [_post(1), _post(2)]
    verdicts = score_speeches(posts, client=client)
    assert set(verdicts) == {posts[0].url, posts[1].url}
    assert all(v.stance == "dovish" for v in verdicts.values())


def test_score_speeches_empty_returns_empty():
    assert score_speeches([], client=_mock_client("{}")) == {}


def test_fallback_verdict_is_neutral():
    v = _fallback_verdict(_post(), "no key")
    assert isinstance(v, SpeechVerdict)
    assert v.stance == "neutral"
    assert v.stance in STANCES
    assert v.summary == ""
