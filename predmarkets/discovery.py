"""Weekly discovery: surface NEWLY-opened relevant prediction markets across
Polymarket + PredictIt + Kalshi.

A market just opening on something relevant is itself a signal (JP). We sweep
each source by JP's keywords, diff against a persisted seen-set (ids are
source-prefixed: pm:/pi:/kalshi:), and surface unseen ones. Seeding is
PER SOURCE — when a new source is added later, it seeds silently on its first
appearance instead of flooding. Markets already in the curated TRACKED set are
excluded. JP's priority: healthcare first, then any *meaningful* legislative
change, then macro.

Persisted to data/predmarket_seen.json, committed by the weekly workflow.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

from . import client, predictit
from .config import TRACKED

SEEN_PATH = Path(__file__).resolve().parent.parent / "data" / "predmarket_seen.json"
_KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
_UA = {"User-Agent": "macro-monitor/predmarkets (jroypeterson@gmail.com)"}

_SEARCH_TERMS = [
    "recession", "fed", "interest rate", "rate cut", "CPI", "inflation", "GDP",
    "unemployment", "jobs report", "government shutdown", "debt ceiling", "tariff",
    "FDA", "drug approval", "clinical trial", "pandemic", "measles", "vaccine",
    "outbreak", "bird flu", "Medicare", "Medicaid", "obesity", "GLP-1", "cancer",
    "biotech", "Alzheimer", "RFK", "HHS", "CDC", "NIH",
]
_MACRO_REL = ("recession", "fed", "rate cut", "rate hike", "interest rate", "cpi",
              "inflation", "gdp", "unemployment", "jobs", "payroll", "tariff",
              "s&p 500", "nasdaq", "treasury", "yield", "dollar", "bitcoin", "oil")
_HC_REL = ("fda", "drug", "approv", "clinical", "phase 3", "pdufa", "cancer",
           "vaccine", "pandemic", "measles", "ebola", "covid", "glp", "obesity",
           "alzheim", "medicare", "medicaid", "obamacare", " aca", "rfk", "hhs",
           "cdc", "nih", "biotech", "pharma", "disease", "therap", "outbreak",
           "bird flu", "h5n1", "autism", "opioid", "abortion")
# "meaningful legislative change" signals (JP's broad interest)
_LEG_REL = ("act enacted", "act be enacted", "act passes", "pass the", "be enacted",
            "be passed", "reconciliation", "debt ceiling", "shutdown", "repeal",
            "tax", "tariff act", "ban ", "mandate", "executive order", "scotus",
            "supreme court", "redistricting", "filibuster", "appropriation",
            "stimulus", "clarity act", "save act", "subsid", "minimum wage")


@dataclass
class NewMarket:
    title: str
    url: str
    lane: str           # "macro" | "healthcare" | "legislative"
    volume: float       # 0 when source has no per-market volume (PredictIt)
    end_date: str
    lead_label: str
    lead_prob: float
    source: str = "polymarket"   # polymarket | predictit | kalshi


def _lane_for(title: str) -> str | None:
    t = title.lower()
    if any(k in t for k in _HC_REL):
        return "healthcare"
    if any(k in t for k in _LEG_REL):
        return "legislative"
    if any(k in t for k in _MACRO_REL):
        return "macro"
    return None


def _is_tracked(title: str) -> bool:
    t = title.lower()
    return any(spec.match and spec.match.lower() in t for spec in TRACKED)


def load_seen(path: Path | None = None) -> set[str]:
    path = path or SEEN_PATH
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    # Migrate legacy bare Polymarket slugs to the pm: prefix.
    return {(s if ":" in s else f"pm:{s}") for s in raw}


def _save_seen(seen: set[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen), indent=0), encoding="utf-8")


def _kget(path: str, params: dict):
    r = requests.get(_KALSHI + path, params=params, headers=_UA, timeout=25)
    r.raise_for_status()
    return r.json()


# ---- per-source candidate gathering: uid -> (source, ref, title, lane) ----

def _gather_polymarket(found: dict) -> None:
    for term in _SEARCH_TERMS:
        try:
            for e in client.search_events(term):
                title, slug = e.get("title") or "", e.get("slug")
                if not slug:
                    continue
                lane = _lane_for(title)
                if lane is None or _is_tracked(title):
                    continue
                found.setdefault(f"pm:{slug}", ("polymarket", slug, title, lane))
        except Exception:
            continue


def _gather_predictit(found: dict) -> None:
    try:
        for m in predictit.fetch_all():
            title, mid = m.get("name") or "", m.get("id")
            if mid is None:
                continue
            lane = _lane_for(title)
            if lane is None or _is_tracked(title):
                continue
            found[f"pi:{mid}"] = ("predictit", m, title, lane)
    except Exception:
        pass


def _gather_kalshi(found: dict) -> None:
    for cat in ("Economics", "Politics", "Health", "Science and Technology"):
        try:
            series = _kget("/series/", {"category": cat}).get("series", []) or []
        except Exception:
            continue
        for s in series:
            title, tk = s.get("title") or "", s.get("ticker")
            if not tk:
                continue
            lane = _lane_for(title)
            if lane is None or _is_tracked(title):
                continue
            found.setdefault(f"kalshi:{tk}", ("kalshi", tk, title, lane))


# ---- build a NewMarket (with odds) for a newly-seen candidate ----

def _build(src: str, ref, title: str, lane: str, min_volume: float) -> NewMarket | None:
    if src == "polymarket":
        try:
            full = client.fetch_event(ref)
        except Exception:
            return None
        if not full or full.get("closed"):
            return None
        vol = client._vol(full)
        if vol < min_volume:
            return None
        outs = client._normalize(full)
        if not outs:
            return None
        return NewMarket(title, f"https://polymarket.com/event/{ref}", lane, vol,
                         str(full.get("endDate") or "")[:10], outs[0][0], outs[0][1], "polymarket")
    if src == "predictit":
        outs = predictit._outcomes(ref)
        if not outs:
            return None
        return NewMarket(title, ref.get("url", ""), lane, 0.0, "", outs[0][0], outs[0][1], "predictit")
    if src == "kalshi":
        try:
            mks = _kget("/markets", {"series_ticker": ref, "status": "open", "limit": "20"}).get("markets", [])
        except Exception:
            return None
        if not mks:
            return None   # listed but no live market → not a real "open" yet
        m = max(mks, key=lambda x: x.get("volume", 0) or 0)
        last = m.get("last_price")
        lead_p = (last / 100.0) if isinstance(last, (int, float)) else 0.0
        sub = m.get("yes_sub_title") or m.get("title") or "Yes"
        return NewMarket(title, f"https://kalshi.com/markets/{ref}", lane,
                         float(m.get("volume", 0) or 0), str(m.get("close_time") or "")[:10],
                         sub, lead_p, "kalshi")
    return None


def discover_new(now: datetime, *, min_volume: float = 10_000,
                 path: Path | None = None, max_surface: int = 14) -> list[NewMarket]:
    """Sweep all sources; return markets whose source-prefixed id we've never
    seen. Each source seeds silently on its first appearance. Always persists
    the updated seen-set."""
    path = path or SEEN_PATH
    seen = load_seen(path)
    seeded = {pfx: any(u.startswith(pfx) for u in seen) for pfx in ("pm:", "pi:", "kalshi:")}

    found: dict[str, tuple] = {}
    _gather_polymarket(found)
    _gather_predictit(found)
    _gather_kalshi(found)

    pfx_of = {"polymarket": "pm:", "predictit": "pi:", "kalshi": "kalshi:"}
    new_candidates = [
        (uid, *meta) for uid, meta in found.items()
        if seeded[pfx_of[meta[0]]] and uid not in seen
    ]
    seen.update(found.keys())
    _save_seen(seen, path)

    out: list[NewMarket] = []
    for uid, src, ref, title, lane in new_candidates:
        nm = _build(src, ref, title, lane, min_volume)
        if nm:
            out.append(nm)
    # Polymarket (real volume) first, then by volume desc.
    out.sort(key=lambda m: (m.source != "polymarket", -m.volume))
    return out[:max_surface]
