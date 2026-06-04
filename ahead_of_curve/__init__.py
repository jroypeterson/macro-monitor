"""Ahead of the Curve (Joseph Ellis) chart recreation.

Renders the book's signature charts — year-over-year rate-of-change lines with
shaded bear-market bands — from FRED data, reusing macro_monitor's FRED client,
cache, and matplotlib style. Phase 2 of the Ahead-of-the-Curve work (Phase 1 was
the macro data inventory under ``data_inventory/``).

Config-driven: ``figures.yaml`` declares the charts, ``bear_markets.yaml`` the shaded
bands. Build with ``python -m macro_monitor.cli ahead-of-curve`` (or
``python -m macro_monitor.ahead_of_curve.build``).
"""
