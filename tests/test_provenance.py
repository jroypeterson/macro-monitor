"""Chart provenance footer: every macro chart states its data source and that
it's macro-monitor-rendered (not an agency PNG)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt

from macro_monitor.charts import timeseries
from macro_monitor.charts.timeseries import (
    _stamp_provenance,
    provenance_label,
    render_family_charts,
)


# --- provenance_label ----------------------------------------------------

def test_label_maps_agency_from_release_url():
    assert (
        provenance_label("fred", "https://www.bls.gov/news.release/cpi.pdf")
        == "Data: BLS via FRED · Chart by macro-monitor"
    )
    assert (
        provenance_label("fred", "https://www.bea.gov/data/gdp")
        == "Data: BEA via FRED · Chart by macro-monitor"
    )


def test_label_without_agency_url():
    assert provenance_label("fred", None) == "Data: FRED · Chart by macro-monitor"


def test_label_unknown_agency_domain_falls_back_to_source():
    # Unrecognized publisher domain -> just name the data provider, no guess.
    assert (
        provenance_label("fred", "https://example.com/whatever")
        == "Data: FRED · Chart by macro-monitor"
    )


def test_label_non_fred_source():
    assert provenance_label("yf", None) == "Data: Yahoo Finance · Chart by macro-monitor"
    assert provenance_label("", None) == "Data: SOURCE · Chart by macro-monitor"


def test_label_subdomain_agency_match():
    assert (
        provenance_label("fred", "https://data.census.gov/x")
        == "Data: Census Bureau via FRED · Chart by macro-monitor"
    )


# --- _stamp_provenance ---------------------------------------------------

def test_stamp_adds_footer_text():
    fig = plt.figure()
    _stamp_provenance(fig, "Data: BLS via FRED · Chart by macro-monitor")
    assert any("Chart by macro-monitor" in t.get_text() for t in fig.texts)
    plt.close(fig)


def test_stamp_none_adds_nothing():
    fig = plt.figure()
    _stamp_provenance(fig, None)
    assert not fig.texts
    plt.close(fig)


# --- threading through render_family_charts ------------------------------

def test_render_family_charts_threads_provenance(monkeypatch, tmp_path):
    captured = []

    def _fake_render(**kwargs):
        captured.append(kwargs.get("provenance"))
        return Path(kwargs["output_path"])

    monkeypatch.setattr(timeseries, "render_chart", _fake_render)

    main = SimpleNamespace(filename="main_{period}.png")
    thread = [SimpleNamespace(filename="t_{period}.png", name="thread1")]
    bundle = SimpleNamespace(main=main, thread=thread)

    render_family_charts(
        family_charts=bundle,
        fetched_series={},
        target_period=None,
        period_key="2026-05",
        output_dir=tmp_path,
        family_display_name="CPI",
        period_label="May 2026",
        provenance="Data: BLS via FRED · Chart by macro-monitor",
    )
    # Both main + thread charts received the provenance string.
    assert captured == [
        "Data: BLS via FRED · Chart by macro-monitor",
        "Data: BLS via FRED · Chart by macro-monitor",
    ]
