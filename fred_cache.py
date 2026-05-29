"""Defensive FRED observations cache.

Phase 1 deliberately skipped a FRED observations mirror to avoid premature
caching complexity. Production reality (May 2026 FRED outage) proved the
value of a *defensive* cache: not a primary store, just a last-known-good
fallback when FRED 504s or times out.

Design constraints:
  - Single SQLite table at data/fred_cache.db
  - Keyed by series_id (latest successful pull wins; we don't keep
    per-window cache entries because callers pass lookback_years=30 and
    a single full-history pull serves every query)
  - Stores the raw JSON FRED returned + fetched_at ISO8601 timestamp
  - Pure read/write API; the FREDClient decides when to consult it
  - Tracked in git so the cache survives across cron runs

The cache is not a substitute for live data — every successful FRED call
writes through. The fallback path activates only on FREDError, and the
returned data is flagged with attrs['from_cache'] = True so downstream
surfaces (Slack post, dashboard) can warn the user that the data is
last-known-good rather than current.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "fred_cache.db"


@dataclass(frozen=True)
class CachedFetch:
    """A previously-successful FRED fetch served from cache."""

    series_id: str
    fetched_at_utc: str   # ISO8601
    observations_json: str  # raw JSON from FRED's response
    observation_start: str | None
    observation_end: str | None

    def age_hours(self, now: datetime | None = None) -> float:
        if now is None:
            now = datetime.now(timezone.utc)
        # Robustly parse ISO8601, including +00:00 or Z suffixes
        fetched = datetime.fromisoformat(self.fetched_at_utc)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return (now - fetched).total_seconds() / 3600.0


SCHEMA = """
CREATE TABLE IF NOT EXISTS series_observations (
    series_id          TEXT PRIMARY KEY,
    fetched_at_utc     TEXT NOT NULL,
    observations_json  TEXT NOT NULL,
    observation_start  TEXT,
    observation_end    TEXT
);
CREATE INDEX IF NOT EXISTS idx_series_fetched_at
    ON series_observations(fetched_at_utc);
"""


class FREDCache:
    """Connection per instance; safe to construct fresh per call site."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "FREDCache":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, series_id: str) -> CachedFetch | None:
        row = self.conn.execute(
            "SELECT * FROM series_observations WHERE series_id = ?",
            (series_id,),
        ).fetchone()
        if row is None:
            return None
        return CachedFetch(
            series_id=row["series_id"],
            fetched_at_utc=row["fetched_at_utc"],
            observations_json=row["observations_json"],
            observation_start=row["observation_start"],
            observation_end=row["observation_end"],
        )

    def count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM series_observations"
        ).fetchone()[0]

    def all_series_ids(self) -> list[str]:
        return [
            r["series_id"]
            for r in self.conn.execute(
                "SELECT series_id FROM series_observations"
            ).fetchall()
        ]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def put(
        self,
        series_id: str,
        observations_json: str,
        observation_start: str | None = None,
        observation_end: str | None = None,
        fetched_at_utc: str | None = None,
    ) -> None:
        """Upsert the cache row for `series_id`. Replaces any prior entry
        — the cache holds only the latest-successful pull per series."""
        if fetched_at_utc is None:
            fetched_at_utc = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO series_observations (
                    series_id, fetched_at_utc, observations_json,
                    observation_start, observation_end
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(series_id) DO UPDATE SET
                    fetched_at_utc = excluded.fetched_at_utc,
                    observations_json = excluded.observations_json,
                    observation_start = excluded.observation_start,
                    observation_end = excluded.observation_end
                """,
                (
                    series_id,
                    fetched_at_utc,
                    observations_json,
                    observation_start,
                    observation_end,
                ),
            )


def reconstruct_observations(cached: CachedFetch) -> dict[str, Any]:
    """Decode the cached JSON back to the dict FRED would have returned."""
    return json.loads(cached.observations_json)
