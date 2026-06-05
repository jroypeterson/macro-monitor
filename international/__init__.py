"""International macro — Phase 2.

A separate "Global macro" layer alongside the US release feed: latest CPI,
GDP, policy rate and labour readings for the eurozone, UK, China and Japan,
pulled from each region's authoritative source and surfaced as a weekly
Slack digest + an HTML dashboard panel (kept apart from the US Tier A/B
discipline by design).

Sources (native where usable):
  eurozone — Eurostat SDMX (JSON-stat) + ECB Data Portal (SDMX-JSON)
  uk       — ONS time-series `/data` JSON + Bank of England IADB CSV
  china    — OECD SDMX-JSON (NBS blocks programmatic access; OECD aggregates)
  japan    — e-Stat JSON (needs a free ESTAT_APP_ID) + BoJ CSV
"""
