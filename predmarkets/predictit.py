"""Keyless PredictIt client.

PredictIt exposes a single public feed of all open markets
(`/api/marketdata/all/`, no auth). It's politics-only but the most *calibrated*
money market (its $3,500 per-trader cap blocks whales — Vanderbilt 2025 put it
at 93% vs Kalshi 78% / Polymarket 67%), so we use it for the sharp
control-of-government + legislative-enactment reads. No per-market volume in
this feed, so PredictIt markets render with a 🎯 (calibrated) flag, not a $.
"""
from __future__ import annotations

import time

import requests

from .client import Resolved

ALL_URL = "https://www.predictit.org/api/marketdata/all/"
_UA = {"User-Agent": "macro-monitor/predmarkets (jroypeterson@gmail.com)"}
_RETRY_BACKOFF = (3, 9, 20)

_cache: list[dict] | None = None


def fetch_all(force: bool = False) -> list[dict]:
    """All open PredictIt markets (process-cached so resolve_all hits once)."""
    global _cache
    if _cache is not None and not force:
        return _cache
    last: Exception | None = None
    for i in range(len(_RETRY_BACKOFF) + 1):
        if i:
            time.sleep(_RETRY_BACKOFF[i - 1])
        try:
            r = requests.get(ALL_URL, headers=_UA, timeout=25)
            r.raise_for_status()
            _cache = (r.json() or {}).get("markets", [])
            return _cache
        except requests.RequestException as e:
            last = e
    raise last  # type: ignore[misc]


def _outcomes(market: dict) -> list[tuple[str, float]]:
    cs = market.get("contracts") or []
    if len(cs) == 1:
        p = cs[0].get("lastTradePrice")
        return [("Yes", float(p))] if p is not None else []
    out: list[tuple[str, float]] = []
    for c in cs:
        p = c.get("lastTradePrice")
        if p is None:
            continue
        lbl = (c.get("shortName") or c.get("name") or "?").strip()
        out.append((lbl, float(p)))
    out.sort(key=lambda t: t[1], reverse=True)
    return out


def resolve(spec) -> Resolved:
    """Resolve a PredictIt-sourced TrackedMarket by name substring. Never raises."""
    base = Resolved(key=spec.key, label=spec.label, lane=spec.lane, biotech=spec.biotech,
                    ok=False, source="predictit")
    try:
        mkts = fetch_all()
    except Exception as e:
        base.note = f"fetch failed: {type(e).__name__}"
        return base
    cand = [m for m in mkts if spec.match in (m.get("name") or "").lower()]
    if not cand:
        base.note = "not found"
        return base
    m = cand[0]
    outs = _outcomes(m)
    if not outs:
        base.note = "no prices"
        return base
    return Resolved(key=spec.key, label=spec.label, lane=spec.lane, biotech=spec.biotech,
                    ok=True, title=m.get("name", ""), url=m.get("url", ""), volume=0.0,
                    end_date="", outcomes=outs, source="predictit")
