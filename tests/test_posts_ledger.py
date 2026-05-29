"""Tests for the posts ledger. The dedupe + revision logic is the second-
highest-risk-of-silent-bug area after transforms — silent misfires here
would either spam Slack or suppress real revisions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from macro_monitor.posts_ledger import (
    DiffResult,
    PostDecision,
    PostsLedger,
    hash_values,
)


def test_hash_values_is_stable_across_dict_orderings():
    a = hash_values({"CPIAUCSL": 3.78, "CPILFESL": 2.74})
    b = hash_values({"CPILFESL": 2.74, "CPIAUCSL": 3.78})
    assert a == b


def test_hash_values_rounds_floats_for_stability():
    # 6-decimal rounding — small float-printing differences shouldn't trigger
    # spurious revisions.
    a = hash_values({"X": 3.123456})
    b = hash_values({"X": 3.1234560000001})
    assert a == b


def test_hash_values_detects_real_value_change():
    a = hash_values({"X": 3.12})
    b = hash_values({"X": 3.13})
    assert a != b


def test_new_period_is_new_period(tmp_path: Path):
    ledger = PostsLedger(tmp_path / "test.db")
    result = ledger.check_and_record(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.78, "CPILFESL": 2.74},
        component_values={"Shelter": 3.29},
    )
    assert result.decision == PostDecision.NEW_PERIOD
    assert result.prior_entry is None
    assert result.revision_count == 0


def test_unchanged_repost_is_idempotent(tmp_path: Path):
    ledger = PostsLedger(tmp_path / "test.db")
    payload = dict(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.78, "CPILFESL": 2.74},
        component_values={"Shelter": 3.29},
    )
    first = ledger.check_and_record(**payload)
    assert first.decision == PostDecision.NEW_PERIOD

    second = ledger.check_and_record(**payload)
    assert second.decision == PostDecision.UNCHANGED


def test_headline_change_triggers_revised_headline(tmp_path: Path):
    ledger = PostsLedger(tmp_path / "test.db")
    ledger.check_and_record(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.78, "CPILFESL": 2.74},
        component_values={"Shelter": 3.29},
    )
    result = ledger.check_and_record(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.80, "CPILFESL": 2.74},  # +0.02
        component_values={"Shelter": 3.29},
    )
    assert result.decision == PostDecision.REVISED_HEADLINE
    assert result.revision_count == 1
    assert result.prior_entry is not None
    assert result.prior_entry.headline_values["CPIAUCSL"] == 3.78


def test_component_only_change_triggers_component_revision(tmp_path: Path):
    ledger = PostsLedger(tmp_path / "test.db")
    ledger.check_and_record(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.78, "CPILFESL": 2.74},
        component_values={"Shelter": 3.29, "Food": 3.22},
    )
    result = ledger.check_and_record(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.78, "CPILFESL": 2.74},
        component_values={"Shelter": 3.30, "Food": 3.22},  # Shelter revised
    )
    assert result.decision == PostDecision.REVISED_COMPONENT_ONLY


def test_headline_and_component_change_collapses_to_one_revised(tmp_path: Path):
    """Headline subsumes component — both changes in one fetch produce
    ONE REVISED top-level post, not a REVISED + thread-note pair."""
    ledger = PostsLedger(tmp_path / "test.db")
    ledger.check_and_record(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.78},
        component_values={"Shelter": 3.29},
    )
    result = ledger.check_and_record(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.80},      # headline changed
        component_values={"Shelter": 3.30},      # component also changed
    )
    assert result.decision == PostDecision.REVISED_HEADLINE  # subsumed


def test_changed_periods_in_batch_detects_benchmark_flood(tmp_path: Path):
    """If a fetch returns N >= 3 changed historical periods, the caller's
    flood guard fires and emits one summary post instead of N REVISED."""
    ledger = PostsLedger(tmp_path / "test.db")
    for month in ("01", "02", "03", "04"):
        ledger.check_and_record(
            family_id="payrolls",
            period=f"2025-{month}",
            headline_values={"PAYEMS": 150_000.0 + int(month)},
            component_values={},
        )

    candidates = {
        "2025-01": (
            "header_hash_NEW",
            "comp_hash_NEW",
        ),
        "2025-02": ("header_hash_NEW", "comp_hash_NEW"),
        "2025-03": ("header_hash_NEW", "comp_hash_NEW"),
        "2025-04": ("header_hash_NEW", "comp_hash_NEW"),
    }
    changed = ledger.changed_periods_in_batch("payrolls", candidates)
    assert sorted(changed) == ["2025-01", "2025-02", "2025-03", "2025-04"]


def test_changed_periods_in_batch_skips_unposted_periods(tmp_path: Path):
    """Periods never posted aren't "changes" in the benchmark-revision
    sense — they're new prints, handled by NEW_PERIOD on their own pass."""
    ledger = PostsLedger(tmp_path / "test.db")
    candidates = {
        "2025-01": ("h", "c"),
        "2025-02": ("h", "c"),
    }
    changed = ledger.changed_periods_in_batch("payrolls", candidates)
    assert changed == []


def test_revision_count_accumulates(tmp_path: Path):
    ledger = PostsLedger(tmp_path / "test.db")
    ledger.check_and_record(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.78},
        component_values={},
    )
    r2 = ledger.check_and_record(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.79},
        component_values={},
    )
    assert r2.revision_count == 1

    r3 = ledger.check_and_record(
        family_id="cpi",
        period="2026-04",
        headline_values={"CPIAUCSL": 3.80},
        component_values={},
    )
    assert r3.revision_count == 2
