"""FRED — reuse the project's existing FRED client for international series.

Used where a native source is blocked or has no clean keyless endpoint
(e.g. Japan's policy rate, which BoJ doesn't expose by-code). FRED is a
keyless-to-us aggregator (needs FRED_API_KEY, already configured for the US
feed). `params.series` is the FRED series id; `params.transform` optionally
applies 'yoy_pct' for index series that need a year-on-year conversion.
"""

from __future__ import annotations

from ..model import IntlObservation
from .base import SourceError


def fetch_fred(spec, *, session) -> list[IntlObservation]:
    params = spec.params or {}
    series_id = params.get("series")
    if not series_id:
        raise SourceError(f"{spec.id}: fred params need a 'series' id")
    try:
        from ...collectors.fred import FREDClient, FREDError
    except ImportError as exc:  # pragma: no cover
        raise SourceError(f"{spec.id}: FRED client unavailable: {exc}") from exc

    try:
        s = FREDClient().get_observations(series_id)
    except FREDError as exc:
        raise SourceError(f"{spec.id}: fred fetch failed: {exc}") from exc
    if s is None or s.empty:
        raise SourceError(f"{spec.id}: fred returned no observations for {series_id}")

    if params.get("transform") == "yoy_pct":
        periods = {"monthly": 12, "quarterly": 4, "annual": 1}.get(spec.freq, 12)
        s = s.pct_change(periods=periods) * 100.0
        s = s.dropna()

    out: list[IntlObservation] = []
    for ts, val in s.items():
        if val is None:
            continue
        period = _period_label(ts, spec.freq)
        try:
            out.append(IntlObservation(period=period, value=float(val)))
        except (TypeError, ValueError):
            continue
    if not out:
        raise SourceError(f"{spec.id}: fred produced no usable observations")
    return out


def _period_label(ts, freq: str) -> str:
    if freq == "quarterly":
        return f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"
    if freq == "annual":
        return f"{ts.year}"
    if freq == "daily":
        return ts.strftime("%Y-%m-%d")
    return ts.strftime("%Y-%m")
