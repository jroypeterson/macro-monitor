"""FRED API client.

PRIMARY collector for v1. No write-through cache — at ~11 families × ~40
series × 5yr history, a release-window pull is sub-second and caching
buys little while adding a staleness-management problem.

References:
  https://fred.stlouisfed.org/docs/api/fred/
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd
import requests

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
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self.api_key = api_key or os.environ.get("FRED_API_KEY")
        if not self.api_key:
            raise FREDError(
                "FRED_API_KEY not set. Register at "
                "https://fredaccount.stlouisfed.org/apikeys"
            )
        self.session = session or requests.Session()

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
        """
        params: dict[str, Any] = {"series_id": series_id}
        if observation_start:
            params["observation_start"] = observation_start
        if observation_end:
            params["observation_end"] = observation_end

        data = self._get("/series/observations", params)
        observations = data.get("observations", [])

        rows = []
        for obs in observations:
            d = pd.Timestamp(obs["date"])
            v = obs["value"]
            # FRED uses "." to signal missing
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
