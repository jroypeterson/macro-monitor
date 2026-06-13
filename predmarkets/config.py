"""Curated tracked-market specs for the prediction-market rundown.

Each market is resolved at run time by a stable search `query` + a title
`match` substring (Polymarket appends drifting numeric suffixes to slugs, and
dated markets roll over — e.g. "Fed Decision in June" → "...July" — so we never
hardcode slugs). The resolver picks the highest-volume ACTIVE event whose title
contains `match`. `kind` (binary vs multi) is auto-detected from the resolved
event, not declared here.

Lanes: "macro" + "healthcare". Biotech FDA-approval catalysts are lane
"healthcare" with `biotech=True` so they also route to the biotech catalyst
channel later (PROJECT_TRIAGE #13/#14). The "aggregated" lane is derived: it
pulls the lead number from each `headline=True` market.

Curated per JP 2026-06-12 (see PREDMARKET_HC_WATCHLIST.md).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# #prediction-markets — JP created it 2026-06-12. Env override wins (CI/.env).
PREDMARKET_CHANNEL_ID = os.environ.get("SLACK_PREDMARKET_CHANNEL_ID", "C0BABUEU38R")

# Liquidity bands (USD volume) → confidence flag. Thin markets are whale-sensitive.
VOL_HIGH = 250_000
VOL_MID = 25_000


@dataclass(frozen=True)
class TrackedMarket:
    key: str
    lane: str          # "macro" | "healthcare" | "legislative"
    query: str         # Polymarket public-search term (ignored for PredictIt)
    match: str         # case-insensitive substring the market/event title must contain
    label: str         # display label in the rundown
    headline: bool = False   # include this market's lead number in the aggregated line
    biotech: bool = False    # FDA-approval catalyst — also routes to the biotech lane
    source: str = "polymarket"   # "polymarket" | "predictit"


TRACKED: list[TrackedMarket] = [
    # ---- Macro lane ----
    TrackedMarket("recession", "macro", "recession", "US recession",
                  "US recession by end of 2026", headline=True),
    TrackedMarket("rate_cuts", "macro", "fed rate cuts", "how many fed rate cuts",
                  "Fed rate cuts in 2026", headline=True),
    TrackedMarket("fed_meeting", "macro", "Fed decision", "fed decision in",
                  "Next Fed decision"),
    TrackedMarket("midterms", "macro", "balance of power", "balance of power",
                  "Balance of Power: 2026 Midterms", headline=True),
    TrackedMarket("shutdown", "macro", "government shutdown", "government shutdown",
                  "US government shutdown"),
    # (S&P-level target dropped from v1: Polymarket's "s&p 500" search surfaces a
    #  noisy "best asset" market, not a clean index-level contract. Re-add once a
    #  stable level-target market is identified.)

    # ---- Healthcare lane: pandemics / public health ----
    TrackedMarket("new_pandemic", "healthcare", "new pandemic", "new pandemic",
                  "New pandemic in 2026", headline=True),
    TrackedMarket("hantavirus", "healthcare", "hantavirus pandemic", "hantavirus pandemic",
                  "Hantavirus pandemic in 2026"),
    TrackedMarket("ebola", "healthcare", "ebola pandemic", "ebola pandemic",
                  "Ebola pandemic in 2026"),
    TrackedMarket("measles_2026", "healthcare", "measles cases", "measles cases in u.s. in 2026",
                  "Measles cases in U.S. in 2026"),
    TrackedMarket("covid_variant", "healthcare", "COVID variant of concern", "variant of concern",
                  "New COVID variant of concern before 2027"),
    TrackedMarket("cdc_level4", "healthcare", "CDC Level 4", "level 4",
                  "CDC issues Level 4 warning by Dec 31"),

    # ---- Healthcare lane: policy / political-health ----
    TrackedMarket("rfk_out", "healthcare", "RFK Jr", "rfk jr. out", "RFK Jr. out by Dec 31",
                  headline=True),
    TrackedMarket("fda_commissioner", "healthcare", "FDA commissioner", "fda commissioner",
                  "Next FDA commissioner"),

    # ---- Healthcare lane: biotech FDA-approval catalysts (also → biotech lane) ----
    TrackedMarket("retatrutide", "healthcare", "Retatrutide", "retatrutide",
                  "FDA approves Retatrutide (Lilly)", biotech=True),
    TrackedMarket("olezarsen", "healthcare", "Olezarsen", "olezarsen",
                  "FDA approves Ionis' Olezarsen", biotech=True),
    TrackedMarket("zoryve", "healthcare", "Zoryve", "zoryve",
                  "FDA approves Arcutis' Zoryve cream", biotech=True),
    TrackedMarket("welireg", "healthcare", "Welireg", "welireg",
                  "FDA approves Merck's Welireg + Keytruda", biotech=True),
    TrackedMarket("unicycive", "healthcare", "Oxylanthanum", "oxylanthanum",
                  "FDA approves Unicycive's Oxylanthanum", biotech=True),
    TrackedMarket("arcalyst", "healthcare", "Arcalyst", "arcalyst",
                  "FDA approves Arcalyst tech transfer", biotech=True),
    TrackedMarket("daraxonrasib", "healthcare", "Daraxonrasib", "daraxonrasib",
                  "FDA approves Daraxonrasib (Rev Med)", biotech=True),
    TrackedMarket("veligrotug", "healthcare", "Veligrotug", "veligrotug",
                  "FDA approves Viridian's Veligrotug", biotech=True),
    TrackedMarket("tebipenem", "healthcare", "Tebipenem", "tebipenem",
                  "FDA approves GSK & Spero's Tebipenem", biotech=True),

    # ---- PredictIt: control of government (most-calibrated electoral signal) ----
    TrackedMarket("pi_senate", "macro", "", "which party will control the senate after the 2026",
                  "Senate control after 2026 (PredictIt)", headline=True, source="predictit"),
    TrackedMarket("pi_house", "macro", "", "which party will win the house in the 2026",
                  "House control after 2026 (PredictIt)", headline=True, source="predictit"),
    TrackedMarket("pi_balance", "macro", "", "what will be the balance of power in congress after the 2026",
                  "Balance of power in Congress (PredictIt)", source="predictit"),

    # ---- Legislative: meaningful law-change markets (PredictIt) ----
    TrackedMarket("clarity_act", "legislative", "", "clarity act",
                  "Crypto CLARITY Act enacted 2026", source="predictit"),
    TrackedMarket("save_act", "legislative", "", "save act",
                  "SAVE Act passes Senate before midterms", source="predictit"),
]


def liquidity_flag(volume: float) -> str:
    """Confidence marker by USD volume (thin markets are whale-sensitive)."""
    if volume >= VOL_HIGH:
        return "🟢"
    if volume >= VOL_MID:
        return "🟡"
    return "🔴"
