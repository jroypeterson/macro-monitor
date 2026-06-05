"""Federal fiscal view — government spending overall + the healthcare wedge.

Answers, from FRED (no key beyond FRED_API_KEY):
  1. Is the government spending more overall?  → federal outlays/receipts/deficit
     as a share of GDP over time.
  2. What has federal healthcare spending been? → Medicare + Medicaid in $ and as
     a share of total federal spending and of GDP.

Forward CBO baseline projections are a follow-up (PDF/structured per report).
Renders readable/fiscal/index.html (mirrors the market-charts gallery).

Run: ``python -m macro_monitor.cli fiscal``.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .collectors.fred import FREDClient
from .market import charts as C

_OUT = Path(__file__).parent / "readable" / "fiscal"
_SRC = "Source: FRED — federal net outlays/receipts (OMB, % of GDP, annual); federal current expenditures, Medicare, Medicaid & GDP (BEA NIPA, quarterly)."

# OMB unified-budget aggregates (annual, % of GDP)
OUTLAYS_PCT_GDP = "FYONGDA188S"
RECEIPTS_PCT_GDP = "FYFRGDA188S"
DEFICIT_PCT_GDP = "FYFSGDA188S"
# BEA NIPA federal current expenditures + the two big health programs (quarterly $B)
FED_EXPEND = "FGEXPND"
MEDICARE = "W824RC1Q027SBEA"
MEDICAID = "W729RC1Q027SBEA"
GDP = "GDP"


def build(out_dir: Path = _OUT) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    fred = FREDClient()
    g = lambda sid: fred.get_observations(sid).dropna()  # noqa: E731

    outlays, receipts, deficit = g(OUTLAYS_PCT_GDP), g(RECEIPTS_PCT_GDP), g(DEFICIT_PCT_GDP)
    fed_exp, medicare, medicaid, gdp = g(FED_EXPEND), g(MEDICARE), g(MEDICAID), g(GDP)
    health = (medicare + medicaid).dropna()  # aligned on the shared quarterly index

    rendered: dict[str, dict] = {}

    # --- 1. Is the government spending more overall? ----------------------- #
    rendered["outlays_gdp"] = dict(
        title="Federal Spending, Receipts & Deficit (% of GDP)",
        sub="Total federal outlays vs receipts as a share of GDP; the gap is the deficit. "
            f"Latest outlays {outlays.iloc[-1]:.1f}% of GDP ({outlays.index[-1]:%Y}).",
        path=C.render_line(
            {"Outlays": outlays, "Receipts": receipts, "Deficit": deficit},
            "Federal Spending, Receipts & Deficit (% of GDP)",
            "OMB unified-budget basis, annual. Outlays above receipts = deficit.",
            out_dir / "outlays_gdp.png", _SRC, latest_fmt="{:.1f}%"),
    )

    # --- 2. Federal healthcare spending in dollars ------------------------ #
    rendered["health_dollars"] = dict(
        title="Federal Health Spending — Medicare & Medicaid ($B)",
        sub="The two largest federal health programs, quarterly (SAAR). "
            f"Latest: Medicare ${medicare.iloc[-1]:,.0f}B, Medicaid ${medicaid.iloc[-1]:,.0f}B.",
        path=C.render_line(
            {"Medicare": medicare, "Medicaid (federal share)": medicaid,
             "Medicare + Medicaid": health},
            "Federal Health Spending — Medicare & Medicaid ($B)",
            "BEA NIPA federal current expenditures, quarterly $B (annual rate).",
            out_dir / "health_dollars.png", _SRC, latest_fmt="${:,.0f}B"),
    )

    # --- 3. Healthcare as a share of spending and of GDP ------------------ #
    share_exp = (health / fed_exp * 100).dropna()
    share_gdp = (health / gdp * 100).dropna()
    rendered["health_share"] = dict(
        title="Federal Health Spending as a Share",
        sub="Medicare + Medicaid as a % of total federal spending and of GDP — the growing wedge. "
            f"Latest: {share_exp.iloc[-1]:.1f}% of federal spending, {share_gdp.iloc[-1]:.1f}% of GDP.",
        path=C.render_line(
            {"% of federal spending": share_exp, "% of GDP": share_gdp},
            "Federal Health Spending as a Share",
            "Medicare + Medicaid ÷ total federal current expenditures (and ÷ GDP), quarterly.",
            out_dir / "health_share.png", _SRC, latest_fmt="{:.1f}%"),
    )

    _render_gallery(rendered, out_dir / "index.html")
    return {k: v["path"] for k, v in rendered.items()}


def _render_gallery(rendered: dict[str, dict], out_path: Path) -> Path:
    cards = []
    for r in rendered.values():
        cards.append(
            f'<section><h2>{r["title"]}</h2><p class="sub">{r["sub"]}</p>'
            f'<img src="{Path(r["path"]).name}" alt="{r["title"]}"/></section>')
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><title>Government & Healthcare Spending</title>
<style>
 body {{ font-family:-apple-system,Segoe UI,Roboto,sans-serif; max-width:980px; margin:2rem auto; padding:0 1rem; color:#222; }}
 h1 {{ font-size:1.5rem; }} .meta {{ color:#777; font-size:.85rem; margin-bottom:2rem; }}
 section {{ margin:2.5rem 0; }} h2 {{ font-size:1.1rem; margin-bottom:.2rem; }}
 .sub {{ color:#555; font-size:.9rem; margin:0 0 .6rem; }}
 img {{ width:100%; border:1px solid #e2e2e2; border-radius:6px; }}
 a {{ color:#1F4E79; }}
</style></head><body>
<h1>Government &amp; Healthcare Spending</h1>
<p class="meta">Is federal spending rising, and how big is the healthcare wedge? Federal outlays
&amp; the Medicare/Medicaid share, from FRED (OMB/BEA). Forward CBO projections are a follow-up. ·
<a href="../index.html">↑ workspace hub</a> · {len(cards)} charts</p>
{''.join(cards)}
</body></html>"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    for k, p in build().items():
        print(f"  {k}: {p}")
