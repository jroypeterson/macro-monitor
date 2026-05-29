"""Haiku-backed read-worthiness scorer + macro classifier.

For each candidate research item we ask Claude two questions:
  1. Is this actually about macro/markets/economics? (drops politics-only,
     M&A, lifestyle, etc. that keyword filters miss)
  2. 1-10 read-worthiness for an institutional macro investor.

Batched in a single API call (~30 items per run) — at Haiku 4.5 pricing
the steady-state cost is < $0.01/day. JSON-mode output, indexed by
position so we can match verdicts back to ResearchPost objects without
the LLM having to echo URLs.

Defensive fallback: any API/parse error returns a permissive verdict
(is_macro=True, score=5) for every item so the digest never silently
loses content because of a scorer hiccup.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from ..collectors.rss import ResearchPost

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
MAX_SUMMARY_CHARS = 280  # keep prompt small; titles carry most of the signal


@dataclass(frozen=True)
class ScoreVerdict:
    """LLM verdict for a single research item.

    Keyed back to ResearchPost via `url` (which is the item's dedupe key —
    unique within a digest run)."""

    url: str
    is_macro: bool
    score: int  # 1-10
    why: str    # short rationale (often blank on fallback path)


def score_posts(
    posts: list[ResearchPost],
    client: Any = None,
) -> dict[str, ScoreVerdict]:
    """Score a batch of research items. Returns {url: ScoreVerdict}.

    On any error returns a permissive fallback for every item so the
    digest never collapses to zero because the scorer broke."""
    if not posts:
        return {}

    if client is None:
        # Lazy import: anthropic is optional — if the SDK is missing or
        # the key isn't set, fall back to permissive verdicts.
        try:
            import anthropic
        except ImportError:
            return _fallback_verdicts(posts, "anthropic SDK not installed")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return _fallback_verdicts(posts, "ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic()

    prompt = _build_prompt(posts)

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
    except Exception as e:  # noqa: BLE001
        return _fallback_verdicts(posts, f"{type(e).__name__}: {e}")

    try:
        verdicts = _parse_verdicts(raw, posts)
    except Exception as e:  # noqa: BLE001
        return _fallback_verdicts(posts, f"parse error: {e}")

    return verdicts


def _build_prompt(posts: list[ResearchPost]) -> str:
    """Construct the batch-scoring prompt. Items are numbered 1..N; the
    LLM responds with a JSON array of verdict objects in the same order."""
    lines = [
        "You are screening research articles for a daily macro digest sent to a "
        "professional portfolio manager. The reader cares about US/global macro: "
        "monetary policy, inflation, growth, labor markets, fiscal policy, "
        "central banks (Fed/ECB/BoJ/BoE/PBoC), rates, yields, currencies, "
        "recession signals, housing, and similar.",
        "",
        "For each article below answer two questions:",
        "",
        "1. is_macro (boolean): Is this article actually about macro/markets/"
        "economics? Return FALSE for: pure politics with no economic angle, "
        "geopolitical/military coverage, individual-stock news, M&A deal news, "
        "tech-product reviews, sports, arts, lifestyle. Mark TRUE for any "
        "article a macro investor would consider relevant even tangentially.",
        "",
        "2. score (1-10 integer): If is_macro=true, read-worthiness for a busy "
        "institutional macro investor. Use the FULL scale:",
        "   1-3: trivial daily-news ('stocks rose today', 'analyst raises target')",
        "   4-6: standard commentary, marginal new info",
        "   7-8: notable — fresh data, new framework, important policy nuance",
        "   9-10: must-read — major Fed/policy shift, regime change, exceptional analysis",
        "   If is_macro=false, score is ignored — set to 0.",
        "",
        "Articles:",
    ]
    for idx, p in enumerate(posts, start=1):
        summary = (p.summary or "")[:MAX_SUMMARY_CHARS]
        lines.append(
            f"[{idx}] Source: {p.source_display} | Title: {p.title}"
            + (f" | Summary: {summary}" if summary else "")
        )
    lines.extend(
        [
            "",
            "Respond with a JSON array of one object per article, in the same "
            "order, with keys: i (1-based index), is_macro (bool), score (int 0-10), "
            "why (≤12 word rationale). Output JSON only — no preamble, no markdown "
            "fences.",
            "",
            'Example: [{"i": 1, "is_macro": true, "score": 7, "why": "Fresh Fed analysis on rate transmission"}, '
            '{"i": 2, "is_macro": false, "score": 0, "why": "Local politics, no econ angle"}]',
        ]
    )
    return "\n".join(lines)


_JSON_ARRAY_RE = re.compile(r"\[\s*\{.*\}\s*\]", re.DOTALL)


def _parse_verdicts(
    raw: str, posts: list[ResearchPost]
) -> dict[str, ScoreVerdict]:
    """Parse the LLM's JSON response into url->verdict. Tolerant of
    leading/trailing prose by extracting the first JSON array."""
    text = raw.strip()
    # Strip markdown code fences if the model added them despite instructions
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    # If we still have prose around it, grab the JSON array
    if not text.startswith("["):
        m = _JSON_ARRAY_RE.search(text)
        if m:
            text = m.group(0)
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError(f"expected JSON array, got {type(parsed).__name__}")

    verdicts: dict[str, ScoreVerdict] = {}
    # Index verdicts by their `i` field if present, else by position
    by_index: dict[int, dict] = {}
    for pos, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            continue
        idx = item.get("i", pos)
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            idx = pos
        by_index[idx] = item

    for idx, post in enumerate(posts, start=1):
        item = by_index.get(idx)
        if item is None:
            # LLM missed this one — default to permissive
            verdicts[post.url] = ScoreVerdict(
                url=post.url, is_macro=True, score=5, why="missing from LLM response"
            )
            continue
        is_macro = bool(item.get("is_macro", True))
        score_raw = item.get("score", 5)
        try:
            score = int(score_raw)
        except (TypeError, ValueError):
            score = 5
        score = max(0, min(10, score))
        why = str(item.get("why", "") or "").strip()[:200]
        verdicts[post.url] = ScoreVerdict(
            url=post.url, is_macro=is_macro, score=score, why=why
        )

    return verdicts


def _fallback_verdicts(
    posts: list[ResearchPost], reason: str
) -> dict[str, ScoreVerdict]:
    """Permissive default — pass everything through with score=5. Used
    when the API or parser fails, so the digest never silently empties."""
    return {
        p.url: ScoreVerdict(url=p.url, is_macro=True, score=5, why=f"fallback: {reason}")
        for p in posts
    }
