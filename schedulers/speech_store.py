"""Queryable archive of Fed speeches — full text + LLM summary/worries/comforts.

Separate from the Slack-post dedup ledger (state/fed_speeches_posted.db). This
is the *content* store: one row per speech with the cleaned full transcript plus
the structured read (summary, what the official is worried about vs sanguine
about, stance). Backs ad-hoc questions like "what has Waller been worried about
lately?" via SQL, and regenerates a human-readable markdown library.

DB:  macro_monitor/data/fed_speeches.db   (table `speeches`, keyed by url)
MD:  macro_monitor/readable/fed_speeches.md
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "fed_speeches.db"
DEFAULT_MD_PATH = Path(__file__).parent.parent / "readable" / "fed_speeches.md"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS speeches (
    url             TEXT PRIMARY KEY,
    speaker         TEXT,
    venue           TEXT,
    title           TEXT,
    source          TEXT,
    speech_date     TEXT,   -- ISO date (YYYY-MM-DD) or ''
    stance          TEXT,
    summary         TEXT,
    worried_about   TEXT,   -- JSON array
    sanguine_about  TEXT,   -- JSON array
    drivers         TEXT,   -- JSON array
    full_text       TEXT,
    archived_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_speeches_speaker ON speeches(speaker);
CREATE INDEX IF NOT EXISTS idx_speeches_date ON speeches(speech_date);
CREATE INDEX IF NOT EXISTS idx_speeches_stance ON speeches(stance);
"""


@dataclass(frozen=True)
class SpeechRecord:
    url: str
    speaker: str = ""
    venue: str = ""
    title: str = ""
    source: str = ""
    speech_date: str = ""
    stance: str = "neutral"
    summary: str = ""
    worried_about: tuple[str, ...] = field(default_factory=tuple)
    sanguine_about: tuple[str, ...] = field(default_factory=tuple)
    drivers: tuple[str, ...] = field(default_factory=tuple)
    full_text: str = ""


class SpeechStore:
    """SQLite archive of scored Fed speeches (idempotent upsert by url)."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SpeechStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def has(self, url: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM speeches WHERE url = ?", (url,)
        ).fetchone() is not None

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM speeches").fetchone()[0]

    def upsert(self, rec: SpeechRecord) -> None:
        """Insert or replace by url. Idempotent — re-archiving updates in place."""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO speeches (
                    url, speaker, venue, title, source, speech_date, stance,
                    summary, worried_about, sanguine_about, drivers, full_text,
                    archived_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    rec.url, rec.speaker, rec.venue, rec.title, rec.source,
                    rec.speech_date, rec.stance, rec.summary,
                    json.dumps(list(rec.worried_about)),
                    json.dumps(list(rec.sanguine_about)),
                    json.dumps(list(rec.drivers)),
                    rec.full_text,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def all_records(self) -> list[dict]:
        """Every speech, newest speech_date first (blank dates last)."""
        rows = self.conn.execute(
            "SELECT * FROM speeches ORDER BY (speech_date = '') ASC, "
            "speech_date DESC, archived_at DESC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def search(
        self,
        *,
        speaker: str | None = None,
        stance: str | None = None,
        text: str | None = None,
    ) -> list[dict]:
        """Convenience filter. `speaker`/`text` are case-insensitive substrings;
        `text` matches title/summary/worries/comforts/full_text."""
        clauses, params = [], []
        if speaker:
            clauses.append("LOWER(speaker) LIKE ?")
            params.append(f"%{speaker.lower()}%")
        if stance:
            clauses.append("stance = ?")
            params.append(stance.lower())
        if text:
            like = f"%{text.lower()}%"
            clauses.append(
                "(LOWER(title) LIKE ? OR LOWER(summary) LIKE ? OR "
                "LOWER(worried_about) LIKE ? OR LOWER(sanguine_about) LIKE ? OR "
                "LOWER(full_text) LIKE ?)"
            )
            params.extend([like, like, like, like, like])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self.conn.execute(
            "SELECT * FROM speeches" + where
            + " ORDER BY (speech_date = '') ASC, speech_date DESC",
            params,
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(r: sqlite3.Row) -> dict:
        d = dict(r)
        for k in ("worried_about", "sanguine_about", "drivers"):
            try:
                d[k] = json.loads(d.get(k) or "[]")
            except (TypeError, ValueError):
                d[k] = []
        return d


_STANCE_BADGE = {"hawkish": "🦅 Hawkish", "dovish": "🕊️ Dovish", "neutral": "➖ Neutral"}


def export_markdown(records: list[dict], out_path: Path | str = DEFAULT_MD_PATH) -> Path:
    """Regenerate the human-readable speech library from the store records.
    Newest first; full transcript tucked in a collapsible <details> block."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    tally = {"hawkish": 0, "dovish": 0, "neutral": 0}
    for r in records:
        s = r.get("stance", "neutral")
        tally[s if s in tally else "neutral"] += 1

    lines = [
        "# Fed Speech Library",
        "",
        f"Queryable archive of Federal Reserve speeches with summaries focused on "
        f"what each official is **worried about** vs **sanguine about**. "
        f"{len(records)} speeches · 🦅 {tally['hawkish']} hawkish · "
        f"🕊️ {tally['dovish']} dovish · ➖ {tally['neutral']} neutral.",
        "",
        "_Generated from `data/fed_speeches.db`. Full text + structured fields are "
        "queryable there (e.g. `SELECT speaker, summary FROM speeches WHERE "
        "stance='hawkish'`)._",
        "",
        "---",
        "",
    ]
    for r in records:
        date = r.get("speech_date") or "—"
        speaker = r.get("speaker") or "Unknown speaker"
        title = r.get("title") or "(untitled)"
        badge = _STANCE_BADGE.get(r.get("stance", "neutral"), _STANCE_BADGE["neutral"])
        url = r.get("url", "")
        venue = r.get("venue") or ""
        source = r.get("source") or ""
        lines.append(f"## {date} — {speaker}: {title}")
        meta = " · ".join(
            x for x in [badge, f"_{venue}_" if venue else "", source] if x
        )
        if url:
            meta += f" · [source]({url})"
        lines.append(meta)
        lines.append("")
        if r.get("summary"):
            lines.append(r["summary"])
            lines.append("")
        worried = r.get("worried_about") or []
        sanguine = r.get("sanguine_about") or []
        if worried:
            lines.append("**Worried about:** " + "; ".join(worried))
        if sanguine:
            lines.append("**Sanguine about:** " + "; ".join(sanguine))
        if worried or sanguine:
            lines.append("")
        full = (r.get("full_text") or "").strip()
        if full:
            lines.append("<details><summary>Full transcript</summary>")
            lines.append("")
            lines.append(full)
            lines.append("")
            lines.append("</details>")
        lines.append("")
        lines.append("---")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out
