"""Tests for the top-down market dataset catalog (no network)."""
from __future__ import annotations

from macro_monitor.market.sources import DATASETS


def test_catalog_has_three_sources():
    sources = {d["source"] for d in DATASETS}
    assert {"Ken French", "AQR", "Robert Shiller"} <= sources


def test_records_are_complete_and_unique():
    ids = [d["id"] for d in DATASETS]
    assert len(ids) == len(set(ids)), "ids must be unique"
    for d in DATASETS:
        for field in ("id", "source", "name", "period", "url", "file", "what", "use", "relevance"):
            assert d.get(field), f"{d['id']} missing {field}"
        assert d["url"].endswith((".zip", ".xls", ".xlsx")), d["id"]


def test_marquee_datasets_present():
    ids = {d["id"] for d in DATASETS}
    assert "shiller_cape" in ids        # CAPE / long-run valuation
    assert "ff_3factor_monthly" in ids  # Fama-French backbone
    assert "aqr_century" in ids         # century of factor premia
