"""FRED API client.

PRIMARY collector for v1. No write-through cache — at ~11 families × ~40
series × 5yr history, a release-window pull is sub-second and caching
buys little while adding a staleness-management problem.

References:
  https://fred.stlouisfed.org/docs/api/fred/
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from ..fred_cache import FREDCache, reconstruct_observations

FRED_BASE = "https://api.stlouisfed.org/fred"
DEFAULT_TIMEOUT = 30  # seconds
# Calendar endpoint occasionally hangs at the FRED side. Keep per-call
# timeout reasonable but FAIL FAST instead of burning ~5 min per family
# on retries — graceful degradation in the schedulers absorbs failures
# at the family level. Future stability improvements can up this again.
RELEASE_DATES_TIMEOUT = 15
RELEASE_DATES_MAX_RETRIES = 2
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5


class FREDError(RuntimeError):
    pass


@dataclass(frozen=True)
class Observation:
    date: pd.Timestamp
    value: float | None  # FRED uses "." for missing; we normalize to None


@dataclass(frozen=True)
class ReleaseDate:
    release_id: int
    date: date


class FREDClient:
    def __init__(
        self,
        api_key: str | None = None,
        session: requests.Session | None = None,
        cache: FREDCache | None = None,
        use_cache: bool = True,
    ):
        """FRED API client with defensive fallback cache.

        cache: explicit FREDCache instance. If None and use_cache is
               True, opens the default cache at data/fred_cache.db.
        use_cache: set False to disable caching entirely (for tests that
               want pure online behavior).
        """
        self.api_key = api_key or os.environ.get("FRED_API_KEY")
        if not self.api_key:
            raise FREDError(
                "FRED_API_KEY not set. Register at "
                "https://fredaccount.stlouisfed.org/apikeys"
            )
        self.session = session or requests.Session()
        if cache is not None:
            self.cache = cache
        elif use_cache:
            self.cache = FREDCache()
        else:
            self.cache = None

    def _get(
        self,
        path: str,
        params: dict[str, Any],
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> dict[str, Any]:
        params = {**params, "api_key": self.api_key, "file_type": "json"}
        url = f"{FRED_BASE}{path}"

        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                if resp.status_code == 429:
                    time.sleep(RETRY_BACKOFF * (2**attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(RETRY_BACKOFF * (2**attempt))

        raise FREDError(f"FRED {path} failed after {max_retries} attempts: {last_exc}")

    def get_observations(
        self,
        series_id: str,
        observation_start: str | None = None,
        observation_end: str | None = None,
    ) -> pd.Series:
        """Fetch observations for a series. Returns a pandas Series indexed
        by date with float values (NaN for missing).

        Defensive cache behavior:
          - On successful fetch: write through to cache (latest-wins per series).
          - On FREDError (504, timeout, etc.): consult cache, return the
            most-recent successful fetch with attrs['from_cache']=True
            and attrs['cache_age_hours']=N. If no prior cache exists,
            re-raise the original error.
        """
        params: dict[str, Any] = {"series_id": series_id}
        if observation_start:
            params["observation_start"] = observation_start
        if observation_end:
            params["observation_end"] = observation_end

        try:
            data = self._get("/series/observations", params)
        except FREDError as exc:
            # Defensive fallback to cache.
            if self.cache is not None:
                cached = self.cache.get(series_id)
                if cached is not None:
                    data = reconstruct_observations(cached)
                    series = self._observations_to_series(series_id, data)
                    series.attrs["from_cache"] = True
                    series.attrs["cache_age_hours"] = cached.age_hours()
                    series.attrs["cache_fetched_at"] = cached.fetched_at_utc
                    return series
            raise

        # Live fetch succeeded — write through to cache and return.
        if self.cache is not None:
            try:
                self.cache.put(
                    series_id=series_id,
                    observations_json=json.dumps(data),
                    observation_start=observation_start,
                    observation_end=observation_end,
                )
            except Exception:
                # Cache write failure must not break the live path.
                pass

        series = self._observations_to_series(series_id, data)
        series.attrs["from_cache"] = False
        return series

    def _observations_to_series(
        self, series_id: str, data: dict[str, Any]
    ) -> pd.Series:
        """Decode a FRED /series/observations response into a pd.Series."""
        observations = data.get("observations", [])
        rows = []
        for obs in observations:
            d = pd.Timestamp(obs["date"])
            v = obs["value"]
            if v == "." or v is None or v == "":
                val: float | None = None
            else:
                try:
                    val = float(v)
                except (TypeError, ValueError):
                    val = None
            rows.append((d, val))

        if not rows:
            return pd.Series(dtype=float, name=series_id)

        idx = pd.DatetimeIndex([r[0] for r in rows])
        vals = [r[1] for r in rows]
        return pd.Series(vals, index=idx, name=series_id, dtype=float)

    def get_initial_release_dates(self, series_id: str) -> dict[pd.Timestamp, "date"]:
        """Map each observation period → the date it was FIRST published (ALFRED
        initial release, output_type=4 over the full real-time window).

        Used to state when a prior headline value was originally released. Returns
        an empty dict if the series has no vintage history or on any error —
        callers treat a missing release date as 'unknown' rather than failing.
        Deliberately NOT written to the defensive observations cache (its
        output_type differs from the live-value path, so it must not overwrite it).
        """
        from datetime import date as _date

        try:
            data = self._get("/series/observations", {
                "series_id": series_id,
                "realtime_start": "1776-07-04",
                "realtime_end": "9999-12-31",
                "output_type": "4",  # initial release only
            })
        except FREDError:
            return {}
        out: dict[pd.Timestamp, _date] = {}
        for obs in data.get("observations", []):
            rt = obs.get("realtime_start")
            if obs.get("value") in (".", None, "") or not rt:
                continue
            try:
                out[pd.Timestamp(obs["date"])] = _date.fromisoformat(rt)
            except (ValueError, TypeError):
                continue
        return out

    def get_series_info(self, series_id: str) -> dict[str, Any]:
        data = self._get("/series", {"series_id": series_id})
        seriess = data.get("seriess", [])
        if not seriess:
            raise FREDError(f"FRED returned no series info for {series_id!r}")
        return seriess[0]

    def get_release_dates(
        self,
        release_id: int,
        realtime_start: str | None = None,
        realtime_end: str | None = None,
        include_release_dates_with_no_data: bool = False,
    ) -> list[ReleaseDate]:
        """Fetch release-date entries for a given FRED release_id.

        Note: FRED's release-date entries reflect what the source agency
        published, not necessarily when FRED ingested the data. For the
        Monday weekly preview this is reliable; for same-day post detection
        the stale-period guard in the orchestrator is what matters.
        """
        params: dict[str, Any] = {
            "release_id": release_id,
            "include_release_dates_with_no_data": str(
                include_release_dates_with_no_data
            ).lower(),
        }
        if realtime_start:
            params["realtime_start"] = realtime_start
        if realtime_end:
            params["realtime_end"] = realtime_end

        data = self._get(
            "/release/dates",
            params,
            timeout=RELEASE_DATES_TIMEOUT,
            max_retries=RELEASE_DATES_MAX_RETRIES,
        )
        rows = data.get("release_dates", [])
        return [
            ReleaseDate(
                release_id=int(r.get("release_id", release_id)),
                date=datetime.strptime(r["date"], "%Y-%m-%d").date(),
            )
            for r in rows
        ]


def latest_observation_period(series: pd.Series) -> pd.Timestamp | None:
    """The most recent non-NaN observation in a series. Used by the
    stale-period guard.
    """
    non_null = series.dropna()
    if non_null.empty:
        return None
    return non_null.index.max()
