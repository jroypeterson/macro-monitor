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
    level_zscore,
)


@dataclass
class TransformedValue:
    """A single (transform, value) at a given period."""

    transform: str
    value: float | None
    raw_value: float | None = None
    label: str | None = None


def is_rate_level(transform: str, display_unit: str | None) -> bool:
    """Is this series a rate LEVEL — a series whose observations are already
    percents (U-3/U-6 unemployment, the quits rate, capacity utilization,
    a delinquency rate)?

    For these, a *relative* percent change (yoy_pct / mom_pct) is a
    confusing %-of-a-% ("U-6 +3.85% YoY" when the rate moved 7.8 → 8.1).
    The meaningful change context is the percentage-point (pp) delta
    (mom_chg / yoy_chg), labelled "pp" (JP ask 2026-07-04). Renderers use
    this to pick pp formatting; compute_release uses it to build the
    prior-period context in pp instead of a relative %.
    """
    return transform == "raw" and display_unit == "%"


@dataclass
class HeadlineSeriesResult:
    id: str
    label: str
    primary: TransformedValue
    also_display: list[TransformedValue]
    prior_primary: TransformedValue | None  # the same primary_transform one period prior
    display_unit: str | None = None
    # Optional explicit basis label (see config.SeriesSpec.basis). None
    # means the publisher derives it from primary.transform.
    basis: str | None = None
    # Prior-period context (JP ask 2026-06-19): the period the prior value
    # covered (e.g. "April 2026") and that prior period's YoY, so the prior
    # line is self-dating and always carries a year-over-year read even when
    # the headline transform isn't itself YoY. `prior_yoy` is None when the
    # primary transform already IS yoy_pct (prior_primary already shows it).
    # For rate-LEVEL series (is_rate_level: U-3, U-6, quits rate…) the
    # relative % would be a %-of-a-%, so prior_yoy carries a `yoy_chg` pp
    # delta instead and `prior_mom` additionally carries the `mom_chg` pp
    # delta (JP ask 2026-07-04). prior_mom stays None for non-rate series.
    prior_period_label: str | None = None
    prior_yoy: TransformedValue | None = None
    prior_mom: TransformedValue | None = None
    # ISO date the prior value was first released (ALFRED initial release); None
    # when the series has no vintage history or the lookup is unavailable.
    prior_release_date: str | None = None
    # Plain-English definition (config.SeriesSpec.definition). Rendered as a
    # footnote wherever the series appears; None = no footnote.
    definition: str | None = None


@dataclass
class ComponentSeriesResult:
    id: str
    label: str
    transformed: TransformedValue
    tags: list[str]
    display_unit: str | None = None
    basis: str | None = None
    definition: str | None = None
    # The same primary_transform one observation prior. Lets renderers state
    # whether a YoY cut is accelerating or decelerating (white-collar ask,
    # JP 2026-06-30) without re-fetching.
    prior_transformed: TransformedValue | None = None
    # The same primary_transform three observations prior (= 3 months ago on
    # a monthly series). The accel/decel read shows BOTH comparisons — vs
    # prior month AND vs 3 months ago (JP ask 2026-07-04).
    prior_3m_transformed: TransformedValue | None = None


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
    basis: str | None = None
    definition: str | None = None
    # The same primary_transform 3 months prior — the second leg of the
    # accel/decel read (vs prior month AND vs 3 months ago, JP 2026-07-04).
    prior_3m_primary: TransformedValue | None = None


@dataclass
class TrendValue:
    label: str
    value: float | None
    window_months: int
    stat: str
    # What the value IS, so renderers don't force a bogus unit. An
    # annualized_mom stat is always a percent; a `mean` stat carries the
    # units of the family's anchor transform (mom_chg on payrolls/ADP = a
    # jobs count in `display_unit`, NOT a %). See H4.
    transform: str | None = None
    display_unit: str | None = None


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
    # Per-headline latest observation. In a healthy release every headline
    # series carries an observation AT target_period. When FRED has only
    # partially ingested a new period, a LEADING series pulls target_period
    # forward while a LAGGARD still ends a period back — that laggard then
    # renders a blank "—" headline, and (because compute_release was only
    # ever called without expected_period, C2) the old guard never fired,
    # so an apparently-fresh release posted with a missing headline. Treat
    # any such gap as stale so the poller skips and retries next cron rather
    # than posting a partial release.
    headline_latests = [
        latest_observation_period(series_cache[s.id]) for s in family.headline
    ]
    headline_latest = max(
        (d for d in headline_latests if d is not None), default=None
    )
    partial_ingest = any(d is None or d < target_period for d in headline_latests)
    is_stale = (
        headline_latest is None
        or headline_latest < expected_period
        or partial_ingest
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

        # Prior = the previous actual observation (cadence-agnostic: the last
        # index entry strictly before the target). More robust than a fixed
        # 1-month offset, which silently yielded no prior for quarterly/weekly
        # families and broke on observation gaps.
        _prior_idx = series.index[series.index < target_period]
        prior_period = _prior_idx.max() if len(_prior_idx) else None
        prior_primary: TransformedValue | None = None
        prior_yoy: TransformedValue | None = None
        prior_mom: TransformedValue | None = None
        prior_period_lbl: str | None = None
        prior_release: str | None = None
        if prior_period is not None:
            prior_primary = TransformedValue(
                transform=s.primary_transform,
                value=apply_transform(s.primary_transform, series, prior_period),
            )
            prior_period_lbl = period_label(prior_period, family.cadence)
            # Always surface the prior period's change context (JP ask
            # 2026-06-19) unless the headline is already a YoY (then
            # prior_primary already carries it, so don't duplicate).
            if is_rate_level(s.primary_transform, s.display_unit):
                # Rate LEVEL (U-3, U-6, quits rate…): a relative % change of
                # a percent is a %-of-a-%. Carry percentage-point deltas
                # instead — MoM + YoY pp changes (JP ask 2026-07-04).
                _mv = apply_transform("mom_chg", series, prior_period)
                if _mv is not None:
                    prior_mom = TransformedValue(transform="mom_chg", value=_mv)
                _yv = apply_transform("yoy_chg", series, prior_period)
                if _yv is not None:
                    prior_yoy = TransformedValue(transform="yoy_chg", value=_yv)
            elif s.primary_transform != "yoy_pct":
                _yv = apply_transform("yoy_pct", series, prior_period)
                if _yv is not None:
                    prior_yoy = TransformedValue(transform="yoy_pct", value=_yv)
            # When the prior value was first released (ALFRED initial release).
            # Best-effort: skip cleanly if the client lacks the method (mocked in
            # tests), the series has no vintage history, or the lookup errors.
            _getter = getattr(client, "get_initial_release_dates", None)
            if _getter is not None:
                try:
                    _rel = _getter(s.id).get(prior_period)
                    prior_release = _rel.isoformat() if _rel else None
                except Exception:  # noqa: BLE001
                    prior_release = None

        headline_results.append(
            HeadlineSeriesResult(
                id=s.id,
                label=s.label,
                primary=primary,
                also_display=also_display,
                prior_primary=prior_primary,
                display_unit=s.display_unit,
                basis=s.basis,
                prior_period_label=prior_period_lbl,
                prior_yoy=prior_yoy,
                prior_mom=prior_mom,
                prior_release_date=prior_release,
                definition=s.definition,
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
        # Prior observation in the same transform (cadence-agnostic, same
        # lookup as headline priors) — powers accel/decel context on cuts.
        # prior_3m = three observations back (3 months on a monthly series):
        # the second leg of the accel/decel read (JP ask 2026-07-04).
        _prior_idx = series.index[series.index < target_period].sort_values()
        _prior_period = _prior_idx[-1] if len(_prior_idx) else None
        prior_tv: TransformedValue | None = None
        if _prior_period is not None:
            prior_tv = TransformedValue(
                transform=s.primary_transform,
                value=apply_transform(s.primary_transform, series, _prior_period),
            )
        prior_3m_tv: TransformedValue | None = None
        if len(_prior_idx) >= 3:
            prior_3m_tv = TransformedValue(
                transform=s.primary_transform,
                value=apply_transform(s.primary_transform, series, _prior_idx[-3]),
            )
        component_results.append(
            ComponentSeriesResult(
                id=s.id,
                label=s.label,
                transformed=tv,
                tags=list(s.tags),
                display_unit=s.display_unit,
                basis=s.basis,
                definition=s.definition,
                prior_transformed=prior_tv,
                prior_3m_transformed=prior_3m_tv,
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
        # 3 months back — second leg of the accel/decel read (JP 2026-07-04).
        prior_3m_period = target_period - pd.DateOffset(months=3)
        prior_3m_primary: TransformedValue | None = None
        if prior_3m_period in series.index:
            prior_3m_primary = TransformedValue(
                transform=cs.primary_transform,
                value=apply_transform(cs.primary_transform, series, prior_3m_period),
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
                basis=cs.basis,
                definition=cs.definition,
                prior_3m_primary=prior_3m_primary,
            )
        )

    # === Context (trends + z-score) ===
    context_result: ContextResult | None = None
    if family.context is not None:
        ctx = family.context
        anchor = series_cache[ctx.anchor_series]
        # The anchor's display unit (e.g. "K" for PAYEMS) lives on its
        # SeriesSpec — resolve it so a `mean`-of-mom_chg trend renders as a
        # signed jobs count rather than a forced "%". None (ADP) → plain count.
        _anchor_unit = next(
            (
                s.display_unit
                for s in (*family.headline, *family.components)
                if s.id == ctx.anchor_series
            ),
            None,
        )
        trends = []
        for t in ctx.trends:
            # An annualized_mom stat is a percent regardless of the anchor
            # transform; every other stat carries the anchor transform's units.
            if t.stat == "annualized_mom":
                _t_transform: str | None = "annualized_mom"
                _t_unit: str | None = None
            else:
                _t_transform = ctx.anchor_transform
                _t_unit = _anchor_unit
            trends.append(
                TrendValue(
                    label=t.label,
                    value=_compute_trend(
                        anchor,
                        target_period,
                        t.window_months,
                        t.stat,
                        ctx.anchor_transform,
                    ),
                    window_months=t.window_months,
                    stat=t.stat,
                    transform=_t_transform,
                    display_unit=_t_unit,
                )
            )
        _zscore_fn = delta_zscore if ctx.zscore_kind == "delta" else level_zscore
        zscore_val = _zscore_fn(
            anchor,
            target_period,
            ctx.anchor_transform,
            lookback_years=ctx.zscore_lookback_years,
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
    series: pd.Series,
    target: pd.Timestamp,
    window_months: int,
    stat: str,
    anchor_transform: str = "mom_pct",
) -> float | None:
    """Compute a single trend value. `stat` is one of:
      - annualized_mom: compound MoM over the window, annualize
      - mean: simple mean of the trailing window's `anchor_transform` values

    The `mean` branch averages the FAMILY's anchor transform (H4) — for
    payrolls/ADP that is `mom_chg` (a jobs count), NOT `mom_pct`; averaging
    the % produced a bogus "3mo avg change: 0.11%" instead of "~+167K".
    """
    if stat == "annualized_mom":
        return annualized_n_month(series, target, window_months)
    if stat == "mean":
        from .transforms import apply_transform

        values = []
        for i in range(window_months):
            d = target - pd.DateOffset(months=i)
            v = apply_transform(anchor_transform, series, d)
            if v is not None:
                values.append(v)
        if not values:
            return None
        return float(pd.Series(values).mean())
    raise ValueError(f"Unknown trend stat: {stat!r}")
