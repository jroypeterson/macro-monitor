"""Odds history + movers for the prediction-market lane.

Each run appends a dated snapshot of every resolved market's outcomes, keyed by
the STABLE config key (so a market that rolls over — "Fed Decision in June" →
"...July" — keeps one continuous history under key `fed_meeting`). `movers()`
then flags large week-over-week / year-over-year shifts.

Persisted to data/predmarket_history.json and committed by the weekly workflow
so deltas survive across fresh CI checkouts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .client import Resolved

HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "predmarket_history.json"
_MAX_SNAPSHOTS = 70   # ~16 months of weekly snapshots; bounds file growth


@dataclass
class Mover:
    key: str
    label: str
    lane: str
    outcome: str        # which outcome moved (matched label; "Yes" for binary)
    old: float          # prior probability 0..1
    new: float          # current probability 0..1
    delta_pp: float     # (new - old) * 100, signed
    period: str         # "WoW" | "YoY"

    @property
    def biotech(self) -> bool:  # set by caller when needed
        return False


def load(path: Path | None = None) -> dict:
    path = path or HISTORY_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def record(resolved: list[Resolved], now: datetime, path: Path | None = None) -> dict:
    """Append today's snapshot for each live market (idempotent per UTC date)."""
    path = path or HISTORY_PATH
    hist = load(path)
    today = now.strftime("%Y-%m-%d")
    for r in resolved:
        if not r.ok:
            continue
        snaps = hist.setdefault(r.key, [])
        snap = {"date": today, "title": r.title, "volume": r.volume,
                "outcomes": [[lbl, p] for lbl, p in r.outcomes]}
        if snaps and snaps[-1]["date"] == today:
            snaps[-1] = snap          # overwrite a same-day re-run
        else:
            snaps.append(snap)
        if len(snaps) > _MAX_SNAPSHOTS:
            del snaps[: len(snaps) - _MAX_SNAPSHOTS]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hist, indent=1), encoding="utf-8")
    return hist


def _nearest(snaps: list[dict], target: date, tol_days: int) -> dict | None:
    """The snapshot whose date is closest to `target` within ±tol_days."""
    best, best_gap = None, tol_days + 1
    for s in snaps:
        try:
            d = datetime.strptime(s["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        gap = abs((d - target).days)
        if gap <= tol_days and gap < best_gap:
            best, best_gap = s, gap
    return best


def _outcome_map(snap: dict) -> dict[str, float]:
    return {lbl: float(p) for lbl, p in snap.get("outcomes", [])}


def movers(resolved: list[Resolved], now: datetime, *, hist: dict | None = None,
           threshold_pp: float = 8.0) -> list[Mover]:
    """Flag markets whose lead/any-matched outcome shifted >= threshold_pp since
    ~7 days ago (WoW) or ~365 days ago (YoY). YoY only fires where a year of
    history exists (sparse until the archive matures). Returns biggest move per
    market per period, sorted by |delta| desc."""
    hist = load() if hist is None else hist
    today = now.date()
    out: list[Mover] = []
    lane_by_key = {r.key: (r.lane, r.label, r.biotech) for r in resolved}
    for r in resolved:
        if not r.ok:
            continue
        snaps = hist.get(r.key, [])
        cur = {lbl: p for lbl, p in r.outcomes}
        for period, days, tol in (("WoW", 7, 3), ("YoY", 365, 30)):
            prior = _nearest(snaps, today - timedelta(days=days), tol)
            if not prior:
                continue
            old_map = _outcome_map(prior)
            best: Mover | None = None
            for lbl, new_p in cur.items():
                if lbl not in old_map:
                    continue
                d = (new_p - old_map[lbl]) * 100
                if abs(d) >= threshold_pp and (best is None or abs(d) > abs(best.delta_pp)):
                    best = Mover(r.key, r.label, r.lane, lbl, old_map[lbl], new_p, d, period)
            if best:
                out.append(best)
    out.sort(key=lambda m: abs(m.delta_pp), reverse=True)
    return out
