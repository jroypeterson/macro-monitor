"""Keyless Polymarket Gamma API client + market resolver.

Gamma (`https://gamma-api.polymarket.com`) needs no auth/key for reads. We use
`/public-search` for text discovery and `/events?slug=` for full market data
(outcomes + prices + volume). Trading (CLOB) would need a Polygon wallet — we
only read public odds.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import requests

GAMMA = "https://gamma-api.polymarket.com"
_UA = {"User-Agent": "macro-monitor/predmarkets (jroypeterson@gmail.com)"}
_RETRY_BACKOFF = (3, 9, 20)  # wake-race / transient-blip retry (CONVENTIONS §3)


@dataclass
class Resolved:
    """A tracked market resolved to live Polymarket data."""
    key: str
    label: str
    lane: str
    biotech: bool
    ok: bool
    title: str = ""
    url: str = ""
    volume: float = 0.0
    end_date: str = ""
    # (outcome_label, yes_probability 0..1), sorted desc. Binary → [("Yes", p)].
    outcomes: list[tuple[str, float]] = field(default_factory=list)
    note: str = ""

    @property
    def lead(self) -> tuple[str, float] | None:
        return self.outcomes[0] if self.outcomes else None

    @property
    def is_binary(self) -> bool:
        return len(self.outcomes) == 1 and self.outcomes[0][0].lower() == "yes"


def _get(path: str, params: dict, timeout: int = 25):
    last: Exception | None = None
    for i in range(len(_RETRY_BACKOFF) + 1):
        if i:
            time.sleep(_RETRY_BACKOFF[i - 1])
        try:
            r = requests.get(GAMMA + path, params=params, headers=_UA, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = e
    raise last  # type: ignore[misc]


def _as_list(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return []
    return v or []


def _yes_price(market: dict) -> float | None:
    ocs = _as_list(market.get("outcomes"))
    prs = _as_list(market.get("outcomePrices"))
    for o, p in zip(ocs, prs):
        if str(o).strip().lower() == "yes":
            try:
                return float(p)
            except (TypeError, ValueError):
                return None
    return None


def _vol(obj: dict) -> float:
    for k in ("volume", "volumeNum"):
        try:
            v = obj.get(k)
            if v is not None:
                return float(v)
        except (TypeError, ValueError):
            pass
    return 0.0


def search_events(query: str, limit: int = 20) -> list[dict]:
    """Active events matching a text query (title/slug only — thin objects)."""
    data = _get("/public-search", {
        "q": query, "limit_per_type": str(limit), "events_status": "active",
    })
    return data.get("events", []) if isinstance(data, dict) else []


def fetch_event(slug: str) -> dict | None:
    data = _get("/events", {"slug": slug})
    rows = data if isinstance(data, list) else data.get("data", [])
    return rows[0] if rows else None


def _normalize(event: dict) -> list[tuple[str, float]]:
    """Event markets → [(label, yes_prob)] desc. Binary (1 market) → [('Yes', p)]."""
    markets = [m for m in (event.get("markets") or []) if not m.get("closed")]
    if not markets:
        markets = event.get("markets") or []
    if len(markets) == 1:
        p = _yes_price(markets[0])
        return [("Yes", p)] if p is not None else []
    out: list[tuple[str, float]] = []
    for m in markets:
        p = _yes_price(m)
        if p is None:
            continue
        label = (m.get("groupItemTitle") or m.get("question") or "?").strip()
        out.append((label, p))
    out.sort(key=lambda t: t[1], reverse=True)
    return out


def resolve(spec, max_candidates: int = 4) -> Resolved:
    """Resolve a TrackedMarket spec to the highest-volume active event whose
    title contains spec.match. Never raises — returns ok=False with a note."""
    base = Resolved(key=spec.key, label=spec.label, lane=spec.lane, biotech=spec.biotech, ok=False)
    try:
        hits = search_events(spec.query)
    except Exception as e:  # network etc. — degrade, don't crash the run
        base.note = f"search failed: {type(e).__name__}"
        return base
    cand = [e for e in hits if spec.match.lower() in (e.get("title") or "").lower()]
    if not cand:
        base.note = "not found"
        return base
    best: Resolved | None = None
    for e in cand[:max_candidates]:
        slug = e.get("slug")
        if not slug:
            continue
        try:
            full = fetch_event(slug)
        except Exception:
            full = None
        if not full or full.get("closed"):
            continue
        outcomes = _normalize(full)
        if not outcomes:
            continue
        r = Resolved(
            key=spec.key, label=spec.label, lane=spec.lane, biotech=spec.biotech, ok=True,
            title=full.get("title", ""), url=f"https://polymarket.com/event/{slug}",
            volume=_vol(full), end_date=str(full.get("endDate") or "")[:10], outcomes=outcomes,
        )
        if best is None or r.volume > best.volume:
            best = r
    if best is None:
        base.note = "no active market with prices"
        return base
    return best


def resolve_all(specs) -> list[Resolved]:
    return [resolve(s) for s in specs]
