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

def test_apply_yoy_matches_same_period_prior_year():
    from macro_monitor.international.collect import apply_yoy
    # 13 monthly index points; YoY defined only once we have a year-back match.
    obs = [IntlObservation(f"2025-{m:02d}", 100.0 + m) for m in range(1, 13)]
    obs.append(IntlObservation("2026-01", 111.1))  # vs 2025-01 = 101.0
    out = apply_yoy(obs)
    assert out[-1].period == "2026-01"
    assert round(out[-1].value, 2) == round((111.1 / 101.0 - 1) * 100, 2)
    # No spurious YoY for periods lacking a prior-year base.
    assert all(o.period == "2026-01" for o in out)


def test_ytd_change_bps_anchors_on_prior_year_end():
    from macro_monitor.international.format import fmt_bps, ytd_change_bps
    r = IntlSeriesResult(
        spec_id="y", region="uk", indicator="yield_10y", label="10Y", unit="%",
        source="boe", freq="daily", decimals=2,
        observations=[
            IntlObservation("2025-12-30", 4.46),  # prior-year-end anchor
            IntlObservation("2026-01-02", 4.50),
            IntlObservation("2026-06-03", 4.83),
        ],
    )
    bps = ytd_change_bps(r)
    assert round(bps) == 37  # (4.83 - 4.46) * 100
    assert fmt_bps(bps) == "+37bps"
    # No prior-year point -> None.
    r2 = IntlSeriesResult(
        spec_id="y2", region="uk", indicator="yield_10y", label="10Y", unit="%",
        source="boe", freq="daily", observations=[IntlObservation("2026-01-02", 4.5)],
    )
    assert ytd_change_bps(r2) is None


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


# ---- 2026-11-12: dated change, stale flag, China yields -------------------

def _res(periods_values, *, indicator="cpi_yoy", freq="monthly", unit="%", decimals=1):
    from macro_monitor.international.model import IntlObservation, IntlSeriesResult

    return IntlSeriesResult(
        spec_id="x", region="eurozone", indicator=indicator, label="X", unit=unit,
        source="eurostat", freq=freq, decimals=decimals,
        observations=[IntlObservation(p, v) for p, v in periods_values],
    )


def test_change_names_its_unit_and_what_it_is_measured_against():
    from macro_monitor.international.format import fmt_change_vs

    assert fmt_change_vs(_res([("2025-11", 2.1), ("2025-12", 2.0)])) == "▼0.1 pt vs Nov 2025"
    # An index has no percentage points.
    assert fmt_change_vs(_res([("2026-09", 100.1), ("2026-10", 100.3)], unit="")) == "▲0.2 vs Sep 2026"
    assert fmt_change_vs(_res([("2026-09", 2.5), ("2026-10", 2.5)])) == "unchanged vs Sep 2026"
    assert fmt_change_vs(_res([("2026-10", 2.5)])) == ""


def test_stale_flag_fires_on_the_frozen_eurostat_reading_and_not_on_normal_lags():
    """The production shape: prc_hicp_manr answered Dec 2025 on 2026-11-12."""
    from macro_monitor.international.format import is_stale

    today = "2026-11-12"
    assert is_stale(_res([("2025-11", 2.1), ("2025-12", 2.0)]), today)
    assert not is_stale(_res([("2026-06", 4.9), ("2026-07", 4.7)]), today)  # UK unemployment lag
    assert not is_stale(_res([("2026-Q1", 0.8), ("2026-Q2", 1.4)], freq="quarterly"), today)
    assert is_stale(_res([("2025-Q3", 0.8), ("2025-Q4", 1.4)], freq="quarterly"), today)
    assert is_stale(_res([("2026-08-03", 5.0)], indicator="yield_10y", freq="daily"), today)
    # A policy rate that has not MOVED since 2025 is not a dead feed.
    assert not is_stale(
        _res([("2025-06-11", 2.15), ("2025-12-18", 2.4)], indicator="policy_rate", freq="daily"),
        today,
    )


def test_digest_lines_say_period_base_and_staleness():
    from macro_monitor.international.digest import build_digest_blocks

    rate = _res([("2026-06-17", 2.4), ("2026-09-16", 2.65)],
                indicator="policy_rate", freq="daily", decimals=2)
    frozen = _res([("2025-11", 2.1), ("2025-12", 2.0)])
    _, blocks = build_digest_blocks([frozen, rate], as_of="2026-11-12")
    body = "\n".join(b["text"]["text"] for b in blocks if b["type"] == "section")
    assert "*2.0%* in Dec 2025 · _▼0.1 pt vs Nov 2025_ · ⚠️ _stale" in body
    assert "*2.65%*, last changed Sep 2026 _(▲0.25 pt)_" in body
    _, fresh = build_digest_blocks([frozen], as_of="2026-01-20")
    assert "stale" not in "\n".join(b["text"]["text"] for b in fresh if b["type"] == "section")


def test_eurozone_inflation_reads_the_live_eurostat_dataset():
    from macro_monitor.international.config import load_series

    by = {s.id: s for s in load_series()}
    for sid in ("ez_cpi", "ez_core_cpi"):
        assert by[sid].params["dataset"] == "prc_hicp_minr", "prc_hicp_manr was retired Feb 2026"
        assert by[sid].params["filters"]["unit"] == "RCH_A"


def test_chinamoney_curve_parser_picks_the_maturity():
    import pytest
    from macro_monitor.international.sources.base import SourceError
    from macro_monitor.international.sources.chinamoney import parse_curve

    payload = {"records": [
        {"newDateValueCN": "2026-11-12", "yearTermStr": "1.0", "maturityYieldStr": "1.1788"},
        {"newDateValueCN": "2026-11-12", "yearTermStr": "2.0", "maturityYieldStr": "1.2261"},
        {"newDateValueCN": "2026-11-12", "yearTermStr": "10.0", "maturityYieldStr": "1.6039"},
        {"newDateValueCN": "2026-11-12", "yearTermStr": "20.0", "maturityYieldStr": "---"},
    ]}
    (obs,) = parse_curve(payload, 10.0, "cn_yield_10y")
    assert (obs.period, obs.value) == ("2026-11-12", 1.6039)
    assert parse_curve(payload, 2.0, "cn_yield_2y")[0].value == 1.2261
    with pytest.raises(SourceError):
        parse_curve(payload, 20.0, "x")
    with pytest.raises(SourceError):
        parse_curve({}, 10.0, "x")
