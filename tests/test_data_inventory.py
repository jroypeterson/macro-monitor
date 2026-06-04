"""Tests for the macro data inventory: the seed YAML must stay schema-valid and the
renderer must produce a non-empty markdown table. The inventory is a hand-maintained
catalog, so a structural check guards against a typo silently dropping a field.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from macro_monitor.data_inventory.render import render

_YAML = Path(__file__).parent.parent / "data_inventory" / "datasets.yaml"

# Required on every entry per data_inventory/SCHEMA.md.
_REQUIRED = ["id", "name", "publisher", "publisher_type", "category", "url",
             "access", "cadence", "lag", "coverage", "relevance", "status",
             "last_inventoried"]
_VALID_STATUS = {"in_charts", "shipped", "staged", "candidate", "rejected", "not_evaluated"}
_VALID_ACCESS_METHOD = {"fred", "bea_api", "bls_api", "csv_download", "excel_download",
                        "html_scrape", "rest_api", "manual_download", "paid"}


def _load() -> list[dict]:
    data = yaml.safe_load(_YAML.read_text(encoding="utf-8")) or {}
    return data.get("datasets", [])


def test_yaml_parses_and_is_nonempty():
    rows = _load()
    assert len(rows) >= 18, "Ahead-of-the-Curve seed should hold ~21 series"


def test_every_entry_has_required_fields():
    for r in _load():
        missing = [f for f in _REQUIRED if f not in r or r[f] in (None, "", [])]
        assert not missing, f"{r.get('id', '?')} missing required fields: {missing}"


def test_ids_are_unique():
    ids = [r["id"] for r in _load()]
    assert len(ids) == len(set(ids)), "duplicate dataset ids"


def test_status_and_access_method_are_valid():
    for r in _load():
        assert r["status"] in _VALID_STATUS, f"{r['id']}: bad status {r['status']!r}"
        method = (r.get("access") or {}).get("method")
        assert method in _VALID_ACCESS_METHOD, f"{r['id']}: bad access method {method!r}"


def test_staged_entries_have_gaps():
    # SCHEMA.md: gaps required once status is staged or live.
    for r in _load():
        if r["status"] in ("staged", "in_charts", "shipped"):
            assert r.get("gaps"), f"{r['id']}: staged/live entry must document gaps"


def test_fred_entries_carry_a_series_id_detail():
    for r in _load():
        acc = r.get("access") or {}
        if acc.get("method") == "fred":
            assert acc.get("detail"), f"{r['id']}: fred access must name the series id"


def test_render_writes_nonempty_markdown(tmp_path):
    out = render(yaml_path=_YAML, out_path=tmp_path / "out.md")
    text = out.read_text(encoding="utf-8")
    assert "# Macro Data Inventory" in text
    assert "PCEC96" in text, "real PCE (the leading indicator) must appear in the table"
    assert text.count("|") > 50, "expected a populated markdown table"
