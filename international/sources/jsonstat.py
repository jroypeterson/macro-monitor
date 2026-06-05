"""Eurostat — JSON-stat 2.0 dissemination API.

URL shape:
  .../statistics/1.0/data/{dataset}?format=JSON&lang=EN&{filter=code}&lastTimePeriod=N

Response is JSON-stat: a flat `value` dict keyed by the row-major index
over `id` (dimension order) with sizes in `size`; period labels live in
`dimension.time.category.index` (period -> position). For a fully-filtered
single series every dimension except `time` has size 1, so the flat index
collapses to the time position — but we compute strides properly anyway.
"""

from __future__ import annotations

from math import prod

from ..model import IntlObservation
from .base import SourceError, get

EUROSTAT_BASE = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
)


def fetch_eurostat(spec, *, session) -> list[IntlObservation]:
    params = spec.params or {}
    dataset = params.get("dataset")
    if not dataset:
        raise SourceError(f"{spec.id}: eurostat params need a 'dataset'")
    query = {"format": "JSON", "lang": "EN", "lastTimePeriod": params.get("last", 8)}
    query.update(params.get("filters", {}))

    resp = get(session, f"{EUROSTAT_BASE}/{dataset}", params=query)
    try:
        d = resp.json()
    except ValueError as exc:
        raise SourceError(f"{spec.id}: eurostat returned non-JSON: {exc}") from exc

    dim_order = d.get("id") or []
    size = d.get("size") or []
    value = d.get("value") or {}
    if "time" not in dim_order:
        raise SourceError(f"{spec.id}: eurostat response has no 'time' dimension")
    if not value:
        raise SourceError(f"{spec.id}: eurostat returned no values (check filters)")

    # Row-major strides for the flat `value` index.
    strides = [1] * len(size)
    for i in range(len(size) - 2, -1, -1):
        strides[i] = strides[i + 1] * size[i + 1]
    time_pos = dim_order.index("time")

    time_index = d["dimension"]["time"]["category"]["index"]  # period -> pos
    out: list[IntlObservation] = []
    for period, pos in sorted(time_index.items(), key=lambda kv: kv[1]):
        # All non-time dims collapse to index 0 in a single-series query.
        flat = pos * strides[time_pos]
        v = value.get(str(flat))
        if v is None:
            continue
        out.append(IntlObservation(period=period, value=float(v)))
    if not out:
        raise SourceError(f"{spec.id}: eurostat produced no observations")
    return out
