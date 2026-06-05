"""Source clients for international series.

Each source exposes `fetch(spec, *, session) -> list[IntlObservation]`,
raising SourceError on failure. The collector wraps them so one bad source
never sinks the digest. `FETCHERS` maps a source name to its fetcher.
"""

from __future__ import annotations

from .base import SourceError
from . import boe, boj, estat, fred, jsonstat, ons, sdmx

FETCHERS = {
    "eurostat": jsonstat.fetch_eurostat,
    "ecb": sdmx.fetch_ecb,
    "oecd": sdmx.fetch_oecd,
    "ons": ons.fetch_ons,
    "boe": boe.fetch_boe,
    "estat": estat.fetch_estat,
    "boj": boj.fetch_boj,
    "fred": fred.fetch_fred,
}

__all__ = ["FETCHERS", "SourceError"]
