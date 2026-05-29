"""Tests for the heartbeat state collector + Block Kit builder."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from macro_monitor.posts_ledger import PostsLedger
from macro_monitor.schedulers.heartbeat import (
    HeartbeatState,
    build_heartbeat_blocks,
    collect_state,
)


def test_collect_state_with_empty_ledger(tmp_path: Path):
    """Heartbeat works even when nothing has been posted yet — the first
    run of a fresh deploy should still send a clean 'UP' ping."""
    db = tmp_path / "empty.db"
    PostsLedger(db).close()  # creates schema, no rows
    state = collect_state(families={}, db_path=db)
    assert state.posts_total == 0
    assert state.last_post_ts_utc is None
    assert state.families_tracked == 0
    assert state.stale_families == []


def test_collect_state_reads_most_recent_post(tmp_path: Path):
    db = tmp_path / "posts.db"
    ledger = PostsLedger(db)
    ledger.record_post(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.78},
        component_values={},
    )
    ledger.record_post(
        family_id="payrolls",
        period="2026-04",
        headline_values={"PAYEMS": 175},
        component_values={},
    )
    ledger.close()

    state = collect_state(families={"a": None, "b": None, "c": None}, db_path=db)
    assert state.posts_total == 2
    assert state.last_post_family_id == "payrolls"
    assert state.last_post_period == "2026-04"
    assert state.families_tracked == 3


def test_build_heartbeat_blocks_renders_text_fallback_and_blocks():
    state = HeartbeatState(
        posts_total=9,
        families_tracked=11,
        last_post_ts_utc="2026-05-28T19:05:00+00:00",
        last_post_family_id="eci",
        last_post_period="2026-Q1",
        stale_families=[],
        outputs_total=9,
    )
    text, blocks = build_heartbeat_blocks(state)
    assert "macro-monitor" in text
    assert "eci" in text
    assert "2026-Q1" in text
    assert blocks  # non-empty
    assert blocks[0]["type"] == "section"
    assert blocks[0]["text"]["type"] == "mrkdwn"


def test_build_heartbeat_blocks_flags_stale_families():
    state = HeartbeatState(
        posts_total=5,
        families_tracked=9,
        last_post_ts_utc=None,
        last_post_family_id=None,
        last_post_period=None,
        stale_families=["cpi", "payrolls"],
        outputs_total=9,
    )
    text, blocks = build_heartbeat_blocks(state)
    assert "stale" in text
    # The stale list should appear in the formatted block
    rendered = blocks[0]["text"]["text"]
    assert "cpi" in rendered and "payrolls" in rendered
