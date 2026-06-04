"""Tests for the config loader + validator.

Validator is the v1 hard guard against silent typos that would otherwise
show up on a live release morning.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from macro_monitor.config import (
    FamilyConfig,
    calendar_families,
    default_config_path,
    load_config,
    validate_all_or_raise,
    validate_family,
)


def test_default_config_loads_and_validates():
    cfg = load_config(default_config_path())
    assert "cpi" in cfg
    validate_all_or_raise(cfg)


def test_validator_catches_dedupe_referring_to_undeclared_series(tmp_path: Path):
    cfg = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
    cfg["families"]["cpi"]["dedupe"]["headline_hash"].append("BOGUS_SERIES")
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    families = load_config(path)
    errors = validate_family(families["cpi"])
    assert any("BOGUS_SERIES" in e for e in errors)


def test_validator_catches_chart_series_not_declared(tmp_path: Path):
    cfg = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
    cfg["families"]["cpi"]["charts"]["main"]["series"].append(
        {"id": "GHOST_SERIES", "transform": "yoy_pct", "label": "Ghost"}
    )
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    families = load_config(path)
    errors = validate_family(families["cpi"])
    assert any("GHOST_SERIES" in e for e in errors)


def test_validator_catches_unknown_transform_at_load_time(tmp_path: Path):
    cfg = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
    cfg["families"]["cpi"]["headline"][0]["primary_transform"] = "wibble"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    # Pydantic catches this at model_validate; we don't even get to validate_family
    with pytest.raises(Exception):
        load_config(path)


def test_validator_requires_release_calendar_id_for_numeric(tmp_path: Path):
    cfg = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
    cfg["families"]["cpi"]["release_calendar_id"] = None
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    families = load_config(path)
    errors = validate_family(families["cpi"])
    assert any("release_calendar_id" in e for e in errors)


def test_validator_rejects_tier_b_gate_on_tier_a(tmp_path: Path):
    cfg = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
    cfg["families"]["cpi"]["tier_b_gate"] = {
        "threshold": 1.0,
        "vs": "trailing_5y_volatility",
    }
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    families = load_config(path)
    errors = validate_family(families["cpi"])
    assert any("tier A" in e.lower() or "tier_b_gate" in e for e in errors)


def test_calendar_families_is_shared_scope_for_both_surfaces():
    """The Google Calendar backfill and the annual HTML grid must draw
    from the same family set, or they silently diverge (the bug that left
    the HTML showing only Tier A while the calendar carried all tiers).

    Lock the contract: calendar_families == every family with a
    release_calendar_id, all tiers, and route both surfaces through it.
    """
    cfg = load_config(default_config_path())
    cal = calendar_families(cfg)

    # Exactly the families that have a FRED release calendar id.
    expected = {fid for fid, f in cfg.items() if f.release_calendar_id is not None}
    assert set(cal) == expected
    assert cal, "expected at least one calendar family in the default config"

    # Tier is deliberately NOT filtered — both A and B must be present so
    # the two surfaces stay comprehensive together.
    tiers = {f.tier for f in cal.values()}
    assert "A" in tiers and "B" in tiers


def test_calendar_families_excludes_families_without_release_id(tmp_path: Path):
    cfg = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
    cfg["families"]["umich"]["release_calendar_id"] = None
    path = tmp_path / "no_umich_cal.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    families = load_config(path)
    assert "umich" not in calendar_families(families)


def test_validator_rejects_event_family_without_federal_reserve_source(tmp_path: Path):
    cfg = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
    cpi = cfg["families"]["cpi"]
    cpi["family_type"] = "event"
    cpi["source"] = "fred"  # Wrong for an event family
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    families = load_config(path)
    errors = validate_family(families["cpi"])
    assert any("federal_reserve" in e for e in errors)
