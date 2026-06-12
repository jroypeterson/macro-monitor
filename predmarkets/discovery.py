"""Weekly discovery: surface NEWLY-opened relevant prediction markets.

The fact that a market just opened on something relevant is itself a signal
(JP). We sweep Polymarket by JP's macro + healthcare/biotech keywords, diff
against a persisted "seen" slug set, and surface markets we haven't seen before.
First run seeds the seen-set silently (no flood). Markets already in the curated
TRACKED set are excluded (they're shown in the main rundown).

Persisted to data/predmarket_seen.json, committed by the weekly workflow.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import client
from .config import TRACKED

SEEN_PATH = Path(__file__).resolve().parent.parent / "data" / "predmarket_seen.json"

# Search terms (broad) + per-lane relevance keywords (the search is fuzzy, so we
# re-filter the returned titles).
_SEARCH_TERMS = [
    "recession", "fed", "interest rate", "rate cut", "CPI", "inflation", "GDP",
    "unemployment", "jobs report", "government shutdown", "debt ceiling", "tariff",
    "FDA", "drug approval", "clinical trial", "pandemic", "measles", "vaccine",
    "outbreak", "bird flu", "Medicare", "Medicaid", "obesity", "GLP-1", "cancer",
    "biotech", "Alzheimer", "RFK", "HHS", "CDC", "NIH",
]
_MACRO_REL = ("recession", "fed", "rate cut", "rate hike", "interest rate", "cpi",
              "inflation", "gdp", "unemployment", "jobs", "payroll", "shutdown",
              "debt ceiling", "tariff", "s&p 500", "nasdaq", "treasury", "yield",
              "dollar", "bitcoin", "oil")
_HC_REL = ("fda", "drug", "approv", "clinical", "phase 3", "pdufa", "cancer",
           "vaccine", "pandemic", "measles", "ebola", "covid", "glp", "obesity",
           "alzheim", "medicare", "medicaid", "obamacare", " aca", "rfk", "hhs",
           "cdc", "nih", "biotech", "pharma", "disease", "therap", "outbreak",
           "bird flu", "h5n1", "autism", "opioid")


@dataclass
class NewMarket:
    title: str
    url: str
    lane: str           # "macro" | "healthcare"
    volume: float
    end_date: str
    lead_label: str
    lead_prob: float


def _lane_for(title: str) -> str | None:
    t = title.lower()
    if any(k in t for k in _HC_REL):
        return "healthcare"
    if any(k in t for k in _MACRO_REL):
        return "macro"
    return None


def _is_tracked(title: str) -> bool:
    t = title.lower()
    return any(spec.match.lower() in t for spec in TRACKED)


def load_seen(path: Path | None = None) -> set[str]:
    path = path or SEEN_PATH
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_seen(seen: set[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen), indent=0), encoding="utf-8")


def discover_new(now: datetime, *, min_volume: float = 10_000,
                 path: Path | None = None, max_surface: int = 12) -> list[NewMarket]:
    """Sweep for relevant markets; return ones whose slug we've never seen.
    First run (no seen file) seeds silently and returns []. Always persists the
    updated seen-set."""
    path = path or SEEN_PATH
    first_run = not path.exists()
    seen = load_seen(path)

    # slug -> (title, lane). Collect relevant, non-tracked candidates.
    candidates: dict[str, tuple[str, str]] = {}
    for term in _SEARCH_TERMS:
        try:
            for e in client.search_events(term):
                title = e.get("title") or ""
                slug = e.get("slug")
                if not slug or slug in candidates:
                    continue
                lane = _lane_for(title)
                if lane is None or _is_tracked(title):
                    continue
                candidates[slug] = (title, lane)
        except Exception:
            continue  # one bad term shouldn't sink discovery

    new_slugs = [s for s in candidates if s not in seen]
    seen.update(candidates.keys())
    _save_seen(seen, path)
    if first_run:
        return []   # seeded; don't flood the first digest

    out: list[NewMarket] = []
    for slug in new_slugs:
        title, lane = candidates[slug]
        try:
            full = client.fetch_event(slug)
        except Exception:
            full = None
        if not full or full.get("closed"):
            continue
        vol = client._vol(full)
        if vol < min_volume:
            continue
        outs = client._normalize(full)
        if not outs:
            continue
        lead_lbl, lead_p = outs[0]
        out.append(NewMarket(title=title, url=f"https://polymarket.com/event/{slug}",
                             lane=lane, volume=vol, end_date=str(full.get("endDate") or "")[:10],
                             lead_label=lead_lbl, lead_prob=lead_p))
    out.sort(key=lambda m: m.volume, reverse=True)
    return out[:max_surface]
