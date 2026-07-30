"""#macro channel overview / reference card.

Generates the Block Kit payload for the pinned "what this channel is"
message. Regenerable any time the family list, cadence, or surface set
changes — re-post and re-pin.
"""

from __future__ import annotations

from ..config import FamilyConfig
from ..outputs import family_slug

# Published US current-state dashboard. Each family renders a card anchored
# at #fam-<slug> (see charts/dashboard.py), so an overview line can deep-link
# straight to the card holding that family's latest data.
_DASHBOARD_URL = "https://jroypeterson.github.io/macro-monitor/dashboard/"

# Cadence-by-day descriptions, keyed by family_id. Tight enough to read
# on mobile; matches the v5 plan §5 release windows.
RELEASE_WINDOWS: dict[str, str] = {
    # Tier A
    "cpi": "monthly · mid-month 8:30 ET · BLS",
    "payrolls": "monthly · 1st Friday 8:30 ET · BLS (U-3 + U-6 unemployment; HC + white-collar sub-cuts in thread)",
    "pce": "monthly · end-month 8:30 ET · BEA",
    "claims": "weekly · Thursday 8:30 ET · DOL",
    "gdp": "quarterly · 8:30 ET · BEA (PCE Health Services quarterly here)",
    "jolts": "monthly · 10:00 ET, ~2mo lag · BLS",
    "ppi": "monthly · 8:30 ET · BLS",
    "retail_sales": "monthly · mid-month 8:30 ET · Census",
    "eci": "quarterly · 8:30 ET · BLS (total compensation headline)",
    # Tier B
    "industrial_production": "monthly · mid-month 9:15 ET · Federal Reserve G.17",
    "housing": "monthly · mid-month 8:30 ET · Census",
    "mortgage_rates": "weekly · Thursday 12:00 ET · Freddie Mac PMMS",
    "existing_home_sales": "monthly · ~3rd week 10:00 ET · NAR",
    "new_home_sales": "monthly · ~4th week 10:00 ET · Census",
    "construction_spending": "monthly · 1st business day 10:00 ET · Census",
    "durable_goods": "monthly · end-month 8:30 ET · Census",
    "trade_balance": "monthly · early-month 8:30 ET · BEA",
    "consumer_credit": "monthly · 15:00 ET · Federal Reserve G.19",
    "productivity": "quarterly · 8:30 ET · BLS",
    "umich": "monthly (prelim + final) · 10:00 ET · UMich",
}


def build_overview_blocks(families: dict[str, FamilyConfig]) -> tuple[str, list[dict]]:
    """Return (text_fallback, blocks) for the channel overview message."""

    tier_a = sorted(
        ((fid, f) for fid, f in families.items() if f.tier == "A"),
        key=lambda kv: kv[1].display_name,
    )
    tier_b = sorted(
        ((fid, f) for fid, f in families.items() if f.tier == "B"),
        key=lambda kv: kv[1].display_name,
    )

    def _lines(items):
        out = []
        for fid, fam in items:
            window = RELEASE_WINDOWS.get(fid, f"{fam.cadence} · {fam.release_time_et} ET")
            # Deep-link the family name to its card on the current-state dashboard.
            anchor = f"{_DASHBOARD_URL}#fam-{family_slug(fam.display_name)}"
            out.append(f"• *<{anchor}|{fam.display_name}>* — {window}")
        return out

    tier_a_lines = _lines(tier_a)
    tier_b_lines = _lines(tier_b)

    # The "what does this tier mean" notes are DERIVED from the family
    # config, never asserted in prose — a hand-written "1σ vs trailing 5y"
    # silently becomes a lie the moment a family is added with a different
    # gate. Anything non-uniform is named explicitly rather than averaged
    # away, so the pin can't quietly misdescribe a family.
    # `context` and `tier_b_gate` are both optional on FamilyConfig, so every
    # read is guarded — a family missing either must degrade the note, never
    # raise and take the whole pin down with it.
    _thresholds = {f.tier_b_gate.threshold for _, f in tier_b if f.tier_b_gate}
    _scored = [(fid, f) for fid, f in tier_b if f.context is not None]
    _lookbacks = {f.context.zscore_lookback_years for _, f in _scored}
    _gate = (
        f"|z| ≥ {min(_thresholds):g}σ" if len(_thresholds) == 1
        else f"|z| ≥ {min(_thresholds):g}–{max(_thresholds):g}σ (varies by family)"
        if _thresholds else "|z| over its gate"
    )
    _window = (
        f"trailing {min(_lookbacks)}y" if len(_lookbacks) == 1
        else f"trailing {min(_lookbacks)}–{max(_lookbacks)}y" if _lookbacks
        else "trailing"
    )
    # Most families gate on the MOVE (delta z); a few ask "how elevated is
    # the level" instead. Name the minority so the sentence stays true.
    _level_gated = sorted(
        f.display_name for _, f in _scored if f.context.zscore_kind == "level"
    )
    _delta_n = len(_scored) - len(_level_gated)
    if not _scored:
        _kind_note = ""
    elif not _level_gated:
        _kind_note = (
            " Notably, the test is on the *move* — how big this period's change was, "
            "not the level."
        )
    elif not _delta_n:
        _kind_note = (
            f" Notably, the test is on the level, not the move ({', '.join(_level_gated)})."
        )
    else:
        _kind_note = (
            f" Notably, for {_delta_n} of {len(_scored)} the test is on the *move* — how big "
            f"this period's change was, not the level. {', '.join(_level_gated)} is gated on "
            "the level instead, since \"how elevated is it\" is the real question there."
        )

    tier_a_note = (
        "_The core, market-moving releases — deliberately curated, not exhaustive. "
        "Every print lands the same day it publishes (~1h after the agency), with a 5y "
        "chart and a long-history thread. Tier A alone drives the Google Calendar events "
        "and the 4-week lookahead in the Sunday preview._"
    )
    tier_b_note = (
        "_The second ring: worth knowing, not worth a post every time. Always listed in "
        f"the Sunday preview, but only posts when the print is unusual — {_gate} against "
        f"that series' own {_window} history.{_kind_note} A series without enough history "
        "to score is skipped, not posted._"
    )

    text = (
        "Macro & Markets Monitor — channel overview\n"
        f"Macro release feed ({len(tier_a)} Tier A + {len(tier_b)} Tier B families) plus "
        "top-down market data (valuation, ERP, factor returns) and the Ahead-of-the-Curve charts."
    )

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📊 Macro & Markets Monitor — channel overview",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Two halves — macro and markets — across four layers:*\n"
                    "1️⃣ *Macro releases & cycle* — the disciplined Tier A/B release feed (below)\n"
                    "2️⃣ *Markets* — valuation, equity-risk premium & factor returns (dedicated section below)\n"
                    "3️⃣ *Ahead of the Curve* — Joseph Ellis's leading-indicator chart framework (23 charts)\n"
                    "4️⃣ *Global macro* — international CPI/GDP/rates + OECD business "
                    "confidence (Eurozone · UK · China · Japan), weekly"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Tier A ({len(tier_a)} series) — always posts on release*\n"
                    + tier_a_note + "\n"
                    + "\n".join(tier_a_lines)
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Tier B ({len(tier_b)} series) — posts only on a material surprise*\n"
                    + tier_b_note + "\n"
                    + "\n".join(tier_b_lines)
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*💹 Markets — top-down valuation, risk premium, earnings & factor returns*\n"
                    "• *<https://jroypeterson.github.io/macro-monitor/market/|Valuation vs history>* — "
                    "Shiller CAPE vs its own history (live from multpl.com)\n"
                    "• *Implied equity-risk premium (ERP)* — Damodaran-style, vs the 10y\n"
                    "• *<https://jroypeterson.github.io/macro-monitor/market/growth.html|Earnings & growth>* — "
                    "S&P 500 EPS growth (vs corporate profits) + real GDP/PCE/IP/capex & unemployment YoY, quarterly\n"
                    "• *Factor returns* — Fama-French / Ken French + AQR premia (size · value · momentum · quality)\n"
                    "_The full gallery: <https://jroypeterson.github.io/macro-monitor/market/|Market valuation & factors>. "
                    "Dataset inventories: "
                    "<https://github.com/jroypeterson/macro-monitor/blob/main/damodaran/DATA_OVERVIEW.md|Damodaran>, "
                    "<https://github.com/jroypeterson/macro-monitor/blob/main/market/README.md|Ken French / AQR / Shiller>._"
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*When and what posts*\n"
                    "• 📅 *Sun 07:00 ET* — week-ahead + 4-week lookout\n"
                    "• 🌍 *Sun 08:00 ET* — Global macro digest (Eurozone / UK / China / Japan)\n"
                    "• 🔴 *Release time* — main post with headline + 5y chart; "
                    "thread with long-history + components + (for payrolls) "
                    "HC-employment two-pane chart\n"
                    "• 🔁 *Revisions* — new REVISED post with diff; "
                    "annual benchmarks collapse into one summary\n"
                    "• 🏛️ *Daily 08:30 ET* — Fed research digest (NBER, NY Fed, "
                    "SF Fed, St. Louis Fed, FRB FEDS — only when new papers land)\n"
                    "• 📆 *Jan + quarterly* — year-long Macro Calendar HTML uploaded\n"
                    "• 🏥 *Healthcare context* surfaced in every release where applicable"
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Where else to look*\n"
                    "• 🧭 <https://jroypeterson.github.io/macro-monitor/|Overview hub> — "
                    "the published landing page with live links to every view. Chart galleries: "
                    "<https://jroypeterson.github.io/macro-monitor/ahead_of_curve/|Ahead of the Curve> "
                    "(Ellis leading-indicator framework, 23 charts) · "
                    "<https://jroypeterson.github.io/macro-monitor/market/|Market valuation & factors> "
                    "(CAPE vs history, implied ERP, Fama-French).\n"
                    "• 💹 *Top-down market data inventories* — "
                    "<https://github.com/jroypeterson/macro-monitor/blob/main/damodaran/DATA_OVERVIEW.md|Damodaran time-series overview>, "
                    "<https://github.com/jroypeterson/macro-monitor/blob/main/market/README.md|Ken French / AQR / Shiller datasets>.\n"
                    "• 🏥 *Healthcare dashboards* (sibling `hc_macro_policy`) — "
                    "<https://jroypeterson.github.io/hc-macro-policy-pages/dashboard.html|HC Operating Dashboard> "
                    "(weekly HC operating series rebuilt by subsector), "
                    "<https://jroypeterson.github.io/hc-macro-policy-pages/cms_calendar.html|CMS Rule-Cycle Calendar> "
                    "(3-year CMS payment-rule cycles + key data releases), "
                    "<https://jroypeterson.github.io/hc-macro-policy-pages/cms_rates.html|CMS Rates> "
                    "(headline update %, proposed vs final, by payment system).\n"
                    "• 📊 <https://jroypeterson.github.io/macro-monitor/dashboard/|US current state dashboard> — "
                    "latest value per family, mini-charts, links into release reports. Auto-refreshes after every release post.\n"
                    "• 🌍 <https://jroypeterson.github.io/macro-monitor/international/|Global macro dashboard> — "
                    "latest CPI / GDP / unemployment / business confidence / policy rates for "
                    "the eurozone, UK, China & Japan. Refreshed weekly.\n"
                    "• 📅 <https://jroypeterson.github.io/macro-monitor/calendar/2026_macro_calendar.html|2026 Annual Macro Calendar> — "
                    "year-long release schedule (all tiers; Tier B tagged), refreshed quarterly\n"
                    "• `#status-reports` — daily 08:00 ET heartbeat + operator alerts\n"
                    "• *Google Calendar* (floridabusinessman@gmail.com) — "
                    "\"Macro Calendar\" with rolling 90-day release events (all tiers)\n"
                    "• 🔧 <https://github.com/jroypeterson/macro-monitor|Source on GitHub> — "
                    "code, workflows, design plan"
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Intentionally not covered yet*\n"
                    "• *ISM Mfg + Services PMI* — licensing terms (no free redistribution). "
                    "The OECD Business Confidence Index in the Global-macro layer is the "
                    "free, redistributable business-survey stand-in.\n"
                    "• *Conference Board Consumer Confidence* — same licensing issue\n"
                    "• *FOMC decisions / minutes* — manual until a meeting tests the parser\n"
                    "• *Intraday market data* (live yields, USD, oil) — sigma-alert owns price moves"
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "_Regenerated via `cli overview`. Update + re-pin when the family list changes._",
                }
            ],
        },
    ]

    return text, blocks
