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


def test_no_headline_is_a_bare_level():
    """Every raw/level headline must carry a rate-of-change `also_display`
    (YoY/MoM/pp context) so the channel never shows a bare level — except GDP,
    whose `raw` series IS the QoQ-SAAR growth rate (already a rate of change)."""
    cfg = load_config(default_config_path())
    offenders = []
    for fid, fam in cfg.items():
        for h in fam.headline:
            if h.primary_transform == "raw" and not h.also_display and fid != "gdp":
                offenders.append(f"{fam.display_name}/{h.label}")
    assert offenders == [], f"bare-level headlines (need also_display): {offenders}"


def test_default_config_loads_and_validates():
    cfg = load_config(default_config_path())
    assert "cpi" in cfg
    validate_all_or_raise(cfg)


def test_consumer_credit_delinquency_family_wired():
    cfg = load_config(default_config_path())
    fam = cfg["consumer_credit_delinquency"]
    assert fam.cadence == "quarterly"
    assert fam.release_calendar_id == 231          # FRB Charge-Off & Delinquency
    assert fam.group == "Consumer"
    assert fam.headline[0].id == "DRCCLACBS"
    assert "yoy_chg" in fam.headline[0].also_display  # pp change context
    ids = {c.id for c in fam.components}
    assert {"DRCLACBS", "DRSFRMACBS", "DRALACBS"} <= ids


def test_consumer_families_carry_group():
    cfg = load_config(default_config_path())
    for key in ["pce", "retail_sales", "consumer_credit", "umich",
                "mortgage_rates", "existing_home_sales", "new_home_sales",
                "consumer_credit_delinquency"]:
        assert cfg[key].group == "Consumer", key


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


def test_tier_a_mandated_topic_families_are_tier_a():
    """Families covering consumer spending, employment, or real hourly
    earnings must always be Tier A (post unconditionally). Lock the
    data-driven mandate: every family tagged with such a topic is tier A."""
    from macro_monitor.config import TIER_A_MANDATED_TOPICS

    cfg = load_config(default_config_path())
    mandated = [
        (fid, f)
        for fid, f in cfg.items()
        if set(f.topics) & TIER_A_MANDATED_TOPICS
    ]
    assert mandated, "expected at least one Tier-A-mandated family"
    for fid, f in mandated:
        assert f.tier == "A", f"{fid} covers {f.topics} but is tier {f.tier}"

    # The canonical consumer-spending + employment + real-hourly-earnings
    # families specifically.
    assert "consumer_spending" in cfg["pce"].topics
    assert "consumer_spending" in cfg["retail_sales"].topics
    assert "employment" in cfg["payrolls"].topics
    assert "real_hourly_earnings" in cfg["payrolls"].topics


def test_validator_rejects_mandated_topic_on_tier_b(tmp_path: Path):
    """A family declaring a Tier-A-mandated topic but set to tier B must
    fail validation — the mandate is enforced, not advisory."""
    cfg = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
    # housing is Tier B; mislabel it as covering consumer spending.
    cfg["families"]["housing"]["topics"] = ["consumer_spending"]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    families = load_config(path)
    errors = validate_family(families["housing"])
    assert any("consumer_spending" in e and "tier A" in e for e in errors)


def test_validator_rejects_unknown_topic(tmp_path: Path):
    cfg = yaml.safe_load(default_config_path().read_text(encoding="utf-8"))
    cfg["families"]["cpi"]["topics"] = ["bogus_topic"]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(Exception):  # field_validator rejects at load time
        load_config(path)


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
