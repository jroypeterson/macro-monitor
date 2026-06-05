"""SDMX-JSON sources — ECB Data Portal and OECD.

Both speak "SDMX-JSON" but with different nesting:

ECB  (data-api.ecb.europa.eu/service/data/{flow}/{key}?format=jsondata)
  top-level `dataSets[0].series[<key>].observations` = {obsIdx: [val,...]}
  `structure.dimensions.observation[0].values`        = [{id: period}, ...]

OECD (sdmx.oecd.org/public/rest/data/{flow}/{key}?dimensionAtObservation=AllDimensions)
  `data.dataSets[0].observations` = {"d0:d1:...:t": [val,...]}  (all dims in key)
  `data.structures[0].dimensions.observation`          last dim is TIME_PERIOD

Both collapse to a single (period, value) list for our single-series queries.
"""

from __future__ import annotations

from ..model import IntlObservation
from .base import SourceError, get

ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
OECD_BASE = "https://sdmx.oecd.org/public/rest/data"


def fetch_ecb(spec, *, session) -> list[IntlObservation]:
    params = spec.params or {}
    flow, key = params.get("flow"), params.get("key")
    if not flow or not key:
        raise SourceError(f"{spec.id}: ecb params need 'flow' and 'key'")
    query = {"format": "jsondata"}
    if params.get("start"):
        query["startPeriod"] = params["start"]  # full history since date (for YTD)
    else:
        query["lastNObservations"] = params.get("last", 8)
    resp = get(session, f"{ECB_BASE}/{flow}/{key}", params=query)
    try:
        d = resp.json()
    except ValueError as exc:
        raise SourceError(f"{spec.id}: ecb returned non-JSON: {exc}") from exc

    try:
        series = d["dataSets"][0]["series"]
        skey = next(iter(series))
        observations = series[skey]["observations"]
        time_values = d["structure"]["dimensions"]["observation"][0]["values"]
    except (KeyError, IndexError, StopIteration) as exc:
        raise SourceError(f"{spec.id}: unexpected ecb structure: {exc}") from exc

    out: list[IntlObservation] = []
    for idx, arr in observations.items():
        period = time_values[int(idx)]["id"]
        if arr and arr[0] is not None:
            out.append(IntlObservation(period=period, value=float(arr[0])))
    out.sort(key=lambda o: o.period)
    if not out:
        raise SourceError(f"{spec.id}: ecb produced no observations")
    return out


def fetch_oecd(spec, *, session) -> list[IntlObservation]:
    params = spec.params or {}
    flow, key = params.get("flow"), params.get("key")
    if not flow or not key:
        raise SourceError(f"{spec.id}: oecd params need 'flow' and 'key'")
    query = {"dimensionAtObservation": "AllDimensions"}
    if params.get("start"):
        query["startPeriod"] = params["start"]
    resp = get(
        session,
        f"{OECD_BASE}/{flow}/{key}",
        params=query,
        headers={"Accept": "application/vnd.sdmx.data+json"},
    )
    try:
        d = resp.json()
    except ValueError as exc:
        raise SourceError(f"{spec.id}: oecd returned non-JSON: {exc}") from exc

    try:
        data = d["data"]
        observations = data["dataSets"][0]["observations"]
        obs_dims = data["structures"][0]["dimensions"]["observation"]
    except (KeyError, IndexError) as exc:
        raise SourceError(f"{spec.id}: unexpected oecd structure: {exc}") from exc

    # Locate the TIME_PERIOD dimension's position within the observation key.
    ti = next((i for i, dim in enumerate(obs_dims) if dim["id"] == "TIME_PERIOD"), None)
    if ti is None:
        raise SourceError(f"{spec.id}: oecd response has no TIME_PERIOD dimension")
    time_values = obs_dims[ti]["values"]

    out: list[IntlObservation] = []
    for okey, arr in observations.items():
        parts = okey.split(":")
        period = time_values[int(parts[ti])]["id"]
        if arr and arr[0] is not None:
            out.append(IntlObservation(period=period, value=float(arr[0])))
    out.sort(key=lambda o: o.period)
    if not out:
        raise SourceError(f"{spec.id}: oecd produced no observations")
    return out
