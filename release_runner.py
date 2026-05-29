"""Release orchestrator. Compute everything we need for a release post.

Given a FamilyConfig + a target period:
  1. Fetch each series in headline + components from FRED with sufficient history
  2. Apply primary_transform + also_display transforms at the target period
  3. Compute trend rows (3mo annualized, 6mo annualized, etc.)
  4. Compute delta z-score
  5. Bundle into a ReleaseResult

This module does NOT touch Slack, the posts ledger, or charts — it's pure
data shaping. That keeps it testable with a mocked FRED client.
"""

from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .collectors.fred import FREDClient, latest_observation_period
from .computed import compute_series
from .config import FamilyConfig
from .transforms import (
    annualized_n_month,
    apply_transform,
    delta_zscore,
)


@dataclass
class TransformedValue:
    """A single (transform, value) at a given period."""

    transform: str
    value: float | None
    raw_value: float | None = None
    label: str | None = None


@dataclass
class HeadlineSeriesResult:
    id: str
    label: str
    primary: TransformedValue
    also_display: list[TransformedValue]
    prior_primary: TransformedValue | None  # the same primary_transform one period prior
    display_unit: str | None = None


@dataclass
class ComponentSeriesResult:
    id: str
    label: str
    transformed: TransformedValue
    tags: list[str]
    display_unit: str | None = None


@dataclass
class ComputedSeriesResult:
    """A series derived in-process via the computed engine
    (e.g. HC employment = sum of NAICS 621+622+623)."""

    id: str
    label: str
    method: str
    inputs: list[str]
    transformed: TransformedValue
    also_display: list[TransformedValue]
    prior_primary: TransformedValue | None
    tags: list[str]
    display_unit: str | None = None


@dataclass
class TrendValue:
    label: str
    value: float | None
    window_months: int
    stat: str


@dataclass
class ContextResult:
    anchor_series: str
    anchor_transform: str
    trends: list[TrendValue]
    zscore: float | None
    zscore_lookback_years: int
    zscore_kind: str


@dataclass
class ReleaseResult:
    family_id: str
    family_display_name: str
    period: str               # e.g. "2026-04"
    period_label: str         # e.g. "April 2026"
    headline: list[HeadlineSeriesResult]
    components: list[ComponentSeriesResult]
    computed: list[ComputedSeriesResult]
    context: ContextResult | None

    # Source-freshness fields per plan §3.1
    source: str
    source_fetched_at: str           # ISO8601
    latest_observation_period: str   # e.g. "2026-04"
    expected_observation_period: str # e.g. "2026-04"
    is_stale: bool
    source_lag_minutes: int | None

    # Defensive-cache fallback fields (see fred_cache.py).
    # Set to True if ANY series in this release came from the cache
    # instead of a live FRED fetch. cache_age_hours is the age of the
    # OLDEST cached series in the release (worst-case staleness).
    from_fallback_cache: bool = False
    cache_age_hours: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    # All series this release knows about, real + computed. Used by the
    # chart factory to look up data by series id.
    def series_ids_for_charts(self) -> list[str]:
        return (
            [h.id for h in self.headline]
            + [c.id for c in self.components]
            + [cmp.id for cmp in self.computed]
        )


def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses to dicts. Used for JSON serialization."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def period_label(period: pd.Timestamp, cadence: str) -> str:
    if cadence == "monthly":
        return f"{calendar.month_name[period.month]} {period.year}"
    if cadence == "quarterly":
        q = (period.month - 1) // 3 + 1
        return f"Q{q} {period.year}"
    if cadence == "weekly":
        return f"Week ending {period.strftime('%b %d, %Y')}"
    return period.strftime("%Y-%m-%d")


def period_key(period: pd.Timestamp, cadence: str = "monthly") -> str:
    """Period key used in filenames + ledger keys. Cadence-aware so
    different cadences can't collide (e.g. weekly 2026-05-23 vs monthly
    2026-05, or quarterly Q1 2026 vs January 2026)."""
    if cadence == "weekly":
        return period.strftime("%Y-%m-%d")
    if cadence == "quarterly":
        q = (period.month - 1) // 3 + 1
        return f"{period.year}-Q{q}"
    # monthly default
    return period.strftime("%Y-%m")


def parse_period_key(key: str, cadence: str = "monthly") -> pd.Timestamp:
    """Reverse of `period_key`: parse a period key string back to a
    pd.Timestamp anchored on the first day of the period."""
    if cadence == "weekly":
        return pd.Timestamp(key)
    if cadence == "quarterly":
        # "2026-Q1" → first day of Q1 = 2026-01-01
        year_str, q_str = key.split("-Q")
        month = (int(q_str) - 1) * 3 + 1
        return pd.Timestamp(year=int(year_str), month=month, day=1)
    # monthly: "2026-04" → 2026-04-01
    return pd.Timestamp(key + "-01")


def _fetch_series(client: FREDClient, series_id: str, lookback_years: int = 10) -> pd.Series:
    """Fetch enough history for trend + chart + z-score math.

    lookback_years=10 gives plenty of room for 5y z-score plus the chart's
    longest lookback (25y for CPI long-history) — actually let's pull 30y
    for the long-history chart. We over-fetch slightly for simplicity.
    """
    start = (pd.Timestamp.utcnow() - pd.DateOffset(years=lookback_years)).strftime("%Y-%m-%d")
    return client.get_observations(series_id, observation_start=start)


def compute_release(
    family: FamilyConfig,
    client: FREDClient,
    target_period: pd.Timestamp | None = None,
    expected_period: pd.Timestamp | None = None,
    history_years: int = 30,
) -> ReleaseResult:
    """Compute a ReleaseResult for the given family + period.

    If target_period is None, uses the latest period available across the
    headline series.

    If expected_period is None, it's set equal to target_period (no stale
    check). The release poller will pass an explicit expected_period
    derived from the calendar so the stale-period guard fires when FRED
    hasn't ingested yet.
    """
    # === Fetch every declared FRED series with generous history ===
    series_cache: dict[str, pd.Series] = {}
    fetch_start = datetime.now(timezone.utc)

    real_ids = [s.id for s in family.headline] + [
        s.id for s in family.components
    ]

    # Track if any series in this release came from the defensive cache.
    # Stale-fallback warning surfaces in the Slack post + dashboard +
    # archive JSON so the user knows the data isn't live.
    from_fallback_cache = False
    max_cache_age_hours: float | None = None

    for sid in real_ids:
        s = _fetch_series(client, sid, lookback_years=history_years)
        series_cache[sid] = s
        if s.attrs.get("from_cache"):
            from_fallback_cache = True
            age = s.attrs.get("cache_age_hours")
            if age is not None and (max_cache_age_hours is None or age > max_cache_age_hours):
                max_cache_age_hours = age

    fetch_end = datetime.now(timezone.utc)

    # === Compute derived series and add to the same cache ===
    # Charts and components can reference computed IDs interchangeably
    # with FRED IDs since they all live in series_cache.
    for cs in family.computed:
        inputs = {iid: series_cache[iid] for iid in cs.inputs}
        series_cache[cs.id] = compute_series(cs.method, inputs, cs.id)

    # === Resolve target_period ===
    if target_period is None:
        # Use the latest period present in any HEADLINE series
        latest_dates = [
            latest_observation_period(series_cache[s.id])
            for s in family.headline
        ]
        latest_dates = [d for d in latest_dates if d is not None]
        if not latest_dates:
            raise RuntimeError(
                f"{family.display_name}: no observations available for any headline series"
            )
        target_period = max(latest_dates)
    if expected_period is None:
        expected_period = target_period

    # === Stale check ===
    headline_latest = max(
        (latest_observation_period(series_cache[s.id]) for s in family.headline),
        default=None,
    )
    is_stale = (
        headline_latest is None or headline_latest < expected_period
    )
    source_lag_minutes: int | None = None
    if headline_latest is not None and headline_latest >= expected_period:
        # We don't have an authoritative agency-publish timestamp here.
        # Leave as None for now; this will be populated by the poller when
        # we have the release-time stamp.
        source_lag_minutes = None

    # === Headline series ===
    headline_results: list[HeadlineSeriesResult] = []
    for s in family.headline:
        series = series_cache[s.id]
        raw_at_target = series.loc[target_period] if target_period in series.index else None
        primary_val = apply_transform(s.primary_transform, series, target_period)
        primary = TransformedValue(
            transform=s.primary_transform,
            value=primary_val,
            raw_value=float(raw_at_target) if pd.notna(raw_at_target) else None,
        )

        also_display: list[TransformedValue] = []
        for t in s.also_display:
            also_display.append(
                TransformedValue(
                    transform=t,
                    value=apply_transform(t, series, target_period),
                )
            )

        prior_period = target_period - pd.DateOffset(months=1)
        prior_primary: TransformedValue | None = None
        if prior_period in series.index:
            prior_primary = TransformedValue(
                transform=s.primary_transform,
                value=apply_transform(s.primary_transform, series, prior_period),
            )

        headline_results.append(
            HeadlineSeriesResult(
                id=s.id,
                label=s.label,
                primary=primary,
                also_display=also_display,
                prior_primary=prior_primary,
                display_unit=s.display_unit,
            )
        )

    # === Component series ===
    component_results: list[ComponentSeriesResult] = []
    for s in family.components:
        series = series_cache[s.id]
        tv = TransformedValue(
            transform=s.primary_transform,
            value=apply_transform(s.primary_transform, series, target_period),
        )
        component_results.append(
            ComponentSeriesResult(
                id=s.id,
                label=s.label,
                transformed=tv,
                tags=list(s.tags),
                display_unit=s.display_unit,
            )
        )

    # === Computed series ===
    computed_results: list[ComputedSeriesResult] = []
    for cs in family.computed:
        series = series_cache[cs.id]
        raw_at_target = (
            float(series.loc[target_period])
            if target_period in series.index and pd.notna(series.loc[target_period])
            else None
        )
        primary = TransformedValue(
            transform=cs.primary_transform,
            value=apply_transform(cs.primary_transform, series, target_period),
            raw_value=raw_at_target,
        )
        also_display = [
            TransformedValue(
                transform=t,
                value=apply_transform(t, series, target_period),
            )
            for t in cs.also_display
        ]
        prior_period = target_period - pd.DateOffset(months=1)
        prior_primary: TransformedValue | None = None
        if prior_period in series.index:
            prior_primary = TransformedValue(
                transform=cs.primary_transform,
                value=apply_transform(cs.primary_transform, series, prior_period),
            )
        computed_results.append(
            ComputedSeriesResult(
                id=cs.id,
                label=cs.label,
                method=cs.method,
                inputs=list(cs.inputs),
                transformed=primary,
                also_display=also_display,
                prior_primary=prior_primary,
                tags=list(cs.tags),
                display_unit=cs.display_unit,
            )
        )

    # === Context (trends + z-score) ===
    context_result: ContextResult | None = None
    if family.context is not None:
        ctx = family.context
        anchor = series_cache[ctx.anchor_series]
        trends = [
            TrendValue(
                label=t.label,
                value=_compute_trend(anchor, target_period, t.window_months, t.stat),
                window_months=t.window_months,
                stat=t.stat,
            )
            for t in ctx.trends
        ]
        zscore_val = (
            delta_zscore(
                anchor,
                target_period,
                ctx.anchor_transform,
                lookback_years=ctx.zscore_lookback_years,
            )
            if ctx.zscore_kind == "delta"
            else None  # level z-score not yet implemented; flag in v1
        )
        context_result = ContextResult(
            anchor_series=ctx.anchor_series,
            anchor_transform=ctx.anchor_transform,
            trends=trends,
            zscore=zscore_val,
            zscore_lookback_years=ctx.zscore_lookback_years,
            zscore_kind=ctx.zscore_kind,
        )

    return ReleaseResult(
        family_id=family.display_name.lower().replace(" ", "_").replace("&", "and"),
        family_display_name=family.display_name,
        period=period_key(target_period, family.cadence),
        period_label=period_label(target_period, family.cadence),
        headline=headline_results,
        components=component_results,
        computed=computed_results,
        context=context_result,
        source=family.source,
        source_fetched_at=fetch_end.isoformat(),
        latest_observation_period=(
            period_key(headline_latest, family.cadence) if headline_latest else ""
        ),
        expected_observation_period=period_key(expected_period, family.cadence),
        is_stale=is_stale,
        source_lag_minutes=source_lag_minutes,
        from_fallback_cache=from_fallback_cache,
        cache_age_hours=max_cache_age_hours,
    )


def _compute_trend(
    series: pd.Series, target: pd.Timestamp, window_months: int, stat: str
) -> float | None:
    """Compute a single trend value. `stat` is one of:
      - annualized_mom: compound MoM over the window, annualize
      - mean: simple mean of the window's MoM% (less useful; provided for completeness)
    """
    if stat == "annualized_mom":
        return annualized_n_month(series, target, window_months)
    if stat == "mean":
        # mean of the trailing window's MoM% values
        from .transforms import mom_pct

        values = []
        for i in range(window_months):
            d = target - pd.DateOffset(months=i)
            v = mom_pct(series, d)
            if v is not None:
                values.append(v)
        if not values:
            return None
        return float(pd.Series(values).mean())
    raise ValueError(f"Unknown trend stat: {stat!r}")
