"""Prediction-market odds lane for macro_monitor.

Pulls forward-looking crowd odds from Polymarket (keyless Gamma API) for a
curated, lane-organized set of markets and renders a 3-lane rundown (Macro /
Healthcare / Aggregated) to a readable HTML panel + a Slack post to
#prediction-markets.

See PREDICTION_MARKETS.md (source inventory + design) and
PREDMARKET_HC_WATCHLIST.md (the curated market list).
"""
