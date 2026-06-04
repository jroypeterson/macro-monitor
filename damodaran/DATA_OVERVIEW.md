# Damodaran Data — Time-Series Overview

A reader's guide to **what is actually a time series** in Aswath Damodaran's data, versus what
is a yearly cross-sectional snapshot. Source: [pages.stern.nyu.edu/~adamodar](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html).
He refreshes everything in the **first two weeks of each January**. The full file catalog +
download status is in [`../readable/DAMODARAN_DATA_INVENTORY.md`](../readable/DAMODARAN_DATA_INVENTORY.md);
this file is the "which of these can I plot over time, and why would I" companion.

There are **two kinds** of data here:

1. **Genuine long-run time series** — a single file that already spans many decades. Plot directly.
2. **Annual cross-sections** (multiples/betas/margins by industry & region) — each download is a
   *current* snapshot. They become a time series only by **archiving each January's release** (we
   keep dated copies under `data/raw/<date>/`; Damodaran himself also keeps dated back-files to ~1999
   on his "archived data" page). Pull several years and you have a sector-valuation history.

---

## 1. Genuine long-run time series (plot directly)

| Dataset | File | Freq | Time period | What it is | Use cases |
|---|---|---|---|---|---|
| **Historical Returns: Stocks, Bonds, Bills** | `histretSP.xls` | Annual | **1928 → 2025** | Yearly total returns for the S&P 500, 3-month T-Bill, 10-year T-Bond, Baa corporates, real estate and gold — plus the **risk-free rate** history and the **realized** equity risk premium (stocks − bonds/bills). | The canonical long-run **risk-free rate** and **asset-class return** series; compute/observe the realized ERP; stocks-vs-bonds over any horizon; sanity-check long-run return assumptions. |
| **Historical Implied Equity Risk Premium** | `histimpl.xls` | Annual | **1960 → 2025** | By year: S&P 500 level, earnings, dividends + buybacks, the T-Bond (risk-free) rate, and the **forward-looking, market-implied ERP** and expected return Damodaran back-solves from prices. | The **forward ERP / market discount-rate** time series — is the market pricing in a high or low risk premium vs history? Gauge whether equities are cheap/expensive on a discount-rate basis; the ERP input for DCF valuation. |
| **Macroeconomic data** | `macro.xls` | Annual + Quarterly | Multi-decade (verify in file) | US T-Bond rate, GDP (real & nominal), CPI/inflation, trade-weighted dollar, and related macro series. | Risk-free + inflation backdrop alongside the valuation series; a supplementary macro reference (lighter than `macro_monitor`'s FRED feed). |

> Higher-frequency note: Damodaran also publishes a **monthly** implied ERP on his site (the "ERP by
> month" file). We currently mirror the **annual** `histimpl`; the monthly file can be added to the
> catalog if you want month-end ERP.

---

## 2. Annual cross-sections → time series via the January archive

Each of these is one current snapshot per download. Archive every January (our `damodaran-fetch`
keeps dated `data/raw/<date>/` copies) and you build an annual history. Damodaran's own archived-data
page holds dated versions back to roughly **1999**, so a ~25-year sector history is reconstructable.

| Dataset group | Coverage (per release) | How to get a time series | Use cases |
|---|---|---|---|
| **Valuation multiples** — PE/PEG, EV/EBITDA, EV/Sales, P/BV, P/S, by industry | 8 regions: US · Europe · Japan · Rest · Emerging · China · India · Global | Archive each Jan (or pull his dated back-files ~1999→) | Is a sector expensive vs **its own history**? Mean-reversion; cross-region valuation gaps (e.g. US vs Europe vs Japan PE over time); relative-value screens. |
| **Discount-rate inputs** — betas, total betas, cost of capital (WACC), tax rates, ratings/spreads | By industry × 8 regions (+ US ratings table) | Archive each Jan | Sector risk & cost-of-capital drift over time; build/justify discount rates; how risk premia by sector have moved. |
| **Fundamentals** — margins, ROE/ROIC, EVA, market cap | By industry × 8 regions | Archive each Jan | Sector **profitability trends**; margin expansion/compression; where returns-on-capital are rising/falling. |
| **Growth** — fundamental (equity & EBIT), historical growth | By industry × 8 regions | Archive each Jan | Sector growth-rate trends; reinvestment/quality inputs. |
| **Cash flows / capital structure** — capex, R&D, working capital, financing flows, debt details, leases, dividends/FCFE | By industry × 8 regions | Archive each Jan | Sector capital-intensity & payout trends; corporate-finance inputs for modeling. |
| **Country data** — equity risk premiums, default spreads, country statistics | By country (current snapshot) | Archive each Jan (+ his dated back-files) | **Country discount rates** over time; sovereign-risk trends; cross-country cost-of-equity. |

---

## Bottom line

- **Want a chart today, no archiving needed:** `histretSP` (risk-free + asset returns, 1928→) and
  `histimpl` (implied ERP, 1960→). These two carry the risk-free-rate and equity-risk-premium history.
- **Want sector/region valuation *over time*:** that's an archive play — keep running `damodaran-fetch`
  each January (and optionally backfill from his archived-data page), and the multiples/betas/margins
  become multi-year series. This is the natural **Phase 2** of this module.

_Update cadence: annual, first two weeks of January. Re-mirror with
`python -m macro_monitor.cli damodaran-fetch`._
