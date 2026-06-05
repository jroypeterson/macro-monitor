"""Bank of Japan — placeholder.

BoJ's time-series portal (stat-search.boj.or.jp) has no clean keyless
by-code CSV endpoint like the BoE's; pulling it reliably needs a form POST
against the search UI, which isn't worth a fragile scraper here. Japan's
policy rate is therefore sourced from OECD in series.yaml (keyless, already
proven for China). This fetcher stays registered so a future native BoJ
client can drop in without touching the collector.
"""

from __future__ import annotations

from ..model import IntlObservation
from .base import SourceError


def fetch_boj(spec, *, session) -> list[IntlObservation]:
    raise SourceError(
        f"{spec.id}: BoJ native source not implemented — configure this series "
        "via 'oecd' instead (see series.yaml)"
    )
