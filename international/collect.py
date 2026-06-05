"""Collect all configured international series into IntlSeriesResult objects.

Per-series isolation: a fetcher raising SourceError (dead endpoint, missing
key, bad locator) becomes a result with `error` set and no observations, so
one broken source never sinks the whole digest.
"""

from __future__ import annotations

from .config import IntlSeriesSpec, load_series, validate_series_or_raise
from .model import IntlSeriesResult
from .sources import FETCHERS, SourceError
from .sources.base import make_session


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
        result.observations = fetcher(spec, session=session)
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
