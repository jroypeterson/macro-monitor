"""International macro — offline parser/config/digest tests.

Parsers are exercised against captured response *shapes* (no network) via a
fake session, so the SDMX/JSON-stat/ONS/BoE dialect handling is locked in.
"""

from __future__ import annotations

import json

import pytest

from macro_monitor.international.config import (
    IntlSeriesSpec,
    load_series,
    validate_series_or_raise,
)
from macro_monitor.international.format import fmt_change, fmt_period, fmt_value
from macro_monitor.international.model import IntlObservation, IntlSeriesResult
from macro_monitor.international.sources import boe, jsonstat, ons, sdmx


class _FakeResp:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _FakeSession:
    """Returns a queued response regardless of URL (single-call fetchers)."""

    def __init__(self, payload=None, text=""):
        self._resp = _FakeResp(payload, text)

    def get(self, url, params=None, headers=None, timeout=None):
        return self._resp


def _spec(source, **params):
    return IntlSeriesSpec(
        id="t", region="eurozone", indicator="cpi_yoy", label="t",
        source=source, params=params,
    )


# ───────────────────────── config ──────────────────────────

def test_default_series_config_loads_and_validates():
    specs = load_series()
    validate_series_or_raise(specs)
    assert any(s.region == "china" for s in specs)
    assert {s.region for s in specs} == {"eurozone", "uk", "china", "japan"}


def test_validate_rejects_unknown_source_and_dupes():
    bad = [
        IntlSeriesSpec(id="a", region="uk", indicator="cpi_yoy", label="x",
                       source="bogus", params={"x": 1}),
        IntlSeriesSpec(id="a", region="uk", indicator="cpi_yoy", label="x",
                       source="ons", params={"url": "u"}),
    ]
    with pytest.raises(ValueError) as e:
        validate_series_or_raise(bad)
    assert "bogus" in str(e.value) and "duplicate" in str(e.value)


# ───────────────────────── parsers ─────────────────────────

def test_eurostat_jsonstat_parser():
    payload = {
        "id": ["freq", "unit", "coicop", "geo", "time"],
        "size": [1, 1, 1, 1, 3],
        "value": {"0": 2.2, "1": 2.1, "2": 2.0},
        "dimension": {"time": {"category": {"index": {"2025-10": 0, "2025-11": 1, "2025-12": 2}}}},
    }
    obs = jsonstat.fetch_eurostat(_spec("eurostat", dataset="prc_hicp_manr"),
                                  session=_FakeSession(payload))
    assert obs[-1] == IntlObservation("2025-12", 2.0)
    assert [o.period for o in obs] == ["2025-10", "2025-11", "2025-12"]


def test_ecb_sdmx_parser():
    payload = {
        "dataSets": [{"series": {"0:0:0": {"observations": {"0": [2.65], "1": [2.4], "2": [2.15]}}}}],
        "structure": {"dimensions": {"observation": [
            {"id": "TIME_PERIOD", "values": [
                {"id": "2025-03-12"}, {"id": "2025-04-23"}, {"id": "2025-06-11"}]}]}},
    }
    obs = sdmx.fetch_ecb(_spec("ecb", flow="FM", key="K"), session=_FakeSession(payload))
    assert obs[-1] == IntlObservation("2025-06-11", 2.15)


def test_oecd_sdmx_parser_picks_time_dimension():
    payload = {"data": {
        "dataSets": [{"observations": {
            "0:0:0:0:0:0:0:0:0": [0.7], "0:0:0:0:0:0:0:0:1": [0.8], "0:0:0:0:0:0:0:0:2": [1.2]}}],
        "structures": [{"dimensions": {"observation": [
            {"id": "REF_AREA", "values": [{"id": "CHN"}]},
            {"id": "TIME_PERIOD", "values": [
                {"id": "2026-02"}, {"id": "2026-03"}, {"id": "2026-04"}]}]}}],
    }}
    # TIME_PERIOD is the LAST observation dim (index 8 in the key here).
    payload["data"]["structures"][0]["dimensions"]["observation"] = (
        [{"id": f"D{i}", "values": [{"id": "_"}]} for i in range(8)]
        + [{"id": "TIME_PERIOD", "values": [{"id": "2026-02"}, {"id": "2026-03"}, {"id": "2026-04"}]}]
    )
    obs = sdmx.fetch_oecd(_spec("oecd", flow="F", key="K"), session=_FakeSession(payload))
    assert obs[-1] == IntlObservation("2026-04", 1.2)


def test_ons_parser_normalizes_month_labels():
    payload = {"months": [
        {"date": "2026 FEB", "value": "3.0"},
        {"date": "2026 MAR", "value": "3.3"},
        {"date": "2026 APR", "value": "2.8"}]}
    obs = ons.fetch_ons(_spec("ons", url="u"), session=_FakeSession(payload))
    assert obs[-1] == IntlObservation("2026-04", 2.8)


def test_boe_csv_collapses_unchanged_runs():
    csv_text = "DATE,IUDBEDR\n02 Jan 2025,4.75\n03 Jan 2025,4.75\n07 Feb 2025,4.50\n18 Dec 2025,3.75\n"
    obs = boe.fetch_boe(_spec("boe", series="IUDBEDR"), session=_FakeSession(text=csv_text))
    # Daily-carried duplicates collapse to the change points only.
    assert [(o.period, o.value) for o in obs] == [
        ("2025-01-02", 4.75), ("2025-02-07", 4.50), ("2025-12-18", 3.75)]


# ───────────────────────── format + model ──────────────────

def test_fmt_period_variants():
    assert fmt_period("2025-12") == "Dec 2025"
    assert fmt_period("2026-Q1") == "Q1 2026"
    assert fmt_period("2026") == "2026"


def test_result_change_and_formatting():
    r = IntlSeriesResult(
        spec_id="t", region="uk", indicator="cpi_yoy", label="CPI", unit="%",
        source="ons", freq="monthly", decimals=1,
        observations=[IntlObservation("2026-03", 3.3), IntlObservation("2026-04", 2.8)],
    )
    assert r.ok and r.latest.value == 2.8
    assert fmt_value(r) == "2.8%"
    assert fmt_change(r) == "▼0.5"
