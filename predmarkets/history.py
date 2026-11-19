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
import os
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


class HistoryUnreadable(RuntimeError):
    """An existing state file could not be read. Distinct from "no file yet"
    (a first run): writing after this would replace the history with one day."""


def read_json_state(path: Path, *, strict: bool, empty, exc_type=HistoryUnreadable,
                    valid=None):
    """Read a JSON state file. Missing -> `empty` (first run). Unreadable, or
    parseable but failing `valid` (wrong shape: a bare string would iterate into
    one-character ids) -> `empty` when lenient, `exc_type` when strict, so a
    caller about to WRITE the file back never mistakes a bad file for an empty one."""
    if not path.exists():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        if strict:
            raise exc_type(f"{path}: {type(e).__name__}: {e}") from e
        return empty
    if valid is not None and not valid(data):
        if strict:
            raise exc_type(f"{path}: unexpected shape ({type(data).__name__})")
        return empty
    return data


def _valid_history(data) -> bool:
    return isinstance(data, dict) and all(
        isinstance(v, list) and all(isinstance(s, dict) for s in v) for v in data.values())


def write_json_atomic(path: Path, text: str) -> None:
    """Write to a sibling temp file, then os.replace: a crash mid-write leaves
    the previous file intact instead of a truncated one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load(path: Path | None = None, *, strict: bool = False) -> dict:
    path = path or HISTORY_PATH
    return read_json_state(path, strict=strict, empty={}, valid=_valid_history)


def record(resolved: list[Resolved], now: datetime, path: Path | None = None) -> dict:
    """Append today's snapshot for each live market (idempotent per UTC date).

    Raises HistoryUnreadable, writing nothing, if the existing file is corrupt."""
    path = path or HISTORY_PATH
    hist = load(path, strict=True)
    today = now.strftime("%Y-%m-%d")
    for r in resolved:
        if not r.ok:
            continue
        snaps = hist.setdefault(r.key, [])
        snap = {"date": today, "title": r.title, "url": r.url, "volume": r.volume,
                "outcomes": [[lbl, p] for lbl, p in r.outcomes]}
        if snaps and snaps[-1]["date"] == today:
            snaps[-1] = snap          # overwrite a same-day re-run
        else:
            snaps.append(snap)
        if len(snaps) > _MAX_SNAPSHOTS:
            del snaps[: len(snaps) - _MAX_SNAPSHOTS]
    write_json_atomic(path, json.dumps(hist, indent=1))
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
            # The key is continuous across contract rolls by design ("Fed Decision
            # in June" -> "...July" both live under `fed_meeting`), so a delta is
            # only meaningful between two snapshots of the SAME contract.
            # URL (event slug) is the stronger identity -- two contracts can share
            # a title. Legacy snapshots carry only the title, so fall back to it.
            if prior.get("url") and r.url:
                if prior["url"] != r.url:
                    continue
            elif prior.get("title") != r.title:
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
