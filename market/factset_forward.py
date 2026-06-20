"""FactSet Earnings Insight — forward S&P 500 EPS-growth consensus.

FactSet publishes *Earnings Insight* weekly (Fridays) as a **public** PDF at a
date-patterned URL. This fetches the most recent report, extracts the forward
(year-over-year) EPS-growth estimates — the in-progress quarter, the next two
quarters, and the CY estimates — plus the forward 12-month P/E, and caches the
parsed result so the S&P 500 earnings chart always has a forward overlay even
if a later fetch fails (graceful fallback to the mirror).

Note the methodology: the chart's *actual* line is S&P 500 reported TTM EPS
(multpl.com); FactSet's *forward* is bottom-up operating-EPS consensus by
quarter — a difference the chart caption flags.

(The same report also lands as a weekly email, Insight@factset.com →
research@jasonpeterson.nyc, but the public PDF avoids needing an attachment
download and is what the scheduled build uses.)
"""
from __future__ import annotations

import io
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

_MIRROR = Path(__file__).parent / "data"
_CACHE = _MIRROR / "latest" / "factset_forward.json"
_BASE = (
    "https://advantage.factset.com/hubfs/Website/Resources%20Section/"
    "Research%20Desk/Earnings%20Insight/EarningsInsight_{name}.pdf"
)
_UA = {"User-Agent": "Mozilla/5.0 (macro_monitor research; jroypeterson@gmail.com)"}

# FactSet's phrasings (stable across recent reports):
#   "For Q2 2026, the estimated (year-over-year) earnings growth rate for the S&P 500 is 21.9%."
#   "For Q3 2026 and Q4 2026, analysts are calling for earnings growth rates of 25.3% and 22.8%."
#   "For CY 2026, analysts are predicting (year-over-year) earnings growth of 23.2%."
#   "The forward 12-month P/E ratio is 20.1 ..."
_Q = re.compile(
    r"For (Q[1-4] 20\d\d), the estimated \(year-over-year\) earnings growth "
    r"rate for the S&P 500 is (-?[\d.]+)%", re.I)
_QQ = re.compile(
    r"For (Q[1-4] 20\d\d) and (Q[1-4] 20\d\d), analysts are calling for "
    r"earnings growth rates of (-?[\d.]+)% and (-?[\d.]+)%", re.I)
_CY = re.compile(
    r"For (CY 20\d\d), analysts are (?:predicting|projecting)"
    r"(?: \(year-over-year\))? earnings growth of (-?[\d.]+)%", re.I)
_PE = re.compile(r"forward 12-month P/E ratio is ([\d.]+)", re.I)


def recent_fridays(today: date, n: int = 6) -> list[date]:
    """Most recent Friday on/before `today`, then weekly back (FactSet publishes Fri)."""
    friday = today - timedelta(days=(today.weekday() - 4) % 7)
    return [friday - timedelta(weeks=i) for i in range(n)]


def _url(d: date, suffix: str = "") -> str:
    # Some weeks carry a trailing 'A' before .pdf (e.g. EarningsInsight_041026A.pdf).
    return _BASE.format(name=d.strftime("%m%d%y") + suffix)


def fetch_pdf(today: date | None = None) -> tuple[date, bytes]:
    """Return (report_date, pdf_bytes) for the most recent available report."""
    today = today or date.today()
    for d in recent_fridays(today):
        for suffix in ("", "A"):
            try:
                r = requests.get(_url(d, suffix), headers=_UA, timeout=30)
            except requests.RequestException:
                continue
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                return d, r.content
    raise RuntimeError("no recent FactSet Earnings Insight PDF found")


def parse_forward_text(text: str) -> dict:
    """Extract {quarters: {'Q2 2026': 21.9, ...}, cy: {'2026': 23.2, ...},
    forward_pe: 20.1} from the report text. Raises if nothing parses (so a
    silent format change surfaces instead of writing an empty cache)."""
    text = re.sub(r"\s+", " ", text)
    quarters: dict[str, float] = {}
    for per, val in _Q.findall(text):
        quarters[per] = float(val)
    for p1, p2, v1, v2 in _QQ.findall(text):
        quarters.setdefault(p1, float(v1))
        quarters.setdefault(p2, float(v2))
    cy = {per.split()[1]: float(val) for per, val in _CY.findall(text)}
    pe = _PE.search(text)
    if not quarters and not cy:
        raise ValueError("FactSet forward parse found no growth figures — format may have changed")
    return {"quarters": quarters, "cy": cy, "forward_pe": float(pe.group(1)) if pe else None}


def parse_forward(pdf_bytes: bytes) -> dict:
    """Extract the forward consensus from a FactSet Earnings Insight PDF."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
        text = " ".join((p.extract_text() or "") for p in doc.pages)
    return parse_forward_text(text)


def _save(parsed: dict, report_date: date, mirror: Path = _MIRROR) -> None:
    (mirror / "latest").mkdir(parents=True, exist_ok=True)
    payload = {**parsed, "report_date": report_date.isoformat()}
    _CACHE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_forward(prefer_live: bool = True, mirror: Path = _MIRROR) -> dict | None:
    """Forward consensus dict (with report_date), or None if unavailable.

    Live fetch+parse → cache → mirror. Returns None (not raises) when there's no
    data at all, so the chart can simply skip the overlay rather than fail.
    """
    if prefer_live:
        try:
            d, pdf = fetch_pdf()
            parsed = parse_forward(pdf)
            _save(parsed, d, mirror)
            return {**parsed, "report_date": d.isoformat()}
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] FactSet forward fetch/parse failed ({exc}); falling back to mirror")
    if _CACHE.exists():
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    return None


def quarter_to_ts(qlabel: str) -> pd.Timestamp:
    """'Q2 2026' -> quarter-end Timestamp (2026-06-30)."""
    q, y = qlabel.split()
    return pd.Period(f"{y}Q{int(q[1])}", freq="Q").to_timestamp(how="end").normalize()


def forward_quarterly_series(parsed: dict) -> pd.Series:
    """The forward quarterly YoY% estimates as a dated Series (quarter-end index)."""
    items = {quarter_to_ts(k): v for k, v in parsed.get("quarters", {}).items()}
    return pd.Series(items, dtype=float).sort_index()
