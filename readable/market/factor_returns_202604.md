# Fundamental factor performance

_Fama-French 5 factors + momentum · monthly returns compounded per period · data through **Apr 2026** (Ken French Data Library, ~1-2 month publication lag)._

| Factor | Latest mo | QTD | 2026 YTD | Trailing 12m | 2025 FY |
|---|---|---|---|---|---|
| Market (excess) | +9.9% | +9.9% | +4.1% | +26.1% | +12.8% |
| Size (SMB) | +0.4% | +0.4% | +5.1% | +6.5% | -7.9% |
| Value (HML) | -1.3% | -1.3% | +8.8% | +9.2% | +6.5% |
| Profitability (RMW) | -4.3% | -4.3% | -2.8% | -11.2% | -10.5% |
| Investment (CMA) | -3.8% | -3.8% | +2.8% | +1.1% | -4.9% |
| Momentum (UMD) | +9.6% | +9.6% | +18.3% | +13.1% | -2.2% |
| Risk-free (1mo T-bill) | +0.3% | +0.3% | +1.2% | +4.0% | +4.3% |

**Reading it:** each cell is the factor's cumulative return over the period (long-minus-short premium, in percent). Market is the excess return over the risk-free rate; Size/Value/Profitability/Investment/Momentum are the classic long-short premia. A negative Value or Momentum number means that style detracted over the window.

_Source: `market/data/latest/` (mirrored via `cli market-fetch`). AQR QMJ / BAB are mirrored too but not yet parsed into this table — a follow-on. Regenerate: `python -m macro_monitor.cli market-factors`._
