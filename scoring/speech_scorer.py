"""Haiku-backed Fed-speech summarizer + hawkish/dovish/neutral classifier.

Sibling of llm_scorer.py, for the Fed-speeches lane. For each speech we ask
Claude for:
  1. A 2-3 sentence plain-English summary of the substance.
  2. A monetary-policy stance read: hawkish / dovish / neutral.
  3. A short list of the drivers behind the stance call.

One API call per speech (speeches are long and low-volume — a handful a week —
so per-item is fine and keeps each prompt focused on the full speech body).
Haiku 4.5 pricing makes this effectively free at this volume.

Defensive fallback: any API/parse error returns a neutral verdict with an empty
summary so the lane still posts the speech (tagged neutral) rather than
silently dropping it — per the no-silent-failures rule.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from ..collectors.rss import ResearchPost

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
# Cap the speech body we send. Fed speeches run 1.5k-4k words; the first
# ~6k chars reliably carry the policy signal (framing + outlook) and keep
# the prompt cheap. Body is used when available, else the RSS summary.
MAX_BODY_CHARS = 6000

STANCES = ("hawkish", "dovish", "neutral")


@dataclass(frozen=True)
class SpeechVerdict:
    """LLM verdict for a single Fed speech, keyed back via `url`."""

    url: str
    stance: str            # one of STANCES
    summary: str           # 2-3 sentence plain-English summary ("" on fallback)
    speaker: str = ""      # Fed official's name (LLM-identified; "" if unclear)
    venue: str = ""        # where/what occasion (LLM-identified; "" if unclear)
    worried_about: tuple[str, ...] = field(default_factory=tuple)   # concerns flagged
    sanguine_about: tuple[str, ...] = field(default_factory=tuple)  # comforts/reassurances
    drivers: tuple[str, ...] = field(default_factory=tuple)  # short stance drivers
    why: str = ""          # one-line rationale / fallback reason


def score_speeches(
    posts: list[ResearchPost],
    bodies: dict[str, str] | None = None,
    client: Any = None,
) -> dict[str, SpeechVerdict]:
    """Summarize + classify a batch of speeches. Returns {url: SpeechVerdict}.

    `bodies` is an optional {url: full_text} map (fetched by the caller); when a
    URL is present its text is summarized in preference to the short RSS blurb.
    On any error returns a neutral fallback for every item so the lane never
    silently drops a speech."""
    if not posts:
        return {}
    bodies = bodies or {}

    if client is None:
        # Lazy import: anthropic is optional — if the SDK is missing or the
        # key isn't set, fall back to neutral verdicts (no silent drop).
        try:
            import anthropic
        except ImportError:
            return {
                p.url: _fallback_verdict(p, "anthropic SDK not installed")
                for p in posts
            }
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {
                p.url: _fallback_verdict(p, "ANTHROPIC_API_KEY not set")
                for p in posts
            }
        client = anthropic.Anthropic()

    verdicts: dict[str, SpeechVerdict] = {}
    for p in posts:
        verdicts[p.url] = score_speech(p, bodies.get(p.url, ""), client=client)
    return verdicts


def score_speech(
    post: ResearchPost,
    body: str = "",
    client: Any = None,
) -> SpeechVerdict:
    """Score a single speech. `body` is the full speech text if the caller
    fetched it; otherwise the RSS summary is used. Never raises — returns a
    neutral fallback on any API/parse failure."""
    if client is None:
        try:
            import anthropic
        except ImportError:
            return _fallback_verdict(post, "anthropic SDK not installed")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return _fallback_verdict(post, "ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic()

    prompt = _build_speech_prompt(post, body)
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
    except Exception as e:  # noqa: BLE001
        return _fallback_verdict(post, f"{type(e).__name__}: {e}")

    try:
        return _parse_speech_verdict(raw, post)
    except Exception as e:  # noqa: BLE001
        return _fallback_verdict(post, f"parse error: {e}")


def _build_speech_prompt(post: ResearchPost, body: str) -> str:
    """Construct the per-speech summarize+classify prompt."""
    text = (body or post.summary or "").strip()[:MAX_BODY_CHARS]
    have_body = bool(body and body.strip())
    lines = [
        "You are briefing a professional macro portfolio manager on a speech "
        "by a Federal Reserve official.",
        "",
        f"Speech title: {post.title}",
        f"Source: {post.source_display}",
        "",
        ("Speech text:" if have_body else "Speech blurb (full text unavailable — "
         "summarize and classify from this blurb + title):"),
        text if text else "(no text available; use the title only)",
        "",
        "Extract the following:",
        "1. speaker: the Federal Reserve official's name (e.g. 'Christopher Waller'). "
        "Use the title/text; '' if genuinely unclear.",
        "2. venue: where/what occasion it was (e.g. 'Reykjavik Economic Conference'), "
        "from the title/blurb/text; '' if unclear.",
        "3. summary: 2-3 sentences, plain English, on the substance — what the "
        "official said about the economy, inflation, labor, growth, and the policy path.",
        "4. worried_about: a list (up to 4) of the specific things the official "
        "signaled CONCERN, caution, or downside risk about (e.g. 'sticky services "
        "inflation', 'tariff pass-through', 'labor-market softening', 'fiscal "
        "deficits', 'financial-stability risk'). Each ≤10 words. [] if none.",
        "5. sanguine_about: a list (up to 4) of the things the official sounded "
        "COMFORTABLE, reassured, or confident about (e.g. 'inflation expectations "
        "anchored', 'consumer spending resilient', 'banking system well-capitalized'). "
        "Each ≤10 words. [] if none.",
        "6. stance: classify the monetary-policy lean as exactly one of "
        '"hawkish" (leaning toward tighter policy / higher-for-longer / '
        'inflation-vigilant), "dovish" (leaning toward easier policy / cuts / '
        'growth-and-employment-protective), or "neutral" (balanced, data-'
        "dependent, or not policy-directional). When genuinely balanced or "
        'unclear, use "neutral" — do not force a lean.',
        "7. drivers: up to 3 short phrases (≤8 words) behind the stance call.",
        "",
        "Respond with JSON only — no preamble, no markdown fences — with keys: "
        "speaker (string), venue (string), summary (string), worried_about (array), "
        'sanguine_about (array), stance (one of "hawkish"/"dovish"/"neutral"), '
        "drivers (array).",
        "",
        'Example: {"speaker": "Christopher Waller", "venue": "Economic Club of NY", '
        '"summary": "Waller said disinflation has stalled and the committee is in no '
        'hurry to cut, citing sticky services inflation and a still-firm labor market.", '
        '"worried_about": ["sticky services inflation", "energy-shock pass-through"], '
        '"sanguine_about": ["inflation expectations anchored", "labor market balanced"], '
        '"stance": "hawkish", "drivers": ["disinflation stalled", "no hurry to cut"]}',
    ]
    return "\n".join(lines)


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_speech_verdict(raw: str, post: ResearchPost) -> SpeechVerdict:
    """Parse the LLM's JSON object into a SpeechVerdict. Tolerant of code
    fences and surrounding prose."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    if not text.startswith("{"):
        m = _JSON_OBJ_RE.search(text)
        if m:
            text = m.group(0)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON object, got {type(parsed).__name__}")

    stance = str(parsed.get("stance", "")).strip().lower()
    if stance not in STANCES:
        stance = "neutral"  # unknown/invalid → neutral, never guess a lean
    summary = str(parsed.get("summary", "") or "").strip()[:600]
    speaker = str(parsed.get("speaker", "") or "").strip()[:80]
    venue = str(parsed.get("venue", "") or "").strip()[:160]

    def _strlist(key: str, cap: int, each: int) -> tuple[str, ...]:
        raw = parsed.get(key) or []
        if not isinstance(raw, list):
            return ()
        return tuple(str(x).strip()[:each] for x in raw[:cap] if str(x).strip())

    return SpeechVerdict(
        url=post.url,
        stance=stance,
        summary=summary,
        speaker=speaker,
        venue=venue,
        worried_about=_strlist("worried_about", 4, 80),
        sanguine_about=_strlist("sanguine_about", 4, 80),
        drivers=_strlist("drivers", 3, 60),
        why="",
    )


def _fallback_verdict(post: ResearchPost, reason: str) -> SpeechVerdict:
    """Neutral default — keep the speech in the digest (tagged neutral) when
    the API or parser fails, rather than silently dropping it."""
    return SpeechVerdict(
        url=post.url,
        stance="neutral",
        summary="",
        why=f"fallback: {reason}",
    )
