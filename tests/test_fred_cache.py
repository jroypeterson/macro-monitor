"""Tests for the FRED defensive cache.

This cache is what keeps `#macro` from going dark during a FRED outage.
The behavior bugs we'd dread:
  - Cache serving stale data without flagging it
  - Cache miss on first failure swallowing the original error
  - Cache write failure breaking the live fetch path
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from macro_monitor.collectors.fred import FREDClient, FREDError
from macro_monitor.fred_cache import CachedFetch, FREDCache, reconstruct_observations


# ---------------------------------------------------------------------------
# Pure cache module tests
# ---------------------------------------------------------------------------


def test_cache_roundtrip(tmp_path: Path):
    cache = FREDCache(tmp_path / "test.db")
    payload = {"observations": [{"date": "2026-01-01", "value": "100.5"}]}
    cache.put("CPIAUCSL", json.dumps(payload))

    got = cache.get("CPIAUCSL")
    assert got is not None
    assert got.series_id == "CPIAUCSL"
    assert json.loads(got.observations_json) == payload
    cache.close()


def test_cache_miss_returns_none(tmp_path: Path):
    cache = FREDCache(tmp_path / "test.db")
    assert cache.get("DOES_NOT_EXIST") is None
    cache.close()


def test_cache_latest_wins(tmp_path: Path):
    """Re-putting the same series_id should overwrite, not duplicate."""
    cache = FREDCache(tmp_path / "test.db")
    cache.put("X", json.dumps({"v": "old"}))
    cache.put("X", json.dumps({"v": "new"}))

    got = cache.get("X")
    assert got is not None
    assert json.loads(got.observations_json) == {"v": "new"}
    assert cache.count() == 1
    cache.close()


def test_cache_age_hours_computes_from_iso(tmp_path: Path):
    from datetime import datetime, timedelta, timezone

    cache = FREDCache(tmp_path / "test.db")
    six_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    cache.put("X", "{}", fetched_at_utc=six_hours_ago)

    got = cache.get("X")
    assert got is not None
    age = got.age_hours()
    assert 5.9 < age < 6.1  # rounding leeway
    cache.close()


def test_reconstruct_observations_decodes_json(tmp_path: Path):
    cache = FREDCache(tmp_path / "test.db")
    payload = {"observations": [{"date": "2026-01-01", "value": "100"}]}
    cache.put("X", json.dumps(payload))
    got = cache.get("X")
    assert got is not None
    assert reconstruct_observations(got) == payload
    cache.close()


# ---------------------------------------------------------------------------
# Integration: FREDClient + cache
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_observations_payload():
    return {
        "observations": [
            {"date": "2026-01-01", "value": "100.5"},
            {"date": "2026-02-01", "value": "101.2"},
            {"date": "2026-03-01", "value": "."},  # FRED's missing-value sentinel
        ]
    }


def test_successful_fetch_writes_through_to_cache(tmp_path: Path, fake_observations_payload):
    cache = FREDCache(tmp_path / "cache.db")
    client = FREDClient(api_key="fake", cache=cache)

    with patch.object(client, "_get", return_value=fake_observations_payload):
        s = client.get_observations("CPIAUCSL", observation_start="2026-01-01")

    assert len(s) == 3
    assert s.iloc[0] == 100.5
    assert pd.isna(s.iloc[2])  # FRED "." → NaN
    assert s.attrs.get("from_cache") is False

    # Cache should now hold the data
    cached = cache.get("CPIAUCSL")
    assert cached is not None
    assert reconstruct_observations(cached) == fake_observations_payload
    cache.close()


def test_fred_error_with_prior_cache_returns_cached_with_flag(
    tmp_path: Path, fake_observations_payload
):
    cache = FREDCache(tmp_path / "cache.db")
    cache.put("CPIAUCSL", json.dumps(fake_observations_payload))

    client = FREDClient(api_key="fake", cache=cache)

    with patch.object(client, "_get", side_effect=FREDError("simulated 504")):
        s = client.get_observations("CPIAUCSL")

    assert len(s) == 3
    assert s.iloc[0] == 100.5
    assert s.attrs.get("from_cache") is True
    assert "cache_age_hours" in s.attrs
    assert "cache_fetched_at" in s.attrs
    cache.close()


def test_fred_error_with_no_cache_reraises(tmp_path: Path):
    cache = FREDCache(tmp_path / "cache.db")
    client = FREDClient(api_key="fake", cache=cache)

    with patch.object(client, "_get", side_effect=FREDError("simulated 504")):
        with pytest.raises(FREDError):
            client.get_observations("NEVER_SEEN")
    cache.close()


def test_cache_write_failure_does_not_break_live_path(
    tmp_path: Path, fake_observations_payload
):
    """A broken cache (e.g. disk full) must not silently fail the live
    fetch path. We swallow cache write errors."""
    cache = FREDCache(tmp_path / "cache.db")
    client = FREDClient(api_key="fake", cache=cache)

    with patch.object(client, "_get", return_value=fake_observations_payload):
        with patch.object(cache, "put", side_effect=Exception("disk full")):
            # Should NOT raise — the live data is the success case.
            s = client.get_observations("CPIAUCSL")
            assert s.iloc[0] == 100.5
            assert s.attrs.get("from_cache") is False
    cache.close()


def test_use_cache_false_disables_caching(tmp_path: Path, fake_observations_payload):
    """For pure-online tests, use_cache=False skips all cache interaction."""
    client = FREDClient(api_key="fake", use_cache=False)

    with patch.object(client, "_get", return_value=fake_observations_payload):
        s = client.get_observations("CPIAUCSL")
        # Without a cache, the from_cache attribute may not be set;
        # important thing is that the fetch returns clean data.
        assert s.iloc[0] == 100.5

    assert client.cache is None
