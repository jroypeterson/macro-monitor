# Top-down market data

> Module of `macro_monitor` — the **valuation / factor-return / dispersion** layer. Where the core
> project tracks the economic cycle (FRED releases, leading indicators), this mirrors the free,
> long-history *market* datasets academics publish. Sibling: [`../damodaran/`](../damodaran/README.md)
> (risk-free rates, ERP, valuation multiples by market). **Phase 1: download + archive only.**

He refreshes vary by source (French monthly, AQR periodically, Shiller monthly-ish). The raw files
are archived to `data/raw/<date>/` + `data/latest/` (gitignored — local + Dropbox; the manifest is
tracked). Re-mirror with `python -m macro_monitor.cli market-fetch`.

## The three sources

### 1. Kenneth French Data Library (Dartmouth) — factor returns
The academic gold standard. Free CSVs (zipped), monthly & daily, going back to **1926**.
[data library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)

### 2. AQR Data Sets — multi-asset factor premia
The data behind AQR's published papers — value/momentum everywhere, a century of factor premia,
betting-against-beta, quality-minus-junk. Free Excel.
[datasets](https://www.aqr.com/Insights/Datasets)

### 3. Robert Shiller (Yale) — long-run valuation (CAPE)
Monthly S&P prices, earnings, dividends, CPI and long rates back to **1871**, plus the
cyclically-adjusted PE (CAPE / Shiller PE). Free Excel.
[online data](http://www.econ.yale.edu/~shiller/data.htm)

## Datasets mirrored (12)

| Source | Dataset | Period | Freq | What it is | Use case |
|---|---|---|---|---|---|
| Ken French | Fama-French **3 Factors** | 1926→ | monthly | Mkt-RF, SMB (size), HML (value), RF | Factor-return backbone; value/size cycles; risk-free history |
| Ken French | Fama-French **5 Factors** | 1963→ | monthly | + RMW (profitability), CMA (investment) | Quality & investment style cycles; modern attribution |
| Ken French | **Momentum** factor | 1926→ | monthly | Mom (UMD) | Momentum cycle; momentum crashes |
| Ken French | 3 Factors (**daily**) | 1926→ | daily | Daily Mkt-RF, SMB, HML, RF | High-frequency factor moves; daily dispersion/drawdown |
| Ken French | Portfolios on **Book-to-Market** | 1926→ | monthly | Decile returns sorted on B/M | Value **dispersion**; cheap-vs-expensive spread over time |
| AQR | **Century of Factor Premia** | 1920s→ | monthly | Value/momentum/carry/defensive across assets | Longest-horizon multi-asset factor history; regime context |
| AQR | **Value & Momentum Everywhere** | 1972→ | monthly | Value & momentum across markets/assets | Cross-market value/momentum (AQR flagship) |
| AQR | **Betting Against Beta** | 1926→ | monthly | Low-beta (BAB) factor by country | Low-vol / defensive factor cycle |
| AQR | **Quality Minus Junk** | 1926→ | monthly | Quality (QMJ) factor by country | Quality cycle; pairs with French RMW |
| AQR | **Devil in HML's Details** | 1926→ | monthly | HML built with timelier prices | Value-construction sensitivity |
| AQR | **Time Series Momentum** | 1985→ | monthly | Trend-following factor | Trend / CTA cycle context |
| Robert Shiller | **CAPE / `ie_data`** | 1871→ | monthly | S&P price, earnings, dividends, CPI, long rate, real values, **CAPE** | Long-run valuation; CAPE vs history; pairs with Damodaran ERP |

## Why these (vs the institutional shops)
The practitioners with the best *data* are academics who publish it free; the institutional shops
(ECRI, Rosenberg, Empirical Research Partners) guard theirs. French + AQR + Shiller are the free,
directly-usable backbone for top-down factor/valuation analysis.

## Phase 2 (in progress)
Parse the raw files into normalized time series + reports.

**Built:**
- **Factor period-return table** (`factor_returns.py`, `cli market-factors`): parses the Ken
  French monthly 5-factor + momentum CSVs from `data/latest/` and compounds them into a
  per-period table — latest month / QTD / YTD / trailing-12m / full-year 2025 — written to
  `readable/market/factor_returns_<YYYYMM>.md` (+ `_latest.md`). Answers "how did each factor
  do lately." Tests: `tests/test_factor_returns.py`.
- **Long-history factor + valuation charts** (`build_charts.py`, `cli market-charts`): cumulative
  factor growth, CAPE vs history, implied ERP, value premium.

**Still deferred:** AQR QMJ/BAB parsed into the return table (Excel; the table is FF-only today),
value-spread (B/M decile) **dispersion** over time, and cross-source panels (Shiller CAPE +
Damodaran implied ERP). Reuses the `ahead_of_curve` charting approach.
