"""Current Shiller CAPE from multpl.com.

Robert Shiller's downloadable ie_data.xls is updated only irregularly (it lagged ~2 years,
to 2023-09), but the CAPE itself is maintained current at multpl.com (his underlying series,
back to 1871). This fetches the monthly table so the valuation charts are actually current.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd
import requests

_URL = "https://www.multpl.com/shiller-pe/table/by-month"
_UA = {"User-Agent": "Mozilla/5.0 (macro_monitor research; jroypeterson@gmail.com)"}
_MIRROR = Path(__file__).parent / "data"
# Date cell, then a value cell that leads with an &#x2002; en-space entity before the number.
_ROW = re.compile(r"<td>([A-Z][a-z]{2} \d{1,2}, \d{4})</td>\s*<td>(?:\s|&[^;]+;)*([\d.]+)")


def fetch_cape_multpl() -> pd.Series:
    """Monthly Shiller CAPE indexed by month-start, 1871→present. Raises on fetch/parse fail."""
    r = requests.get(_URL, headers=_UA, timeout=30)
    r.raise_for_status()
    rows = _ROW.findall(r.text)
    if len(rows) < 1000:
        raise ValueError(f"multpl CAPE parse returned only {len(rows)} rows")
    data = {pd.Timestamp(d).to_period("M").to_timestamp(): float(v) for d, v in rows}
    return pd.Series(data, name="cape").sort_index()


def save_cape(s: pd.Series, mirror: Path = _MIRROR) -> None:
    today = date.today().isoformat()
    (mirror / "raw" / today).mkdir(parents=True, exist_ok=True)
    (mirror / "latest").mkdir(parents=True, exist_ok=True)
    csv = s.to_csv()
    (mirror / "raw" / today / "cape_multpl.csv").write_text(csv, encoding="utf-8")
    (mirror / "latest" / "cape_multpl.csv").write_text(csv, encoding="utf-8")


def load_cape(mirror: Path = _MIRROR, prefer_live: bool = True) -> pd.Series:
    """Current CAPE: live multpl (cached to mirror) → mirrored CSV → stale Yale ie_data.xls."""
    if prefer_live:
        try:
            s = fetch_cape_multpl()
            save_cape(s, mirror)
            return s
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] live CAPE fetch failed ({exc}); falling back to mirror/Yale file")
    csv = mirror / "latest" / "cape_multpl.csv"
    if csv.exists():
        return pd.read_csv(csv, index_col=0, parse_dates=True).iloc[:, 0].dropna()
    from .charts import parse_shiller  # last resort: the (stale) Yale spreadsheet
    return parse_shiller()["cape"].dropna()


if __name__ == "__main__":
    cape = load_cape()
    print(f"CAPE: {cape.iloc[-1]:.1f} ({cape.index[-1]:%b %Y}); {len(cape)} months from {cape.index[0]:%Y}")
