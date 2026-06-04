"""Aswath Damodaran data archive.

Mirrors the downloadable datasets from Prof. Aswath Damodaran's NYU Stern data page
(pages.stern.nyu.edu/~adamodar) — risk-free rates & equity risk premiums, historical
returns, and valuation multiples (PE, EV/EBITDA, P/BV, P/S) across equity markets
(US, Europe, Japan, Rest, Emerging, China, India, Global), plus the corporate-finance
inputs he publishes. He refreshes the data in the first two weeks of each January.

Phase 1 (this module): inventory every dataset + download/archive the raw .xls files,
keeping a dated raw archive + a `latest/` mirror and a manifest. Charting/time-series
parsing is a later phase.

CLI: ``python -m macro_monitor.cli damodaran-fetch`` / ``damodaran-inventory``.
"""
