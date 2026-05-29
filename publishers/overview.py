"""#macro channel overview / reference card.

Generates the Block Kit payload for the pinned "what this channel is"
message. Regenerable any time the family list, cadence, or surface set
changes — re-post and re-pin.
"""

from __future__ import annotations

from ..config import FamilyConfig

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
            out.append(f"• *{fam.display_name}* — {window}")
        return out

    tier_a_lines = _lines(tier_a)
    tier_b_lines = _lines(tier_b)

    text = (
        "macro-monitor channel overview\n"
        f"Tracks {len(tier_a)} Tier A families (always post) + {len(tier_b)} "
        "Tier B families (preview always; post only on material surprise)."
    )

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📊 macro-monitor — channel overview",
                "emoji": True,
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
                    "• 📅 *Mon 07:00 ET* — week-ahead + 4-week lookout\n"
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
                    "• 📊 <https://jroypeterson.github.io/macro-monitor/dashboard/|Current state dashboard> — "
                    "latest value per family, mini-charts, links into release reports. Auto-refreshes after every release post.\n"
                    "• 📅 <https://jroypeterson.github.io/macro-monitor/calendar/2026_macro_calendar.html|2026 Annual Macro Calendar> — "
                    "year-long Tier A schedule, refreshed quarterly\n"
                    "• `#status-reports` — daily 08:00 ET heartbeat + operator alerts\n"
                    "• *Google Calendar* (floridabusinessman@gmail.com) — "
                    "\"Macro Calendar\" with rolling 90-day Tier A events\n"
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
                    "• *International macro* (ECB / BoJ / eurozone / China / UK) — Phase 2\n"
                    "• *Market data* (yields, USD, oil) — not the project's edge"
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
