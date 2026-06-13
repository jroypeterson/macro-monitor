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
    "payrolls": "monthly · 1st Friday 8:30 ET · BLS (HC employment sub-cuts in thread)",
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

    text = (
        "macro-and-markets channel overview\n"
        f"Macro release feed ({len(tier_a)} Tier A + {len(tier_b)} Tier B families) plus "
        "top-down market data (valuation, ERP, factor returns) and the Ahead-of-the-Curve charts."
    )

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📊 macro-and-markets — channel overview",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*This channel covers four layers:*\n"
                    "1️⃣ *Macro releases & cycle* — the disciplined Tier A/B release feed (below)\n"
                    "2️⃣ *Ahead of the Curve* — Joseph Ellis's leading-indicator chart framework (23 charts)\n"
                    "3️⃣ *Top-down market data* — valuation, ERP & factor returns (Damodaran · Ken French · AQR · Shiller)\n"
                    "4️⃣ *Global macro* — international CPI/GDP/rates (Eurozone · UK · China · Japan), weekly"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Tier A — always posts on release*\n"
                    + "\n".join(tier_a_lines)
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Tier B — preview always; post only on material surprise (|z| ≥ 1σ vs trailing 5y)*\n"
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
                    "latest CPI / GDP / unemployment / policy rates for the eurozone, UK, China & Japan. Refreshed weekly.\n"
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
                    "• *ISM Mfg + Services PMI* — licensing terms (no free redistribution)\n"
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
