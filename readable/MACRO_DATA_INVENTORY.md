# Macro Data Inventory

_Generated from `data_inventory/datasets.yaml` — 21 datasets (19 reachable via a single FRED id). Schema: `data_inventory/SCHEMA.md`. Edit the YAML, not this file._

_Seeded from the "Ahead of the Curve" (Joseph Ellis) chart-recreation work. Ellis's lens is year-over-year rate of change (`yoy_roc`); real consumer spending (real PCE) is the leading indicator the rest of the cycle follows._

## ⏸ Staged (FRED path confirmed) (18)

| Dataset | Publisher | Category | Access (method · detail · effort) | Cadence · lag | Transform | Ellis fig(s) | Relevance |
|---|---|---|---|---|---|---|---|
| **Market Yield on 10-Year Treasury (constant maturity)** | Federal Reserve (H.15, via FRED) | rates | fred · `GS10` · trivial | monthly · ~1 week | raw | 13-3 | high — long-rate-vs-stock-market relationship (Fig 13-3) |
| **Average Hourly Earnings, Production & Nonsupervisory Employees, Total Private** | U.S. BLS (via FRED) | earnings | fred · `AHETPI` · trivial | monthly · ~1-3 weeks | yoy_roc | 10-4, 10-7, 10-9, 10-10, 11-11 | high — real hourly earnings YoY drives spending power (Figs 10-x) |
| **Civilian Employment Level** | U.S. BLS (via FRED) | labor | fred · `CE16OV` · trivial | monthly · ~1-3 weeks (employment situation) | yoy_roc | 10-9, 11-3, 11-11 | high — employment YoY follows consumer spending |
| **Manufacturers' New Orders: Nondefense Capital Goods ex-Aircraft (core capex)** | U.S. Census (via FRED) | investment | fred · `NEWORDER` · trivial | monthly · ~5 weeks | yoy_roc | (monthly proxy for 7-5 / 7-7) | medium — higher-frequency capex read than the quarterly BEA series |
| **Consumer Price Index, All Urban Consumers, All Items (CPI-U)** | U.S. BLS (via FRED) | prices | fred · `CPIAUCSL` · trivial | monthly · ~2 weeks | yoy_roc | (deflator for 10-4/10-7/10-10) | high — required to compute the book's REAL hourly earnings series |
| **Federal Funds Effective Rate** | Federal Reserve (H.15, via FRED) | rates | fred · `FEDFUNDS` · trivial | monthly · ~1 week | raw | 12-2, 13-2 | high — policy-rate-vs-bear-market relationship |
| **Industrial Production: Manufacturing (NAICS)** | Federal Reserve (G.17, via FRED) | production | fred · `IPMAN` · trivial | monthly · ~2-3 weeks | yoy_roc | 7-3, 7-5 | high — a coincident output series that follows real PCE |
| **NBER-based Recession Indicators (USREC)** | NBER / Federal Reserve (via FRED) | reference | fred · `USREC` · trivial | monthly · NBER dates declared with long lag (~6-18 months after the fact) | raw | (optional shaded bands on any figure) | medium — recession-band overlay toggle (distinct from bear-market bands) |
| **PCE Chain-type Price Index** | U.S. BEA (via FRED) | prices | fred · `PCEPI` · trivial | monthly · ~1 month | yoy_roc | (inflation context; 12-4) | medium — inflation backdrop + deflator |
| **Bank Prime Loan Rate** | Federal Reserve (H.15, via FRED) | rates | fred · `MPRIME` · trivial | monthly · ~1 week | raw | (rates context, ch. 12-13) | low — borrowing-cost context, redundant with fed funds |
| **Real Gross Domestic Product** | U.S. BEA (via FRED) | output | fred · `GDPC1` · trivial | quarterly · ~1 month after quarter-end (advance), revised twice | yoy_roc | 4-1 | high — the growth/recession backdrop in Fig 4-1 |
| **Real Private Nonresidential Fixed Investment** | U.S. BEA (via FRED) | investment | fred · `PNFIC1` · trivial | quarterly · ~1 month after quarter-end | yoy_roc | 7-5, 7-7 | high — capex YoY famously lags PCE YoY (the book's lead/lag overlay) |
| **Real Personal Consumption Expenditures** | U.S. BEA (via FRED) | consumption | fred · `PCEC96` · trivial | monthly · ~1 month | yoy_roc | 7-3, 7-7, 8-4, 10-7, 11-3, 11-6, 11-11 | high — the leading indicator the whole framework hangs on |
| **Personal Saving Rate** | U.S. BEA (via FRED) | consumption | fred · `PSAVERT` · trivial | monthly · ~1 month | raw | Supplemental (saving rate) | medium — saving/spending tradeoff context |
| **All Sectors — Debt Securities & Loans (total domestic debt, Z.1)** | Federal Reserve (Z.1 Financial Accounts, via FRED) | debt, credit | fred · `TCMDO` · trivial | quarterly · ~2-3 months | yoy_roc | 10-9 (borrowing) | medium — borrowing/credit growth alongside employment & earnings (Fig 10-9) |
| **University of Michigan: Consumer Sentiment** | U. Michigan Surveys of Consumers (via FRED) | sentiment | fred · `UMCSENT (1978+), UMCSENT1 (1952-1977)` · low | monthly · ~0-2 weeks (prelim mid-month, final end-month) | raw | 9-3 | medium — sentiment as a coincident/soft indicator (Fig 9-3) |
| **Civilian Unemployment Rate** | U.S. BLS (via FRED) | labor | fred · `UNRATE` · trivial | monthly · ~1-3 weeks | raw | 11-6, 11-8 | high — classic recession/bear confirm in Figs 11-6/11-8 |
| **S&P 500 Price Index** | S&P Dow Jones Indices (via FRED / yfinance) | markets | fred · `SP500 (FRED, last ~10y only); ^GSPC via yfinance for full history` · low | daily · real-time / EOD | raw | 4-1, 8-4, 10-10, 11-8, 13-2, 13-3 (the market line on every overlay) | high — the stock-market series the book overlays everything against |

## 🔎 Candidate (3)

| Dataset | Publisher | Category | Access (method · detail · effort) | Cadence · lag | Transform | Ellis fig(s) | Relevance |
|---|---|---|---|---|---|---|---|
| **Conference Board Consumer Confidence Index** | The Conference Board | sentiment | manual_download · `press release / paid data feed` · high | monthly · ~last Tuesday of month | raw | 9-3 | medium — the book pairs it with UMich; UMich substitutes acceptably |
| **Discount Rate for the United States (historical)** | Federal Reserve (via FRED) | rates | fred · `INTDSRUSM193N` · trivial | monthly · n/a (historical) | raw | (12-2 context) | low — historical only; superseded by fed funds |
| **S&P 500 Operating Earnings Per Share (estimates + actuals)** | S&P Dow Jones Indices | markets | excel_download · `sp-500-eps-est.xlsx` · moderate | quarterly · rolling (forward estimates + trailing actuals) | yoy_roc | (corporate earnings vs spending) | medium — earnings YoY vs the cycle; the .xlsx parse is the effort |
