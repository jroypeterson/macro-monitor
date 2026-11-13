"""China government bond yields -- CFETS / chinamoney.com.cn (keyless).

The China Foreign Exchange Trade System publishes the closing government
bond yield curve (bondType CYCC000) as JSON. One call returns the whole
curve for the latest trading day; `params.term` picks the maturity in years.

LIMIT: the endpoint ignores startDate/endDate and always answers with the
latest day (checked 2026-11-12), so there is no prior-year point and the
digest shows the level without a year-to-date change.
"""

from __future__ import annotations

import requests

from ..model import IntlObservation
from .base import DEFAULT_TIMEOUT, SourceError

CHINAMONEY_URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/ClsYldCurvHis"


def parse_curve(payload: dict, term: float, spec_id: str) -> list[IntlObservation]:
    for rec in payload.get("records") or []:
        try:
            if abs(float(rec.get("yearTermStr")) - term) < 1e-9:
                return [
                    IntlObservation(
                        period=str(rec["newDateValueCN"]),
                        value=float(rec["maturityYieldStr"]),
                    )
                ]
        except (TypeError, ValueError, KeyError):
            continue
    raise SourceError(f"{spec_id}: chinamoney curve has no {term:g}Y point")


def fetch_chinamoney(spec, *, session) -> list[IntlObservation]:
    params = spec.params or {}
    try:
        term = float(params["term"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceError(f"{spec.id}: chinamoney params need a numeric 'term' (years)") from exc
    form = {
        "lang": "EN",
        "reference": "1",
        "bondType": params.get("bond_type", "CYCC000"),
        "termId": "1",
        "pageNum": "1",
        "pageSize": "500",
    }
    try:
        resp = session.post(
            CHINAMONEY_URL,
            data=form,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise SourceError(f"{spec.id}: chinamoney fetch failed: {exc}") from exc
    return parse_curve(payload, term, spec.id)
