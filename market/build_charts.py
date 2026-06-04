"""Build the top-down market charts (valuation + factors) into readable/market/ and write
the gallery page. Parses the mirrored Shiller / Damodaran / Ken French files.

Run: ``python -m macro_monitor.cli market-charts`` (or this module).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import cape as CAPE
from . import charts as C

_MKT = Path(__file__).parent / "data" / "latest"
_DAM = Path(__file__).parent.parent / "damodaran" / "data" / "latest"
_OUT = Path(__file__).parent.parent / "readable" / "market"
_SRC = "Sources: Shiller CAPE via multpl.com (current), A. Damodaran (NYU Stern), Kenneth French Data Library."


def _cumulative(returns: pd.Series) -> pd.Series:
    """Growth of $1 from a monthly return series."""
    return (1 + returns.dropna()).cumprod()


def build(out_dir: Path = _OUT) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, dict] = {}

    # --- 1. Shiller CAPE vs its own history -------------------------------- #
    # Sourced live from multpl.com (current); Shiller's own ie_data.xls lags ~2 years.
    cape = CAPE.load_cape().dropna()
    pctile = (cape.rank(pct=True).iloc[-1]) * 100
    rendered["cape_history"] = dict(
        title="Shiller CAPE vs History",
        sub=f"Cyclically-adjusted P/E (10-yr real earnings). Latest is in the {pctile:.0f}th percentile of its 1881→ history.",
        path=C.render_line({"Shiller CAPE": cape}, "Shiller CAPE vs History",
                           f"Cyclically-adjusted P/E. Latest = {pctile:.0f}th percentile since 1881.",
                           out_dir / "cape_history.png", _SRC, mean_band=cape, latest_fmt="{:.1f}"))

    # --- 2. Damodaran implied ERP ------------------------------------------ #
    erp = C.parse_damodaran_erp()
    rendered["implied_erp"] = dict(
        title="Implied Equity Risk Premium (Damodaran)",
        sub="The forward-looking ERP the market is pricing in, back-solved from S&P prices/cashflows.",
        path=C.render_line({"Implied ERP": erp["implied_erp"], "Risk-free (10Y T.Bond)": erp["riskfree"]},
                           "Implied Equity Risk Premium (Damodaran)",
                           "Forward ERP + risk-free rate, annual 1960→.",
                           out_dir / "implied_erp.png", _SRC, pct_axis=True, latest_fmt="{:.1%}"))

    # --- 3. Valuation panel: CAPE (left) vs ERP (right) -------------------- #
    cape_annual = cape.resample("YS").last()
    rendered["valuation_panel"] = dict(
        title="Are Stocks Expensive? CAPE vs the Implied ERP",
        sub="High CAPE + low ERP = richly priced. The two valuation lenses, aligned.",
        path=C.render_dual(cape_annual, "Shiller CAPE (left)", erp["implied_erp"], "Implied ERP (right)",
                           "Are Stocks Expensive? CAPE vs the Implied ERP",
                           "Shiller CAPE (left) vs Damodaran implied ERP (right), since 1960.",
                           out_dir / "valuation_panel.png", _SRC, right_pct=True))

    # --- 4. Fama-French factor cumulative returns -------------------------- #
    ff = C.parse_ff_factors(_MKT / "F-F_Research_Data_Factors_CSV.zip")
    mom = C.parse_ff_factors(_MKT / "F-F_Momentum_Factor_CSV.zip")
    factors = {
        "Market (Mkt-RF)": _cumulative(ff["Mkt-RF"]),
        "Size (SMB)": _cumulative(ff["SMB"]),
        "Value (HML)": _cumulative(ff["HML"]),
        "Momentum": _cumulative(mom[mom.columns[0]]),
    }
    rendered["factor_returns"] = dict(
        title="Fama-French Factors — Growth of $1 (log)",
        sub="Cumulative factor returns since 1926. Log scale — a straight line is a constant compound rate.",
        path=C.render_line(factors, "Fama-French Factors — Growth of $1 (log)",
                           "Cumulative long-short factor returns, 1926→ (log scale).",
                           out_dir / "factor_returns.png", _SRC, logy=True, latest_fmt="{:,.0f}x"))

    # --- 5. The value premium (HML) cumulative, with its drawdown --------- #
    hml = _cumulative(ff["HML"])
    rendered["value_premium"] = dict(
        title="The Value Premium (HML) Over Time",
        sub="Cumulative value-minus-growth return. The long plateau/drawdown since ~2007 is the 'value winter'.",
        path=C.render_line({"Value (HML) cumulative": hml}, "The Value Premium (HML) Over Time",
                           "Cumulative Fama-French HML (value − growth), 1926→.",
                           out_dir / "value_premium.png", _SRC, logy=True, latest_fmt="{:,.0f}x"))

    _render_gallery(rendered, out_dir / "index.html")
    return {k: v["path"] for k, v in rendered.items()}


def _render_gallery(rendered: dict[str, dict], out_path: Path) -> Path:
    cards = []
    for r in rendered.values():
        cards.append(
            f'<section><h2>{r["title"]}</h2><p class="sub">{r["sub"]}</p>'
            f'<img src="{Path(r["path"]).name}" alt="{r["title"]}"/></section>')
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><title>Top-Down Market Data — Charts</title>
<style>
 body {{ font-family:-apple-system,Segoe UI,Roboto,sans-serif; max-width:980px; margin:2rem auto; padding:0 1rem; color:#222; }}
 h1 {{ font-size:1.5rem; }} .meta {{ color:#777; font-size:.85rem; margin-bottom:2rem; }}
 section {{ margin:2.5rem 0; }} h2 {{ font-size:1.1rem; margin-bottom:.2rem; }}
 .sub {{ color:#555; font-size:.9rem; margin:0 0 .6rem; }}
 img {{ width:100%; border:1px solid #e2e2e2; border-radius:6px; }}
 a {{ color:#1F4E79; }}
</style></head><body>
<h1>Top-Down Market Data — Charts</h1>
<p class="meta">Valuation &amp; factor history from Shiller (CAPE), Damodaran (implied ERP) and
Ken French (factors). · <a href="../index.html">↑ workspace hub</a> · {len(cards)} charts</p>
{''.join(cards)}
</body></html>"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    out = build()
    for k, p in out.items():
        print(f"  {k}: {p}")
