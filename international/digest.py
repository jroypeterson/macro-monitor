"""Weekly "Global macro" Slack digest — Block Kit payload.

A region-by-region snapshot (CPI / core CPI / GDP / unemployment / policy
rate) of the latest international readings. Separate from the US Tier A/B
release feed by design; posts on its own weekly cadence.
"""

from __future__ import annotations

from .config import (
    INDICATOR_LABELS,
    INDICATOR_ORDER,
    REGION_LABELS,
    REGION_ORDER,
    YIELD_INDICATORS,
)
from .format import fmt_bps, fmt_change, fmt_period, fmt_value, ytd_change_bps
from .model import IntlSeriesResult


def _ordered(results: list[IntlSeriesResult], region: str) -> list[IntlSeriesResult]:
    in_region = [r for r in results if r.region == region
                 and r.indicator not in YIELD_INDICATORS]
    order = {ind: i for i, ind in enumerate(INDICATOR_ORDER)}
    return sorted(in_region, key=lambda r: order.get(r.indicator, 99))


def _region_lines(results: list[IntlSeriesResult], region: str) -> list[str]:
    lines: list[str] = []
    for r in _ordered(results, region):
        label = INDICATOR_LABELS.get(r.indicator, r.indicator)
        if r.ok:
            delta = fmt_change(r)
            delta_str = f"  _{delta}_" if delta else ""
            lines.append(
                f"• {label}: *{fmt_value(r)}*  ({fmt_period(r.latest.period)}){delta_str}"
            )
        else:
            why = "needs API key" if "APP_ID" in (r.error or "") else "unavailable"
            lines.append(f"• {label}: _—  ({why})_")
    yld = _yield_line(results, region)
    if yld:
        lines.append(yld)
    return lines


def _yield_line(results: list[IntlSeriesResult], region: str) -> str | None:
    """One combined gov't-bond line: '2Y x% (YTD ±Nbps) · 10Y y% (YTD ±Mbps)'.
    Missing maturities render '—'; a region with no live yields shows the
    no-free-source note."""
    by_ind = {r.indicator: r for r in results if r.region == region}
    parts: list[str] = []
    any_ok = False
    for ind, lab in (("yield_2y", "2Y"), ("yield_10y", "10Y")):
        r = by_ind.get(ind)
        if r and r.ok:
            any_ok = True
            ytd = ytd_change_bps(r)
            ytd_str = f" _(YTD {fmt_bps(ytd)})_" if ytd is not None else ""
            parts.append(f"{lab} *{fmt_value(r)}*{ytd_str}")
        else:
            parts.append(f"{lab} —")
    if not any_ok:
        return "• Gov't yield: _— (no free source)_"
    return "• Gov't yield: " + "  ·  ".join(parts)


def build_digest_blocks(
    results: list[IntlSeriesResult], *, as_of: str
) -> tuple[str, list[dict]]:
    """Return (text_fallback, blocks) for the Global macro digest."""
    ok = sum(1 for r in results if r.ok)
    text = (
        f"Global macro — {ok}/{len(results)} series, as of {as_of}. "
        "Eurozone / UK / China / Japan: CPI, GDP, unemployment, policy rates."
    )

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🌍 Global macro", "emoji": True},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"_Latest international readings as of {as_of}. "
                        "Sources: Eurostat · ECB · ONS · BoE · OECD · e-Stat · FRED._"
                    ),
                }
            ],
        },
    ]

    for region in REGION_ORDER:
        lines = _region_lines(results, region)
        if not lines:
            continue
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{REGION_LABELS.get(region, region)}*\n" + "\n".join(lines),
                },
            }
        )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "_Δ = change vs prior reading (pp). Regenerated via `cli global-macro`._",
                }
            ],
        }
    )
    return text, blocks
