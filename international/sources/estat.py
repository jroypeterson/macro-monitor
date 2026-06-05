"""Japan e-Stat — getStatsData JSON API (requires a free appId).

Set ESTAT_APP_ID in .env (issued from e-Stat → My Page → "Issue Application
ID"; a ~40-char string). Without it this source raises a clear error and
the collector simply shows the Japanese rows as unavailable.

Period decoding uses the response's own time CLASS_OBJ (`@name` like
"2026年4月" / "2026年第1四半期"), which is more robust across tables than the
numeric @time code. NOTE: only end-to-end testable once a key is present;
the statsDataId values in series.yaml may need confirming against the live
table the first time the key is wired.
"""

from __future__ import annotations

import os
import re

from ..model import IntlObservation
from .base import SourceError, get

ESTAT_BASE = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"

_YEAR = re.compile(r"(\d{4})\s*年")
_MONTH = re.compile(r"(\d{1,2})\s*月")
_QUARTER = re.compile(r"第\s*([1-4Ⅰ-Ⅳ])\s*四半期")
_Q_MAP = {"Ⅰ": "1", "Ⅱ": "2", "Ⅲ": "3", "Ⅳ": "4"}


def _norm_period(name: str, freq: str) -> str | None:
    ym = _YEAR.search(name)
    if not ym:
        return None
    year = ym.group(1)
    if freq == "annual":
        return year
    if freq == "quarterly":
        q = _QUARTER.search(name)
        if q:
            n = _Q_MAP.get(q.group(1), q.group(1))
            return f"{year}-Q{n}"
        return None
    # monthly
    mm = _MONTH.search(name)
    return f"{year}-{int(mm.group(1)):02d}" if mm else None


def fetch_estat(spec, *, session) -> list[IntlObservation]:
    app_id = os.environ.get("ESTAT_APP_ID", "").strip()
    if not app_id:
        raise SourceError(
            f"{spec.id}: ESTAT_APP_ID not set — register an e-Stat application "
            "ID and add it to .env to enable Japan e-Stat series"
        )
    params = spec.params or {}
    stats_data_id = params.get("statsDataId")
    if not stats_data_id:
        raise SourceError(f"{spec.id}: estat params need a 'statsDataId'")

    query = {
        "appId": app_id,
        "statsDataId": stats_data_id,
        "limit": params.get("limit", 24),
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
    }
    # Pass through any cdCat / cdArea filters that single out one series.
    for k, v in (params.get("filters") or {}).items():
        query[k] = v

    resp = get(session, ESTAT_BASE, params=query)
    try:
        d = resp.json()
    except ValueError as exc:
        raise SourceError(f"{spec.id}: estat returned non-JSON: {exc}") from exc

    try:
        sd = d["GET_STATS_DATA"]["STATISTICAL_DATA"]
        result = d["GET_STATS_DATA"]["RESULT"]
    except KeyError as exc:
        raise SourceError(f"{spec.id}: unexpected estat envelope: {exc}") from exc
    if str(result.get("STATUS")) != "0":
        raise SourceError(f"{spec.id}: estat error {result.get('STATUS')}: {result.get('ERROR_MSG')}")

    # Build time code -> display name map from the time CLASS_OBJ.
    time_names: dict[str, str] = {}
    class_objs = sd.get("CLASS_INF", {}).get("CLASS_OBJ", [])
    if isinstance(class_objs, dict):
        class_objs = [class_objs]
    for obj in class_objs:
        if obj.get("@id") in ("time", "tab", "@time") or "時間軸" in str(obj.get("@name", "")):
            cls = obj.get("CLASS", [])
            if isinstance(cls, dict):
                cls = [cls]
            for c in cls:
                time_names[c.get("@code")] = c.get("@name", "")

    values = sd.get("DATA_INF", {}).get("VALUE", [])
    if isinstance(values, dict):
        values = [values]
    if not values:
        raise SourceError(f"{spec.id}: estat returned no VALUE rows")

    out: list[IntlObservation] = []
    for v in values:
        code = v.get("@time")
        name = time_names.get(code, code or "")
        period = _norm_period(name, spec.freq)
        raw = v.get("$")
        if period is None or raw in (None, "", "-", "***"):
            continue
        try:
            out.append(IntlObservation(period=period, value=float(raw)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda o: o.period)
    if not out:
        raise SourceError(f"{spec.id}: estat produced no usable observations")
    return out
