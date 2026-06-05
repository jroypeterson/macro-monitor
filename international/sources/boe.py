"""Bank of England — IADB CSV download (keyless).

  https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp
    ?csv.x=yes&Datefrom=DD/Mon/YYYY&Dateto=now&SeriesCodes=<code>&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N

Returns `DATE,<code>` rows with daily values (e.g. Bank Rate IUDBEDR). For a
policy rate the value is carried daily, so we collapse runs of equal values
to the dates the level actually changed — that makes `previous` the prior
*level*, not yesterday.
"""

from __future__ import annotations

import csv
import io

from ..model import IntlObservation
from .base import SourceError, get

BOE_BASE = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
_MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def _iso(d: str) -> str | None:
    # '02 Jan 2025' -> '2025-01-02'
    parts = d.split()
    if len(parts) != 3:
        return None
    day, mon, year = parts
    mm = _MONTHS.get(mon)
    return f"{year}-{mm}-{int(day):02d}" if mm else None


def fetch_boe(spec, *, session) -> list[IntlObservation]:
    params = spec.params or {}
    code = params.get("series")
    if not code:
        raise SourceError(f"{spec.id}: boe params need a 'series' code")
    query = {
        "csv.x": "yes",
        "Datefrom": params.get("from", "01/Jan/2020"),
        "Dateto": "now",
        "SeriesCodes": code,
        "CSVF": "TN",
        "UsingCodes": "Y",
        "VPD": "Y",
        "VFD": "N",
    }
    resp = get(session, BOE_BASE, params=query)
    text = resp.text.strip()
    if not text or "DATE" not in text.splitlines()[0].upper():
        raise SourceError(f"{spec.id}: boe returned no CSV header")

    reader = csv.DictReader(io.StringIO(text))
    field = next((f for f in (reader.fieldnames or []) if f.upper() != "DATE"), None)
    if not field:
        raise SourceError(f"{spec.id}: boe CSV has no value column")

    raw: list[IntlObservation] = []
    for row in reader:
        period = _iso(row.get("DATE", ""))
        val = row.get(field)
        if period is None or val in (None, ""):
            continue
        try:
            raw.append(IntlObservation(period=period, value=float(val)))
        except (TypeError, ValueError):
            continue
    raw.sort(key=lambda o: o.period)

    # Collapse daily-carried runs to level-change points.
    out: list[IntlObservation] = []
    for obs in raw:
        if not out or out[-1].value != obs.value:
            out.append(obs)
    if not out:
        raise SourceError(f"{spec.id}: boe produced no observations")
    return out
