"""Catalog of the free top-down market datasets we mirror (Ken French, AQR, Shiller).

Each record carries the download URL plus human metadata (period, what it is, use case)
so the README/inventory can be rendered straight from here. The downloader attempts every
record and records 404s, so a slightly-wrong AQR filename is non-fatal.
"""
from __future__ import annotations

FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
AQR = "https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/"
SHILLER = "http://www.econ.yale.edu/~shiller/data/"

# id, source, name, category, freq, period, file, url, what, use, relevance
DATASETS = [
    # ---------------- Kenneth French Data Library ----------------
    dict(id="ff_3factor_monthly", source="Ken French", name="Fama-French 3 Factors (monthly + annual)",
         category="factors", freq="monthly", period="1926→", file="F-F_Research_Data_Factors_CSV.zip",
         url=FRENCH + "F-F_Research_Data_Factors_CSV.zip", relevance="high",
         what="Mkt-RF (market excess return), SMB (size), HML (value), RF (risk-free).",
         use="The academic factor-return backbone; value-vs-growth & size cycles; risk-free history."),
    dict(id="ff_5factor_monthly", source="Ken French", name="Fama-French 5 Factors (2x3, monthly)",
         category="factors", freq="monthly", period="1963→", file="F-F_Research_Data_5_Factors_2x3_CSV.zip",
         url=FRENCH + "F-F_Research_Data_5_Factors_2x3_CSV.zip", relevance="high",
         what="Adds RMW (profitability) and CMA (investment) to the 3 factors.",
         use="Profitability/quality & investment style cycles; modern factor attribution."),
    dict(id="ff_momentum_monthly", source="Ken French", name="Momentum Factor (monthly)",
         category="factors", freq="monthly", period="1926→", file="F-F_Momentum_Factor_CSV.zip",
         url=FRENCH + "F-F_Momentum_Factor_CSV.zip", relevance="high",
         what="The momentum (Mom / UMD) factor return.",
         use="Momentum cycle; momentum crashes; complete the 4/6-factor set."),
    dict(id="ff_3factor_daily", source="Ken French", name="Fama-French 3 Factors (daily)",
         category="factors", freq="daily", period="1926→", file="F-F_Research_Data_Factors_daily_CSV.zip",
         url=FRENCH + "F-F_Research_Data_Factors_daily_CSV.zip", relevance="medium",
         what="Daily Mkt-RF, SMB, HML, RF.",
         use="Higher-frequency factor moves; daily dispersion / drawdown analysis."),
    dict(id="ff_portfolios_beme", source="Ken French", name="Portfolios Formed on Book-to-Market",
         category="factors", freq="monthly", period="1926→", file="Portfolios_Formed_on_BE-ME_CSV.zip",
         url=FRENCH + "Portfolios_Formed_on_BE-ME_CSV.zip", relevance="medium",
         what="Decile portfolio returns sorted on book-to-market (value spectrum).",
         use="Cross-sectional value dispersion; cheap-vs-expensive spread over time."),

    # ---------------- AQR Data Sets ----------------
    dict(id="aqr_century", source="AQR", name="Century of Factor Premia (monthly)",
         category="factors", freq="monthly", period="1920s→", file="Century-of-Factor-Premia-Monthly.xlsx",
         url=AQR + "Century-of-Factor-Premia-Monthly.xlsx", relevance="high",
         what="Value, momentum, carry, defensive across asset classes over ~a century.",
         use="Longest-horizon multi-asset factor history; regime/cycle context."),
    dict(id="aqr_vme", source="AQR", name="Value and Momentum Everywhere (monthly)",
         category="factors", freq="monthly", period="1972→", file="Value-and-Momentum-Everywhere-Factors-Monthly.xlsx",
         url=AQR + "Value-and-Momentum-Everywhere-Factors-Monthly.xlsx", relevance="high",
         what="Value & momentum factor returns across markets & asset classes.",
         use="Cross-market value/momentum; the AQR flagship dataset."),
    dict(id="aqr_bab", source="AQR", name="Betting Against Beta — Equity Factors (monthly)",
         category="factors", freq="monthly", period="1926→", file="Betting-Against-Beta-Equity-Factors-Monthly.xlsx",
         url=AQR + "Betting-Against-Beta-Equity-Factors-Monthly.xlsx", relevance="medium",
         what="The low-beta (BAB) factor by country.",
         use="Low-volatility / defensive factor cycle."),
    dict(id="aqr_qmj", source="AQR", name="Quality Minus Junk — Factors (monthly)",
         category="factors", freq="monthly", period="1926→", file="Quality-Minus-Junk-Factors-Monthly.xlsx",
         url=AQR + "Quality-Minus-Junk-Factors-Monthly.xlsx", relevance="medium",
         what="The quality (QMJ) factor by country.",
         use="Quality factor cycle; pairs with French RMW."),
    dict(id="aqr_devil_hml", source="AQR", name="The Devil in HML's Details — Factors (monthly)",
         category="factors", freq="monthly", period="1926→", file="The-Devil-in-HMLs-Details-Factors-Monthly.xlsx",
         url=AQR + "The-Devil-in-HMLs-Details-Factors-Monthly.xlsx", relevance="low",
         what="HML built with more timely price data (HML Devil).",
         use="Value-factor construction sensitivity."),
    dict(id="aqr_tsmom", source="AQR", name="Time Series Momentum — Factors (monthly)",
         category="factors", freq="monthly", period="1985→", file="Time-Series-Momentum-Factors-Monthly.xlsx",
         url=AQR + "Time-Series-Momentum-Factors-Monthly.xlsx", relevance="low",
         what="Trend-following (time-series momentum) factor.",
         use="Trend/CTA cycle context."),

    # ---------------- Robert Shiller ----------------
    dict(id="shiller_cape", source="Robert Shiller", name="U.S. Stock Market Data & CAPE (ie_data)",
         category="valuation", freq="monthly", period="1871→", file="ie_data.xls",
         url=SHILLER + "ie_data.xls", relevance="high",
         what="Monthly S&P price, earnings, dividends, CPI, long interest rate, real values, and the "
              "cyclically-adjusted PE (CAPE / Shiller PE).",
         use="The long-run valuation series — CAPE vs history; mean-reversion; pairs with Damodaran ERP."),
]
