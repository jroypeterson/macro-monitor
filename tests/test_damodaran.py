"""Tests for the Damodaran dataset catalog + inventory render (no network)."""
from __future__ import annotations

from macro_monitor.damodaran.datasets import REGIONS, all_datasets
from macro_monitor.damodaran.render import render


def test_catalog_expands_and_is_unique():
    recs = all_datasets()
    assert len(recs) > 150, "standalone + ~25 families x 8 regions"
    ids = [r["id"] for r in recs]
    assert len(ids) == len(set(ids)), "dataset ids must be unique"


def test_every_record_has_url_and_file():
    for r in all_datasets():
        assert r["url"].startswith("https://pages.stern.nyu.edu/"), r["id"]
        assert r["url"].endswith((".xls", ".xlsx")), r["id"]
        assert r["file"]


def test_known_marquee_urls():
    recs = {r["id"]: r for r in all_datasets()}
    assert recs["histretSP"]["url"].endswith("/datasets/histretSP.xls")
    assert recs["histimpl"]["timeseries"] is True
    # US PE file is pedata.xls but the European one uses the pe stem.
    assert recs["pe_US"]["file"] == "pedata.xls"
    assert recs["pe_Europe"]["file"] == "peEurope.xls"
    # betas family: US "betas.xls" but regional stem is "beta".
    assert recs["betas_US"]["file"] == "betas.xls"
    assert recs["betas_Japan"]["file"] == "betaJapan.xls"


def test_rd_family_url_encodes_ampersand():
    recs = {r["id"]: r for r in all_datasets()}
    # R&D filenames contain "&", which must be percent-encoded in the URL.
    assert "R%26D" in recs["margin_rd_US"]["url"]


def test_all_regions_present_per_family():
    recs = all_datasets()
    pe = [r for r in recs if r["family"] == "pe"]
    assert len(pe) == len(REGIONS)


def test_render_writes_inventory(tmp_path):
    out = render(out_path=tmp_path / "inv.md")
    text = out.read_text(encoding="utf-8")
    assert "Aswath Damodaran" in text
    assert "Valuation multiples" in text
    assert "Equity risk premium" in text
