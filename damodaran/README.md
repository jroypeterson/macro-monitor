# Damodaran data archive

> Module of `macro_monitor`. Mirrors Prof. Aswath Damodaran's NYU Stern datasets and keeps
> a dated raw archive + inventory. **Phase 1 (download + inventory) only — charting is later.**

## What it does
Downloads the downloadable `.xls` datasets from
[pages.stern.nyu.edu/~adamodar](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html)
— risk-free rates & equity risk premiums, historical returns, and valuation multiples
(PE, EV/EBITDA, P/BV, P/S) across equity markets (US · Europe · Japan · Rest · Emerging ·
China · India · Global), plus the corporate-finance inputs he publishes. He refreshes the
data in the **first two weeks of each January**.

## Layout
- `datasets.py` — the catalog (`all_datasets()` → one record per file; 242 files).
- `download.py` — polite downloader (real UA + contact, inter-request delay, retry/backoff,
  404s recorded not fatal). Writes `data/raw/<date>/` + `data/latest/` + `manifest_latest.json`.
- `render.py` — renders `../readable/DAMODARAN_DATA_INVENTORY.md`.

The raw `.xls` archive (`data/raw/`, `data/latest/`) is **gitignored** — it's mirrored
locally + Dropbox-synced, refreshed annually. `manifest_latest.json` is tracked.

## Usage
```
python -m macro_monitor.cli damodaran-fetch                 # download all 242 files
python -m macro_monitor.cli damodaran-fetch --relevance high,medium   # just the core
python -m macro_monitor.cli damodaran-inventory             # re-render the inventory
```

## Marquee (genuine time series)
- `histretSP.xls` — annual S&P 500 / T.Bond / T.Bill / Baa returns, 1928→ (the risk-free series).
- `histimpl.xls` — historical implied equity risk premium + risk-free, 1960→.
- `macro.xls` — macro / risk-free rate series.

Per-industry/region multiples are **annual cross-sections**; their time series deepens as we
archive each January's release. Phase 2 (deferred) parses these into normalized time series + charts.
