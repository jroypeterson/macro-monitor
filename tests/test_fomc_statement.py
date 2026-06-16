"""Tests for the FOMC statement parser + redline summarizer."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from macro_monitor import fomc_statement as fs


def _mock_client(text: str) -> MagicMock:
    c = MagicMock()
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    c.messages.create.return_value = resp
    return c


_GOOD_JSON = (
    '{"target_range": "3-1/2 to 3-3/4 percent", "action": "hold", '
    '"summary": "Held rates; inflation elevated.", '
    '"changes": ["inflation: somewhat elevated -> elevated", "added easing bias"], '
    '"stance": "hawkish", "dissents": "Miran dissented dovishly."}'
)


def test_statement_url():
    assert fs.statement_url(date(2026, 4, 29)).endswith("monetary20260429a.htm")


def test_extract_statement_isolates_core():
    html = ("<html><nav>menu</nav><body>boilerplate "
            "Recent indicators suggest economic activity expanded. The Committee "
            "decided to maintain the target range for the federal funds rate. "
            "Implementation Note site footer junk</body></html>")
    core = fs.extract_statement(html)
    assert core.startswith("Recent indicators")
    assert "Implementation Note" not in core
    assert "footer junk" not in core


def test_extract_statement_empty():
    assert fs.extract_statement("") == ""


def test_parse_valid():
    v = fs._parse(_GOOD_JSON, "2026-04-29", sep=True)
    assert v.action == "hold" and v.stance == "hawkish"
    assert v.target_range.startswith("3-1/2")
    assert len(v.changes) == 2 and v.sep is True
    assert "Miran" in v.dissents


def test_parse_unknown_action_stance_default():
    v = fs._parse('{"action": "pivot", "stance": "spicy", "summary": "x"}', "2026-04-29", False)
    assert v.action == "hold" and v.stance == "neutral"


def test_parse_strips_fences():
    v = fs._parse("```json\n" + _GOOD_JSON + "\n```", "2026-04-29", False)
    assert v.action == "hold"


def test_analyze_fallback_on_api_error():
    c = MagicMock()
    c.messages.create.side_effect = RuntimeError("boom")
    v = fs.analyze_statement("some statement text", "prior", date(2026, 4, 29), client=c)
    assert v.action == "hold" and v.stance == "neutral"
    assert "fallback" not in v.why and "boom" in v.why  # carries the reason


def test_analyze_empty_statement_no_call():
    c = _mock_client(_GOOD_JSON)
    v = fs.analyze_statement("", "prior", date(2026, 4, 29), client=c)
    assert "unavailable" in v.why
    c.messages.create.assert_not_called()


def test_latest_meeting_on_or_before():
    # 2026-05-01 is after the Apr 28-29 meeting, before the Jun one.
    m = fs.latest_meeting_on_or_before(date(2026, 5, 1))
    assert m.end == date(2026, 4, 29)
    assert fs.latest_meeting_on_or_before(date(2026, 1, 1)) is None  # before first 2026 mtg


def test_build_statement_report_end_to_end():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return ("<body>Recent indicators show solid growth. The Committee decided "
                "to maintain the target range for the federal funds rate. "
                "Implementation Note</body>")

    client = _mock_client(_GOOD_JSON)
    verdict, text, blocks = fs.build_statement_report(
        on_date=date(2026, 4, 29), fetch=fake_fetch, client=client)
    assert verdict.decision_date == "2026-04-29"
    assert verdict.action == "hold"
    # fetched the Apr 29 statement AND the Mar 18 prior for the redline
    assert any("20260429" in u for u in calls) and any("20260318" in u for u in calls)
    assert blocks[0]["type"] == "header"
    assert "HOLD" in text and "Key changes" in text


def test_build_statement_report_none_before_first_meeting():
    verdict, text, _ = fs.build_statement_report(
        on_date=date(2025, 1, 1), fetch=lambda u: "", client=_mock_client(_GOOD_JSON))
    assert verdict is None and "no fomc statement" in text.lower()


def test_render_blocks_has_action_and_changes():
    v = fs._parse(_GOOD_JSON, "2026-04-29", sep=False)
    blocks = fs._render_blocks(v)
    body = "".join(b["text"]["text"] for b in blocks if b.get("type") == "section")
    assert "HOLD" in body and "easing bias" in body
