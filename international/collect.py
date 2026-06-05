"""Collect all configured international series into IntlSeriesResult objects.

Per-series isolation: a fetcher raising SourceError (dead endpoint, missing
key, bad locator) becomes a result with `error` set and no observations, so
one broken source never sinks the whole digest.
"""

from __future__ import annotations

from .config import IntlSeriesSpec, load_series, validate_series_or_raise
from .model import IntlObservation, IntlSeriesResult
from .sources import FETCHERS, SourceError
from .sources.base import make_session


def _prior_year_period(period: str) -> str | None:
    """The same period one year earlier: '2026-04'->'2025-04',
    '2026-Q1'->'2025-Q1', '2026'->'2025'. None if unparseable."""
    parts = period.split("-")
    try:
        prev_year = int(parts[0]) - 1
    except ValueError:
        return None
    return "-".join([str(prev_year), *parts[1:]])


def apply_yoy(observations: list[IntlObservation]) -> list[IntlObservation]:
    """Convert a level series to a year-on-year % change by matching each
    period to the same period one year earlier — robust to gaps (no
    positional 12-row assumption)."""
    by_period = {o.period: o.value for o in observations}
    out: list[IntlObservation] = []
    for o in observations:
        base_p = _prior_year_period(o.period)
        base = by_period.get(base_p) if base_p else None
        if base:
            out.append(IntlObservation(o.period, (o.value / base - 1.0) * 100.0))
    return out


def collect_one(spec: IntlSeriesSpec, *, session) -> IntlSeriesResult:
    result = IntlSeriesResult(
        spec_id=spec.id,
        region=spec.region,
        indicator=spec.indicator,
        label=spec.label,
        unit=spec.unit,
        source=spec.source,
        freq=spec.freq,
        decimals=spec.decimals,
        invert=spec.invert,
    )
    fetcher = FETCHERS.get(spec.source)
    if fetcher is None:
        result.error = f"no fetcher for source {spec.source!r}"
        return result
    try:
        obs = fetcher(spec, session=session)
        if (spec.params or {}).get("transform") == "yoy_pct":
            obs = apply_yoy(obs)
            if not obs:
                raise SourceError(
                    f"{spec.id}: yoy_pct transform produced no points "
                    "(need ≥13 months / 5 quarters of level data)"
                )
        result.observations = obs
    except SourceError as exc:
        result.error = str(exc)
    except Exception as exc:  # noqa: BLE001 — defensive: never let one series crash the run
        result.error = f"unexpected {type(exc).__name__}: {exc}"
    return result


def collect_all(
    specs: list[IntlSeriesSpec] | None = None,
) -> list[IntlSeriesResult]:
    if specs is None:
        specs = load_series()
        validate_series_or_raise(specs)
    session = make_session()
    return [collect_one(s, session=session) for s in specs]
