"""ONS (UK) — the ons.gov.uk time-series `/data` JSON endpoint.

The legacy api.ons.gov.uk host is dead; the website's own `/data` endpoint
is the reliable one:
  https://www.ons.gov.uk/<topic-path>/timeseries/<cdid>/<dataset>/data

Response carries parallel `months` / `quarters` / `years` arrays of
{date, value}, with dates like '2026 APR' / '2026 Q1' / '2026'. We read
the array matching the series' freq and normalize the period label.
"""

from __future__ import annotations

from ..model import IntlObservation
from .base import SourceError, get

_MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def _norm_period(raw: str, freq: str) -> str | None:
    raw = raw.strip()
    if freq == "annual":
        return raw if raw.isdigit() else None
    parts = raw.split()
    if len(parts) != 2:
        return None
    year, tail = parts
    if freq == "monthly":
        mm = _MONTHS.get(tail.upper())
        return f"{year}-{mm}" if mm else None
    if freq == "quarterly":
        # 'Q1' -> 'Q1'
        return f"{year}-{tail.upper()}" if tail.upper().startswith("Q") else None
    return None


def fetch_ons(spec, *, session) -> list[IntlObservation]:
    params = spec.params or {}
    url = params.get("url")
    if not url:
        raise SourceError(f"{spec.id}: ons params need a 'url' (the /data endpoint)")
    resp = get(session, url)
    try:
        d = resp.json()
    except ValueError as exc:
        raise SourceError(f"{spec.id}: ons returned non-JSON: {exc}") from exc

    bucket = {"monthly": "months", "quarterly": "quarters", "annual": "years"}.get(spec.freq)
    rows = d.get(bucket) or []
    if not rows:
        raise SourceError(f"{spec.id}: ons returned no '{bucket}' data")

    out: list[IntlObservation] = []
    for r in rows:
        period = _norm_period(str(r.get("date", "")), spec.freq)
        val = r.get("value")
        if period is None or val in (None, ""):
            continue
        try:
            out.append(IntlObservation(period=period, value=float(val)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda o: o.period)
    if not out:
        raise SourceError(f"{spec.id}: ons produced no observations")
    return out
