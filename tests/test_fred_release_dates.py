"""Test FREDClient.get_initial_release_dates (ALFRED initial-release lookup)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from macro_monitor.collectors.fred import FREDClient, FREDError


class _Client(FREDClient):
    """FREDClient with __init__/_get stubbed so no key or network is needed."""

    def __init__(self, payload=None, raises=False):
        self._payload = payload
        self._raises = raises

    def _get(self, path, params):
        assert params.get("output_type") == "4"  # initial-release vintage
        if self._raises:
            raise FREDError("boom")
        return self._payload


def test_maps_period_to_initial_release_date():
    payload = {"observations": [
        {"date": "2026-03-01", "value": "752063.0", "realtime_start": "2026-04-21"},
        {"date": "2026-04-01", "value": "757085.0", "realtime_start": "2026-05-14"},
        {"date": "2026-05-01", "value": ".", "realtime_start": "2026-06-17"},  # missing value -> skip
    ]}
    out = _Client(payload).get_initial_release_dates("RSAFS")
    assert out[pd.Timestamp("2026-03-01")] == date(2026, 4, 21)
    assert out[pd.Timestamp("2026-04-01")] == date(2026, 5, 14)
    assert pd.Timestamp("2026-05-01") not in out  # '.' value dropped


def test_returns_empty_on_error():
    assert _Client(raises=True).get_initial_release_dates("X") == {}


def test_skips_rows_without_realtime_start():
    payload = {"observations": [
        {"date": "2026-04-01", "value": "1.0"},  # no realtime_start -> skip
    ]}
    assert _Client(payload).get_initial_release_dates("X") == {}
