"""FOMC statement parser + redline summarizer.

On decision day the Committee publishes its statement at a predictable URL
(`/newsevents/pressreleases/monetary{YYYYMMDD}a.htm`). This module fetches the
new statement AND the prior meeting's statement, then asks an LLM for the part
markets actually trade on: the rate decision, a plain-English summary, the
notable LANGUAGE CHANGES vs the prior statement (the redline), the action
(hold/cut/hike), the policy lean, and any dissents.

Pairs with `fomc.py` (the meeting calendar) — that supplies the decision dates
and the prior-meeting lookup, so this never guesses when a meeting happened.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import fomc

# Sonnet for the redline — 8x/year, low volume, and the language-diff is subtle
# enough to want a stronger model than the speech lane's Haiku.
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1500
MAX_STMT_CHARS = 6000

ACTIONS = ("cut", "hold", "hike")
STANCES = ("hawkish", "dovish", "neutral")


@dataclass(frozen=True)
class StatementVerdict:
    decision_date: str
    target_range: str = ""          # e.g. "3-1/2 to 3-3/4 percent"
    action: str = "hold"            # cut / hold / hike
    stance: str = "neutral"         # hawkish / dovish / neutral
    summary: str = ""               # 3-4 sentence plain-English read
    changes: tuple[str, ...] = field(default_factory=tuple)   # the redline vs prior
    dissents: str = ""              # dissent description, or ""
    sep: bool = False               # was this a Summary-of-Economic-Projections mtg
    why: str = ""                   # fallback reason


def statement_url(decision_date: date) -> str:
    return (
        "https://www.federalreserve.gov/newsevents/pressreleases/"
        f"monetary{decision_date.strftime('%Y%m%d')}a.htm"
    )


def _fetch(url: str, timeout: int = 20) -> str:
    try:
        import requests

        r = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "macro-monitor/fomc (+research)"},
        )
        r.raise_for_status()
        return r.text
    except Exception:  # noqa: BLE001
        return ""


def extract_statement(html: str) -> str:
    """Strip a statement page to plain text and isolate the statement core
    (drop site nav/footer). Best-effort — returns "" if the page is empty."""
    if not html:
        return ""
    html = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # The statement proper runs from its economic-assessment opener to the
    # "Implementation Note" that follows it. Slice that window when present.
    low = text.lower()
    starts = [low.find(m) for m in (
        "recent indicators", "information received", "economic activity")]
    starts = [s for s in starts if s >= 0]
    start = min(starts) if starts else 0
    end = low.find("implementation note", start)
    core = text[start: end if end > start else start + MAX_STMT_CHARS]
    return core.strip()[:MAX_STMT_CHARS]


def fetch_statement(decision_date: date, fetch=None) -> str:
    """Fetch + extract the statement text for a decision date. `fetch(url)->html`
    injectable for tests."""
    fetch = fetch or _fetch
    return extract_statement(fetch(statement_url(decision_date)))


def analyze_statement(
    current_text: str,
    prior_text: str,
    decision_date: date,
    sep: bool = False,
    client: Any = None,
    model: str | None = None,
) -> StatementVerdict:
    """LLM read of the statement + redline vs the prior. Never raises — returns
    a minimal fallback verdict on any API/parse error."""
    iso = decision_date.isoformat()
    if not current_text:
        return StatementVerdict(decision_date=iso, sep=sep, why="statement text unavailable")

    if client is None:
        try:
            import anthropic
        except ImportError:
            return StatementVerdict(decision_date=iso, sep=sep, why="anthropic SDK not installed")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return StatementVerdict(decision_date=iso, sep=sep, why="ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic()

    prompt = _build_prompt(current_text, prior_text)
    try:
        resp = client.messages.create(
            model=model or MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
    except Exception as e:  # noqa: BLE001
        return StatementVerdict(decision_date=iso, sep=sep, why=f"{type(e).__name__}: {e}")

    try:
        return _parse(raw, iso, sep)
    except Exception as e:  # noqa: BLE001
        return StatementVerdict(decision_date=iso, sep=sep, why=f"parse error: {e}")


def _build_prompt(current_text: str, prior_text: str) -> str:
    lines = [
        "You are briefing a macro portfolio manager on a new FOMC statement.",
        "",
        "NEW statement:",
        current_text,
        "",
        ("PRIOR statement (the previous meeting), for comparison:" if prior_text
         else "(No prior statement available — analyze the new one on its own.)"),
        prior_text or "",
        "",
        "Extract:",
        "1. target_range: the federal funds target range the Committee set "
        "(e.g. '3-1/2 to 3-3/4 percent').",
        "2. action: did they 'cut', 'hold', or 'hike' the rate vs the prior level?",
        "3. summary: 3-4 sentences in plain English on the decision + the economic "
        "assessment + any forward guidance.",
        "4. changes: a list (up to 5) of the NOTABLE LANGUAGE CHANGES vs the prior "
        "statement — the redline markets watch (e.g. characterization of growth/"
        "inflation/labor shifting, adding/removing a bias, new risk language). Each "
        "a short phrase like 'growth: \"moderated\" -> \"solid\"'. [] if first/none.",
        "5. stance: the lean of the CHANGES — 'hawkish', 'dovish', or 'neutral'.",
        "6. dissents: who dissented and which direction, or '' if the vote was unanimous.",
        "",
        "Respond with JSON only — no preamble, no fences — keys: target_range "
        "(string), action ('cut'/'hold'/'hike'), summary (string), changes (array "
        "of strings), stance ('hawkish'/'dovish'/'neutral'), dissents (string).",
    ]
    return "\n".join(lines)


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse(raw: str, iso: str, sep: bool) -> StatementVerdict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    if not text.startswith("{"):
        m = _JSON_OBJ_RE.search(text)
        if m:
            text = m.group(0)
    p = json.loads(text)
    if not isinstance(p, dict):
        raise ValueError("expected JSON object")

    action = str(p.get("action", "")).strip().lower()
    if action not in ACTIONS:
        action = "hold"
    stance = str(p.get("stance", "")).strip().lower()
    if stance not in STANCES:
        stance = "neutral"
    changes_raw = p.get("changes") or []
    changes = tuple(
        str(c).strip()[:160] for c in changes_raw[:5] if str(c).strip()
    ) if isinstance(changes_raw, list) else ()
    return StatementVerdict(
        decision_date=iso,
        target_range=str(p.get("target_range", "") or "").strip()[:80],
        action=action,
        stance=stance,
        summary=str(p.get("summary", "") or "").strip()[:800],
        changes=changes,
        dissents=str(p.get("dissents", "") or "").strip()[:300],
        sep=sep,
    )


# ---------------------------------------------------------------------------
# Orchestration + rendering
# ---------------------------------------------------------------------------


def latest_meeting_on_or_before(today: date) -> "fomc.FOMCMeeting | None":
    """The FOMC meeting whose decision day is on/before `today` (i.e. the most
    recent statement)."""
    past = [m for m in fomc.all_meetings() if m.end <= today]
    return past[-1] if past else None


def build_statement_report(
    on_date: date | None = None,
    fetch=None,
    client=None,
    model: str | None = None,
) -> tuple["StatementVerdict | None", str, list[dict]]:
    """Resolve the relevant meeting, fetch its statement + the prior one,
    analyze, and render. Returns (verdict|None, text, blocks). verdict is None
    when no meeting has occurred (nothing to report)."""
    today = on_date or date.today()
    meeting = latest_meeting_on_or_before(today)
    if meeting is None:
        return None, "macro-monitor: no FOMC statement to report.", []

    current = fetch_statement(meeting.end, fetch=fetch)
    prior_meeting = fomc.all_meetings()
    prior_txt = ""
    prev = [m for m in prior_meeting if m.end < meeting.end]
    if prev:
        prior_txt = fetch_statement(prev[-1].end, fetch=fetch)

    verdict = analyze_statement(
        current, prior_txt, meeting.end, sep=meeting.projections,
        client=client, model=model,
    )
    return verdict, _render_text(verdict), _render_blocks(verdict)


_ACTION_BADGE = {"cut": "✂️ CUT", "hold": "⏸️ HOLD", "hike": "⬆️ HIKE"}
_STANCE_BADGE = {"hawkish": "🦅 hawkish", "dovish": "🕊️ dovish", "neutral": "➖ neutral"}


def _md_escape(t: str) -> str:
    return t.replace("<", "&lt;").replace(">", "&gt;").replace("|", "│")


def _render_text(v: StatementVerdict) -> str:
    lines = [f"🏛️ FOMC STATEMENT — {v.decision_date}"
             + (" (with SEP / dot plot)" if v.sep else "")]
    lines.append(f"{_ACTION_BADGE.get(v.action, v.action.upper())} · "
                 f"target {v.target_range or '—'} · {_STANCE_BADGE.get(v.stance, v.stance)}")
    if v.summary:
        lines.append("\n" + v.summary)
    if v.changes:
        lines.append("\nKey changes vs prior statement:")
        for c in v.changes:
            lines.append(f"  • {c}")
    if v.dissents:
        lines.append(f"\nDissents: {v.dissents}")
    if v.why:
        lines.append(f"\n⚠️ {v.why}")
    return "\n".join(lines)


def _render_blocks(v: StatementVerdict) -> list[dict]:
    title = f"🏛️ FOMC Statement — {v.decision_date}" + (" + SEP" if v.sep else "")
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150], "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text":
            f"*{_ACTION_BADGE.get(v.action, v.action.upper())}*  ·  target "
            f"*{_md_escape(v.target_range or '—')}*  ·  {_STANCE_BADGE.get(v.stance, v.stance)}"}},
    ]
    if v.summary:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _md_escape(v.summary)}})
    if v.changes:
        body = "*Key changes vs prior statement:*\n" + "\n".join(
            f"• {_md_escape(c)}" for c in v.changes)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body}})
    if v.dissents:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"Dissents: {_md_escape(v.dissents)}"}]})
    if v.why:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"⚠️ {_md_escape(v.why)}"}]})
    return blocks


def post_to_macro(text: str, blocks: list[dict]) -> tuple[bool, str]:
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    channel_id = os.environ.get("SLACK_MACRO_CHANNEL_ID")
    if not bot_token or not channel_id:
        return False, "SLACK_BOT_TOKEN + SLACK_MACRO_CHANNEL_ID required"
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    try:
        resp = WebClient(token=bot_token).chat_postMessage(
            channel=channel_id, text=text, blocks=blocks)
        return True, f"posted ts={resp['ts']}"
    except SlackApiError as e:
        return False, f"slack error: {e.response.get('error')}"
