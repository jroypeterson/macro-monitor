"""Catalog of Aswath Damodaran's downloadable datasets.

Two shapes:
- STANDALONE: single-file datasets (several are genuine time series — histretSP, histimpl).
- FAMILIES: an industry dataset published once per region. The US file name sometimes
  differs from the regional stem (e.g. US "pedata.xls" but "peEurope.xls"), so each family
  declares `us_file` + `region_stem` explicitly.

`all_datasets()` expands these into one record per file with a stable id + full URL. The
downloader attempts every record and records 404s (not every family exists for every
region), so an over-broad region list is safe.
"""
from __future__ import annotations

from urllib.parse import quote

_DATASETS = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/"
_PC = "https://pages.stern.nyu.edu/~adamodar/pc/"

# (display name, url suffix). US is the base file; the rest append the suffix to the stem.
REGIONS = [
    ("US", ""), ("Europe", "Europe"), ("Japan", "Japan"), ("Rest of World", "Rest"),
    ("Emerging Markets", "emerg"), ("China", "China"), ("India", "India"), ("Global", "Global"),
]

# Single-file datasets. `base` defaults to the /datasets/ dir.
STANDALONE = [
    dict(id="histretSP", name="Historical Returns: S&P 500, T.Bonds, T.Bills, Baa", category="returns",
         file="histretSP.xls", timeseries=True, relevance="high",
         desc="Annual returns 1928-present — the risk-free (T.Bill/T.Bond) and equity return series."),
    dict(id="histimpl", name="Historical Implied Equity Risk Premium", category="erp",
         file="histimpl.xls", timeseries=True, relevance="high",
         desc="Implied ERP + risk-free rate + S&P earnings/dividends, annual 1960-present."),
    dict(id="ctryprem", name="Country Equity Risk Premiums & default spreads", category="country_risk",
         file="ctryprem.xlsx", relevance="high", desc="ERP + country risk premium by country (current)."),
    dict(id="countrystats", name="Country statistics (pricing multiples by country)", category="country",
         file="countrystats.xls", relevance="high"),
    dict(id="macro", name="Macroeconomic data (risk-free rates, inflation, spreads)", category="macro",
         file="macro.xls", timeseries=True, relevance="high"),
    dict(id="ratings", name="Ratings, interest-coverage ratios & default spreads", category="discount_rate",
         file="ratings.xls", base=_PC, relevance="medium"),
    dict(id="countrytaxrates", name="Country tax rates", category="discount_rate",
         file="countrytaxrates.xls", relevance="medium"),
    dict(id="mktcapmult", name="Pricing multiples by market-cap class (US)", category="multiples",
         file="mktcapmult.xlsx", relevance="medium"),
    dict(id="mktcaprisk", name="Risk by market-cap class (US)", category="discount_rate",
         file="mktcaprisk.xlsx", relevance="low"),
    dict(id="macrodur", name="Macro data (duration series)", category="macro",
         file="macrodur.xls", base=_PC, relevance="low"),
]

# Industry families published per region. us_file = the US file; region_stem + suffix = the rest.
FAMILIES = [
    # --- valuation multiples (the user's core interest) ---
    dict(id="pe", name="PE & PEG ratios by industry", category="multiples", relevance="high",
         us_file="pedata.xls", region_stem="pe"),
    dict(id="pbv", name="Price-to-Book by industry", category="multiples", relevance="high",
         us_file="pbvdata.xls", region_stem="pbv"),
    dict(id="ps", name="Price-to-Sales by industry", category="multiples", relevance="high",
         us_file="psdata.xls", region_stem="ps"),
    dict(id="vebitda", name="EV/EBITDA, EV/EBIT, EV/Sales by industry", category="multiples", relevance="high",
         us_file="vebitda.xls", region_stem="vebitda"),
    # --- discount-rate inputs ---
    dict(id="betas", name="Betas (levered/unlevered) by industry", category="discount_rate", relevance="medium",
         us_file="betas.xls", region_stem="beta"),
    dict(id="totalbeta", name="Total betas by industry", category="discount_rate", relevance="low",
         us_file="totalbeta.xls", region_stem="totalbeta"),
    dict(id="wacc", name="Cost of capital by industry", category="discount_rate", relevance="medium",
         us_file="wacc.xls", region_stem="wacc"),
    dict(id="taxrate", name="Effective vs marginal tax rates by industry", category="discount_rate", relevance="low",
         us_file="taxrate.xls", region_stem="taxrate"),
    # --- fundamentals / profitability ---
    dict(id="margin", name="Margins by industry", category="fundamentals", relevance="medium",
         us_file="margin.xls", region_stem="margin"),
    dict(id="roe", name="ROE & return on capital by industry", category="fundamentals", relevance="medium",
         us_file="roe.xls", region_stem="roe"),
    dict(id="EVA", name="EVA & return spreads by industry", category="fundamentals", relevance="low",
         us_file="EVA.xls", region_stem="EVA"),
    dict(id="mktcap", name="Market capitalization by industry", category="fundamentals", relevance="low",
         us_file="MktCap.xls", region_stem="MktCap"),
    # --- growth ---
    dict(id="fundgr", name="Fundamental growth (equity) by industry", category="growth", relevance="low",
         us_file="fundgr.xls", region_stem="fundgr"),
    dict(id="fundgrEB", name="Fundamental growth (EBIT) by industry", category="growth", relevance="low",
         us_file="fundgrEB.xls", region_stem="fundgrEB"),
    dict(id="histgr", name="Historical growth by industry", category="growth", relevance="low",
         us_file="histgr.xls", region_stem="histgr"),
    # --- cash flows ---
    dict(id="capex", name="Capital expenditures by industry", category="cashflows", relevance="low",
         us_file="capex.xls", region_stem="capex"),
    dict(id="margin_rd", name="R&D by industry", category="cashflows", relevance="low",
         us_file="R&D.xls", region_stem="R&D"),
    dict(id="goodwill", name="Goodwill by industry", category="cashflows", relevance="low",
         us_file="goodwill.xls", region_stem="goodwill"),
    dict(id="wcdata", name="Working capital by industry", category="cashflows", relevance="low",
         us_file="wcdata.xls", region_stem="wcdata"),
    dict(id="finflows", name="Financing flows by industry", category="cashflows", relevance="low",
         us_file="finflows.xls", region_stem="finflows"),
    # --- dividends / payout ---
    dict(id="divfcfe", name="Dividends & FCFE by industry", category="payout", relevance="low",
         us_file="divfcfe.xls", region_stem="divfcfe"),
    dict(id="divfund", name="Dividend fundamentals by industry", category="payout", relevance="low",
         us_file="divfund.xls", region_stem="divfund"),
    # --- capital structure ---
    dict(id="debtdetails", name="Debt details by industry", category="capital_structure", relevance="low",
         us_file="debtdetails.xls", region_stem="debtdetails"),
    dict(id="dbtfund", name="Debt fundamentals by industry", category="capital_structure", relevance="low",
         us_file="dbtfund.xls", region_stem="dbtfund"),
    dict(id="leaseeffect", name="Lease effects by industry", category="capital_structure", relevance="low",
         us_file="leaseeffect.xls", region_stem="leaseeffect"),
    # --- other ---
    dict(id="inshold", name="Insider & institutional holdings by industry", category="governance", relevance="low",
         us_file="inshold.xls", region_stem="inshold"),
    dict(id="employee", name="Employee statistics by industry", category="other", relevance="low",
         us_file="Employee.xls", region_stem="Employee"),
    dict(id="dollar", name="Dollar-value measures by industry", category="other", relevance="low",
         us_file="DollarUS.xls", region_stem="Dollar"),
    dict(id="optvar", name="Option-pricing variance by industry", category="other", relevance="low",
         us_file="optvar.xls", region_stem="optvar"),
]


def _url(base: str, file: str) -> str:
    return base + quote(file)  # quote handles the "&" in R&D filenames


def all_datasets() -> list[dict]:
    """Expand STANDALONE + FAMILIES into one record per downloadable file."""
    out: list[dict] = []
    for d in STANDALONE:
        base = d.get("base", _DATASETS)
        out.append({
            "id": d["id"], "family": d["id"], "name": d["name"], "category": d["category"],
            "region": "—", "relevance": d.get("relevance", "low"),
            "timeseries": d.get("timeseries", False), "file": d["file"],
            "url": _url(base, d["file"]), "desc": d.get("desc", ""),
        })
    for f in FAMILIES:
        for region_name, suffix in REGIONS:
            file = f["us_file"] if suffix == "" else f"{f['region_stem']}{suffix}.xls"
            out.append({
                "id": f"{f['id']}_{suffix or 'US'}", "family": f["id"], "name": f["name"],
                "category": f["category"], "region": region_name,
                "relevance": f.get("relevance", "low"), "timeseries": False,
                "file": file, "url": _url(_DATASETS, file), "desc": "",
            })
    return out
