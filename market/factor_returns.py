"""Factor period-return table from the mirrored Ken French monthly factors.

Phase 2 of the market module (README: "Parse the raw files into normalized time
series ... factor-return cumulative/rolling series"). Where `build_charts` renders
the long-history cumulative factor *chart*, this answers the recent-performance
question JP asked — "how did each factor do in 2025 and 2026" — as a compact
period-return table: the latest month, quarter-to-date, 2026 year-to-date,
trailing 12 months, and full-year 2025.

Source: the zipped monthly CSVs already in `data/latest/` (Ken French Data
Library — free, no network). Values in those files are monthly returns in
PERCENT; a period return compounds them: prod(1 + r/100) - 1. Ken French
publishes with a ~1-2 month lag, so "2026 YTD" runs through the latest published
month, which is surfaced in the report header.

Factors covered (the academic core): the Fama-French 5 (market, size, value,
profitability, investment) plus momentum. AQR's QMJ / BAB (Excel) are mirrored
too but not yet parsed here — a natural follow-on.

Entry point: `build()` -> writes `readable/market/factor_returns_<YYYYMM>.md`
(+ a stable `factor_returns_latest.md`) and returns the path. Wired as the
`market-factors` CLI subcommand.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

_LATEST = Path(__file__).parent / "data" / "latest"
_OUT = Path(__file__).parent.parent / "readable" / "market"

# Which mirrored file supplies which factor columns (in the file's column order,
# excluding the leading YYYYMM date column). The 5-factor file carries the market/
# size/value premia AND profitability/investment, so it is the single source for
# all five; momentum comes from its own file.
_FF5 = "F-F_Research_Data_5_Factors_2x3_CSV.zip"
_MOM = "F-F_Momentum_Factor_CSV.zip"
_FF5_COLS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
_MOM_COLS = ["Mom"]

# Display order + human labels for the report (RF shown last as context).
_FACTOR_LABELS = [
    ("Mkt-RF", "Market (excess)"),
    ("SMB", "Size (SMB)"),
    ("HML", "Value (HML)"),
    ("RMW", "Profitability (RMW)"),
    ("CMA", "Investment (CMA)"),
    ("Mom", "Momentum (UMD)"),
    ("RF", "Risk-free (1mo T-bill)"),
]

_ROW_RE = re.compile(r"^\s*(\d{6})\s*,(.+)$")


def _parse_french_monthly(zip_path: Path, columns: list[str]) -> dict[int, dict[str, float]]:
    """Parse a zipped Ken French monthly CSV into {YYYYMM: {factor: pct}}.

    The files open with prose metadata, then a `,Col1,Col2,...` header, then
    monthly `YYYYMM, v, v, ...` rows, then a blank line and an *annual* section
    whose rows are 4-digit years. Requiring a 6-digit leading field selects the
    monthly rows only and skips both the metadata and the annual block. A row whose
    values don't all parse as floats (e.g. a `-99.99`-padded stub or a stray
    trailer) is dropped rather than trusted.
    """
    with zipfile.ZipFile(zip_path) as zf:
        text = zf.read(zf.namelist()[0]).decode("latin-1")

    out: dict[int, dict[str, float]] = {}
    for line in text.splitlines():
        m = _ROW_RE.match(line)
        if not m:
            continue
        ym = int(m.group(1))
        vals = [v.strip() for v in m.group(2).split(",")]
        if len(vals) < len(columns):
            continue
        rec: dict[str, float] = {}
        try:
            for name, raw in zip(columns, vals):
                rec[name] = float(raw)
        except ValueError:
            continue
        out[ym] = rec
    return out


def load_factors() -> dict[int, dict[str, float]]:
    """Merge the 5-factor and momentum monthly series into one {YYYYMM: {factor}}."""
    merged: dict[int, dict[str, float]] = {}
    for ym, rec in _parse_french_monthly(_LATEST / _FF5, _FF5_COLS).items():
        merged.setdefault(ym, {}).update(rec)
    for ym, rec in _parse_french_monthly(_LATEST / _MOM, _MOM_COLS).items():
        merged.setdefault(ym, {}).update(rec)
    return merged


def _shift_month(ym: int, delta: int) -> int:
    """YYYYMM shifted by `delta` months (negative = earlier)."""
    y, m = divmod(ym, 100)
    idx = y * 12 + (m - 1) + delta
    ny, nm = divmod(idx, 12)
    return ny * 100 + (nm + 1)


def _months_between(start_ym: int, end_ym: int) -> list[int]:
    """Inclusive list of YYYYMM month keys from start to end."""
    out = []
    y, m = divmod(start_ym, 100)
    ey, em = divmod(end_ym, 100)
    while (y, m) <= (ey, em):
        out.append(y * 100 + m)
        m += 1
        if m > 12:
            y += 1
            m = 1
    return out


def _cumulative(factors: dict[int, dict[str, float]], factor: str,
                months: list[int]) -> float | None:
    """Compound monthly percent returns over `months` into one period return (%)."""
    prod = 1.0
    n = 0
    for ym in months:
        r = factors.get(ym, {}).get(factor)
        if r is None:
            continue
        prod *= 1.0 + r / 100.0
        n += 1
    if n == 0:
        return None
    return (prod - 1.0) * 100.0


def _period_months(latest: int) -> dict[str, list[int]]:
    """The month-lists for each reported period, anchored at the latest month."""
    year, month = divmod(latest, 100)
    q_start_month = ((month - 1) // 3) * 3 + 1
    return {
        "Latest mo": [latest],
        "QTD": _months_between(year * 100 + q_start_month, latest),
        f"{year} YTD": _months_between(year * 100 + 1, latest),
        "Trailing 12m": _months_between(_shift_month(latest, -11), latest),
        "2025 FY": _months_between(202501, 202512),
    }


def compute_table(factors: dict[int, dict[str, float]] | None = None) -> dict:
    """Return {'latest': YYYYMM, 'periods': [names], 'rows': [(key,label,{period:pct})]}."""
    factors = factors if factors is not None else load_factors()
    if not factors:
        raise RuntimeError(f"No factor data parsed from {_LATEST} — run `market-fetch` first.")
    latest = max(factors)
    periods = _period_months(latest)
    rows = []
    for key, label in _FACTOR_LABELS:
        vals = {p: _cumulative(factors, key, months) for p, months in periods.items()}
        rows.append((key, label, vals))
    return {"latest": latest, "periods": list(periods.keys()), "rows": rows}


def _fmt(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.1f}%"


def _month_name(ym: int) -> str:
    import calendar
    y, m = divmod(ym, 100)
    return f"{calendar.month_abbr[m]} {y}"


def render_markdown(table: dict) -> str:
    latest = table["latest"]
    periods = table["periods"]
    lines = [
        "# Fundamental factor performance",
        "",
        f"_Fama-French 5 factors + momentum · monthly returns compounded per period · "
        f"data through **{_month_name(latest)}** (Ken French Data Library, ~1-2 month "
        f"publication lag)._",
        "",
        "| Factor | " + " | ".join(periods) + " |",
        "|" + "---|" * (len(periods) + 1),
    ]
    for _key, label, vals in table["rows"]:
        lines.append("| " + label + " | " + " | ".join(_fmt(vals[p]) for p in periods) + " |")
    lines += [
        "",
        "**Reading it:** each cell is the factor's cumulative return over the period "
        "(long-minus-short premium, in percent). Market is the excess return over the "
        "risk-free rate; Size/Value/Profitability/Investment/Momentum are the classic "
        "long-short premia. A negative Value or Momentum number means that style "
        "detracted over the window.",
        "",
        "_Source: `market/data/latest/` (mirrored via `cli market-fetch`). AQR QMJ / BAB "
        "are mirrored too but not yet parsed into this table — a follow-on. Regenerate: "
        "`python -m macro_monitor.cli market-factors`._",
    ]
    return "\n".join(lines) + "\n"


def build() -> Path:
    """Compute the factor-return table and write it to readable/market/."""
    table = compute_table()
    md = render_markdown(table)
    _OUT.mkdir(parents=True, exist_ok=True)
    dated = _OUT / f"factor_returns_{table['latest']}.md"
    dated.write_text(md, encoding="utf-8")
    (_OUT / "factor_returns_latest.md").write_text(md, encoding="utf-8")
    return dated


if __name__ == "__main__":
    print(build())
