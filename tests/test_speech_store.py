"""Tests for the queryable Fed-speech archive + readable-library export."""

from __future__ import annotations

from macro_monitor.schedulers.speech_store import (
    SpeechRecord,
    SpeechStore,
    export_markdown,
)


def _rec(url: str, speaker: str = "Waller", stance: str = "hawkish",
         date: str = "2026-05-22", worried=("inflation",),
         body: str = "full transcript body") -> SpeechRecord:
    return SpeechRecord(
        url=url, speaker=speaker, venue="Econ Club", title=f"{speaker} speech",
        source="Federal Reserve — Speeches", speech_date=date, stance=stance,
        summary="A summary.", worried_about=tuple(worried),
        sanguine_about=("jobs",), drivers=("d",), full_text=body,
    )


def test_upsert_and_has_and_count(tmp_path):
    with SpeechStore(tmp_path / "s.db") as store:
        assert store.count() == 0
        store.upsert(_rec("u1"))
        assert store.has("u1") and store.count() == 1
        # Upsert same url -> replace, not duplicate.
        store.upsert(_rec("u1", stance="dovish"))
        assert store.count() == 1
        assert store.search(stance="dovish")[0]["url"] == "u1"


def test_all_records_newest_first_blank_dates_last(tmp_path):
    with SpeechStore(tmp_path / "s.db") as store:
        store.upsert(_rec("old", date="2026-01-01"))
        store.upsert(_rec("new", date="2026-06-01"))
        store.upsert(_rec("undated", date=""))
        order = [r["url"] for r in store.all_records()]
        assert order[0] == "new" and order[1] == "old" and order[-1] == "undated"


def test_search_by_speaker_stance_text(tmp_path):
    with SpeechStore(tmp_path / "s.db") as store:
        store.upsert(_rec("u1", speaker="Waller", stance="hawkish",
                          worried=("sticky services inflation",)))
        store.upsert(_rec("u2", speaker="Bowman", stance="dovish",
                          worried=("labor softening",), body="dovish remarks"))
        assert {r["url"] for r in store.search(speaker="waller")} == {"u1"}
        assert {r["url"] for r in store.search(stance="dovish")} == {"u2"}
        # free-text hits the worried_about JSON + full_text.
        assert {r["url"] for r in store.search(text="sticky services")} == {"u1"}
        assert {r["url"] for r in store.search(text="dovish remarks")} == {"u2"}


def test_json_fields_roundtrip_as_lists(tmp_path):
    with SpeechStore(tmp_path / "s.db") as store:
        store.upsert(_rec("u1", worried=("a", "b")))
        r = store.all_records()[0]
        assert r["worried_about"] == ["a", "b"]
        assert r["sanguine_about"] == ["jobs"]


def test_audience_roundtrips(tmp_path):
    with SpeechStore(tmp_path / "s.db") as store:
        store.upsert(SpeechRecord(url="u1", speaker="W",
                                  audience="academic / university", stance="neutral"))
        assert store.all_records()[0]["audience"] == "academic / university"


def test_migration_adds_audience_to_v1_db(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.execute(
        "CREATE TABLE speeches (url TEXT PRIMARY KEY, speaker TEXT, venue TEXT, "
        "title TEXT, source TEXT, speech_date TEXT, stance TEXT, summary TEXT, "
        "worried_about TEXT, sanguine_about TEXT, drivers TEXT, full_text TEXT, "
        "archived_at TEXT)"
    )
    c.execute("INSERT INTO speeches (url, speaker, stance) VALUES ('u1','W','neutral')")
    c.commit()
    c.close()
    with SpeechStore(p) as store:  # __init__ migrates
        cols = {r[1] for r in store.conn.execute("PRAGMA table_info(speeches)")}
        assert "audience" in cols
        store.upsert(SpeechRecord(url="u1", speaker="W", audience="testimony", stance="hawkish"))
        assert store.all_records()[0]["audience"] == "testimony"


def test_speaker_timeline_and_prior_speech(tmp_path):
    with SpeechStore(tmp_path / "s.db") as store:
        store.upsert(SpeechRecord(url="u1", speaker="Christopher Waller",
                                  speech_date="2026-01-10", stance="dovish"))
        store.upsert(SpeechRecord(url="u2", speaker="Christopher Waller",
                                  speech_date="2026-05-10", stance="hawkish"))
        store.upsert(SpeechRecord(url="u3", speaker="Lisa Cook",
                                  speech_date="2026-03-01", stance="neutral"))
        tl = store.speaker_timeline("waller")          # surname substring, oldest→newest
        assert [r["url"] for r in tl] == ["u1", "u2"]
        assert store.prior_speech("Christopher Waller", "2026-05-10")["url"] == "u1"
        assert store.prior_speech("Christopher Waller", "2026-01-10") is None
        tl2 = store.speaker_timeline("waller", since="2026-02-01")
        assert [r["url"] for r in tl2] == ["u2"]


def test_export_markdown_writes_library(tmp_path):
    with SpeechStore(tmp_path / "s.db") as store:
        store.upsert(_rec("u1", speaker="Waller"))
        store.upsert(_rec("u2", speaker="Bowman", stance="neutral"))
        records = store.all_records()
    out = tmp_path / "fed_speeches.md"
    path = export_markdown(records, out)
    text = path.read_text(encoding="utf-8")
    assert "# Fed Speech Library" in text
    assert "Waller" in text and "Bowman" in text
    assert "Worried about:" in text
    assert "<details><summary>Full transcript</summary>" in text
    assert "full transcript body" in text
    # stance tally in the header
    assert "hawkish" in text and "neutral" in text
