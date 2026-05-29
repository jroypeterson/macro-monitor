"""Posts ledger — single-table SQLite store for dedupe + revision detection.

Two-tier hashes with headline-subsumes-component:
  - Headline-hash change → REVISED top-level post.
  - Component-hash change only → thread "notes on revisions" line.
  - Both change in one fetch → ONE REVISED top-level post (headline subsumes).
  - Both hashes + values are written transactionally so a mid-update crash
    can't leave a half-revised period that re-fires next poll.

Annual-benchmark flood guard: callers query `changed_periods_in_batch(family)`
after a fetch. If that returns N >= 3, the caller emits a single
"📅 Annual benchmark revision" summary instead of N REVISED posts.

This file is intentionally narrow — no Slack, no Pandas, no JSON
serialization. The orchestrator decides what to do with the diff signals.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "state" / "posts.db"


class PostDecision(Enum):
    NEW_PERIOD = "new_period"                        # never posted before
    REVISED_HEADLINE = "revised_headline"            # headline hash changed (subsumes component)
    REVISED_COMPONENT_ONLY = "revised_component"     # only component hash changed
    UNCHANGED = "unchanged"                          # both hashes match, no-op


@dataclass(frozen=True)
class LedgerEntry:
    family_id: str
    period: str                # e.g. "2026-04"
    headline_hash: str
    component_hash: str
    headline_values: dict      # parsed back from JSON
    component_values: dict
    posted_at: str             # ISO8601
    slack_channel: str | None
    slack_ts: str | None
    revision_count: int


@dataclass(frozen=True)
class DiffResult:
    """Returned by check_and_record. Tells the orchestrator what to post.

    `prior_*_values` are the values displayed in the most recent post; the
    orchestrator uses them to render the diff in a REVISED post.
    """

    decision: PostDecision
    prior_entry: LedgerEntry | None
    revision_count: int


def hash_values(values: dict[str, float | None]) -> str:
    """Stable SHA-256 of a values dict. Floats are formatted to 6 decimal
    places to avoid spurious revisions from float-printing differences.
    """
    formatted = {
        k: (round(v, 6) if isinstance(v, float) else v)
        for k, v in sorted(values.items())
    }
    payload = json.dumps(formatted, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PostsLedger:
    """Single-table SQLite store. Connection per instance; safe to construct
    fresh per CLI invocation (typical pattern)."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS posts (
        family_id        TEXT NOT NULL,
        period           TEXT NOT NULL,
        headline_hash    TEXT NOT NULL,
        component_hash   TEXT NOT NULL,
        headline_values  TEXT NOT NULL,   -- JSON
        component_values TEXT NOT NULL,   -- JSON
        posted_at        TEXT NOT NULL,
        slack_channel    TEXT,
        slack_ts         TEXT,
        revision_count   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (family_id, period)
    );
    CREATE INDEX IF NOT EXISTS idx_posts_family_period
        ON posts(family_id, period);
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "PostsLedger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, family_id: str, period: str) -> LedgerEntry | None:
        row = self.conn.execute(
            "SELECT * FROM posts WHERE family_id = ? AND period = ?",
            (family_id, period),
        ).fetchone()
        if not row:
            return None
        return _entry_from_row(row)

    def changed_periods_in_batch(
        self,
        family_id: str,
        candidate: dict[str, tuple[str, str]],
    ) -> list[str]:
        """Given a dict of {period: (headline_hash, component_hash)}, return
        the list of periods whose hashes differ from what the ledger has on
        record. Used by the annual-benchmark flood guard: if a single
        fetch detects ≥3 changed periods, the caller emits one summary
        instead of N REVISED posts.
        """
        changed: list[str] = []
        for period, (h_hash, c_hash) in candidate.items():
            prior = self.get(family_id, period)
            if prior is None:
                # Never posted = "new period," not a revision in the
                # benchmark-revision sense; benchmark guard only fires on
                # changes to ALREADY-posted periods.
                continue
            if prior.headline_hash != h_hash or prior.component_hash != c_hash:
                changed.append(period)
        return changed

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        *,
        family_id: str,
        period: str,
        headline_values: dict[str, float | None],
        component_values: dict[str, float | None],
    ) -> DiffResult:
        """READ-ONLY diff check. No write. Used by dry-runs and as the
        first half of the live post (compute → post → record_post).
        """
        h_hash = hash_values(headline_values)
        c_hash = hash_values(component_values)
        prior = self.get(family_id, period)

        if prior is None:
            decision = PostDecision.NEW_PERIOD
        else:
            headline_changed = prior.headline_hash != h_hash
            component_changed = prior.component_hash != c_hash
            if headline_changed:
                # Headline subsumes component — fold both into one REVISED post.
                decision = PostDecision.REVISED_HEADLINE
            elif component_changed:
                decision = PostDecision.REVISED_COMPONENT_ONLY
            else:
                decision = PostDecision.UNCHANGED

        revision_count = (prior.revision_count if prior else 0) + (
            0 if decision in (PostDecision.NEW_PERIOD, PostDecision.UNCHANGED) else 1
        )
        return DiffResult(decision=decision, prior_entry=prior, revision_count=revision_count)

    def record_post(
        self,
        *,
        family_id: str,
        period: str,
        headline_values: dict[str, float | None],
        component_values: dict[str, float | None],
        slack_channel: str | None = None,
        slack_ts: str | None = None,
    ) -> DiffResult:
        """Write the post to the ledger. Called AFTER a successful Slack
        post so we can capture `slack_ts` for thread-reply addressing on
        future revisions.

        Transactional: both hashes + values land in one SQL transaction or
        neither does, so a crash mid-update can't leave a half-revised
        period that re-fires next poll.

        Returns a DiffResult describing the recorded state.
        """
        diff = self.compute_diff(
            family_id=family_id,
            period=period,
            headline_values=headline_values,
            component_values=component_values,
        )

        # Skip the write if nothing changed.
        if diff.decision == PostDecision.UNCHANGED:
            return diff

        h_hash = hash_values(headline_values)
        c_hash = hash_values(component_values)
        posted_at = datetime.now(timezone.utc).isoformat()

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO posts (
                    family_id, period, headline_hash, component_hash,
                    headline_values, component_values, posted_at,
                    slack_channel, slack_ts, revision_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(family_id, period) DO UPDATE SET
                    headline_hash = excluded.headline_hash,
                    component_hash = excluded.component_hash,
                    headline_values = excluded.headline_values,
                    component_values = excluded.component_values,
                    posted_at = excluded.posted_at,
                    slack_channel = excluded.slack_channel,
                    slack_ts = excluded.slack_ts,
                    revision_count = excluded.revision_count
                """,
                (
                    family_id,
                    period,
                    h_hash,
                    c_hash,
                    json.dumps(headline_values, sort_keys=True, default=_jsonable),
                    json.dumps(component_values, sort_keys=True, default=_jsonable),
                    posted_at,
                    slack_channel,
                    slack_ts,
                    diff.revision_count,
                ),
            )

        return diff

    # Backwards-compat wrapper for the existing tests that use the old
    # combined `check_and_record` API. Equivalent to compute_diff + record_post.
    def check_and_record(
        self,
        *,
        family_id: str,
        period: str,
        headline_values: dict[str, float | None],
        component_values: dict[str, float | None],
        slack_channel: str | None = None,
        slack_ts: str | None = None,
    ) -> DiffResult:
        return self.record_post(
            family_id=family_id,
            period=period,
            headline_values=headline_values,
            component_values=component_values,
            slack_channel=slack_channel,
            slack_ts=slack_ts,
        )


def _entry_from_row(row: sqlite3.Row) -> LedgerEntry:
    return LedgerEntry(
        family_id=row["family_id"],
        period=row["period"],
        headline_hash=row["headline_hash"],
        component_hash=row["component_hash"],
        headline_values=json.loads(row["headline_values"]),
        component_values=json.loads(row["component_values"]),
        posted_at=row["posted_at"],
        slack_channel=row["slack_channel"],
        slack_ts=row["slack_ts"],
        revision_count=row["revision_count"],
    )


def _jsonable(obj):
    """JSON encoder fallback. None and floats serialize naturally; this
    catches odd numpy / pandas types if they sneak in."""
    if hasattr(obj, "item"):
        return obj.item()
    return str(obj)
