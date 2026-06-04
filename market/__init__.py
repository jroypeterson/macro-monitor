"""Top-down market data — the valuation / factor-return / dispersion layer of macro_monitor.

Where macro_monitor's core tracks the economic cycle (FRED releases, leading indicators),
this sub-package mirrors the free, long-history *market* datasets that academics publish:

- Kenneth French Data Library (Fama-French factor returns, 1926→)
- AQR Data Sets (multi-asset factor premia, value/momentum everywhere, BAB, QMJ, …)
- Robert Shiller (CAPE / long S&P prices, earnings, dividends, rates, 1871→)

Sibling: `macro_monitor/damodaran/` (risk-free rates, ERP, valuation multiples by market).
Together these are the "top-down market data" scope. Phase 1 (this module): catalog +
download/archive the raw files. Charts/time-series parsing is a later phase.

CLI: ``python -m macro_monitor.cli market-fetch`` / ``market-inventory``.
"""
