"""Long S&P 500 monthly history via yfinance.

Yahoo's monthly ^GSPC interval only serves ~1985+, but the daily series reaches back to
1927 — so we pull daily and resample to month-start (last close in each month) to align
with the FRED monthly economic series. The figures reference this under fred id ``GSPC``.
"""
from __future__ import annotations

import pandas as pd

SP500_KEY = "GSPC"  # the fetched-dict key the figures reference (fred: GSPC)


def fetch_sp500_monthly(start: str = "1927-01-01") -> pd.Series:
    """Month-start-indexed S&P 500 close, full history. Raises if yfinance/Yahoo fail
    (the caller warns and renders S&P figures without the line / skips them)."""
    import yfinance as yf

    df = yf.download("^GSPC", start=start, interval="1d", progress=False, auto_adjust=True)
    close = df["Close"]
    if hasattr(close, "columns"):  # yfinance returns a single-col frame under a MultiIndex
        close = close.iloc[:, 0]
    monthly = close.dropna().resample("MS").last()
    monthly.name = SP500_KEY
    return monthly
