"""Annual macro calendar — one-page HTML with the year's Tier A release
schedule rendered as a 12-month grid.

Generated Jan 1 each year and refreshed quarterly. Output:
  outputs/calendar/<year>_macro_calendar.html  (committed)

Uploaded to #macro as a file attachment alongside a short summary post.
HTML (not PDF) for easier formatting + future GitHub Pages dashboard reuse.
"""

from __future__ import annotations

import calendar
import html
from collections import defaultdict
from datetime import date
from pathlib import Path

from ..collectors.fred import FREDClient, FREDError
from ..config import FamilyConfig, calendar_families
from .style import CYCLE


def render_annual_calendar(
    families: dict[str, FamilyConfig],
    client: FREDClient,
    year: int,
    output_path: Path,
) -> Path:
    """Pull every Tier A family's release dates for `year` from FRED and
    render to a single HTML page. Returns the written file path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    # date -> list of (family_id, family_display_name, time_et)
    events: dict[date, list[tuple[str, str, str]]] = defaultdict(list)
    # Stable color per family so the grid reads consistently
    family_color: dict[str, str] = {}
    # Every family with a FRED release calendar — both Tier A (Slack-posted)
    # and Tier B (heartbeat-only) — so the grid is a complete schedule.
    # Shared with the Google Calendar backfill via config.calendar_families.
    cal_families = calendar_families(families)
    failed_families: list[str] = []
    for idx, (fid, fam) in enumerate(sorted(cal_families.items())):
        family_color[fid] = CYCLE[idx % len(CYCLE)]
        try:
            dates = client.get_release_dates(
                release_id=fam.release_calendar_id,
                realtime_start=year_start.isoformat(),
                realtime_end=year_end.isoformat(),
                include_release_dates_with_no_data=True,
            )
        except FREDError:
            failed_families.append(fam.display_name)
            continue
        for rd in dates:
            if year_start <= rd.date <= year_end:
                events[rd.date].append((fid, fam.display_name, fam.release_time_et))

    html_text = _render_html(year, events, family_color, cal_families, failed_families)
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{year} Macro Calendar</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
          max-width: 1400px; margin: 1em auto; padding: 0 1em; color: #222; background: #fafafa; }}
  h1 {{ font-size: 1.7em; margin-bottom: 0.1em; }}
  .subtitle {{ color: #666; margin-bottom: 1.5em; font-size: 0.95em; }}
  .legend {{ background: white; padding: 0.8em 1em; border-radius: 6px;
             margin-bottom: 1.5em; border: 1px solid #e0e0e0; }}
  .legend h3 {{ font-size: 0.9em; margin: 0 0 0.5em 0; color: #555; text-transform: uppercase; letter-spacing: 0.5px; }}
  .legend-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.4em; }}
  .legend-item {{ font-size: 0.85em; display: flex; align-items: center; gap: 0.4em; }}
  .swatch {{ display: inline-block; width: 14px; height: 14px; border-radius: 3px; }}
  .months {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1em; }}
  @media (max-width: 1000px) {{ .months {{ grid-template-columns: repeat(2, 1fr); }} }}
  @media (max-width: 680px) {{ .months {{ grid-template-columns: 1fr; }} }}
  .month {{ background: white; border-radius: 6px; padding: 0.8em; border: 1px solid #e0e0e0; }}
  .month h2 {{ font-size: 1em; margin: 0 0 0.4em 0; color: #1F4E79; border-bottom: 1px solid #eaeaea; padding-bottom: 0.3em; }}
  .month table {{ width: 100%; border-collapse: collapse; font-size: 0.82em; }}
  .month th {{ width: 28px; text-align: center; color: #888; font-weight: normal; padding: 0.15em 0; font-size: 0.7em; }}
  .month td {{ vertical-align: top; padding: 0.15em 0.2em; height: 38px; border: 1px solid #f0f0f0; }}
  .day-num {{ font-weight: 600; color: #555; font-size: 0.8em; }}
  .events {{ margin-top: 0.1em; line-height: 1.1; }}
  .event {{ display: block; font-size: 0.7em; padding: 1px 3px; border-radius: 2px;
            color: white; margin-bottom: 1px; white-space: nowrap; overflow: hidden;
            text-overflow: ellipsis; }}
  /* Tier A = top-tier / most market-moving. Bold + a bright inset ring so it
     visually pops out of the routine (Tier B) releases in the grid. */
  .event.tiera {{ font-weight: 700; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.65); }}
  .weekend {{ background: #fafafa; color: #aaa; }}
  .footer {{ font-size: 0.8em; color: #888; margin-top: 2em; padding-top: 1em; border-top: 1px solid #e0e0e0; }}
</style>
</head>
<body>

<h1>{year} Macro Calendar</h1>
<p class="subtitle">All scheduled release dates pulled from FRED's calendar.
  <strong>&#9733; bold = Tier A</strong> (top-tier, most market-moving); plain = Tier B (routine).
  Quarterly refresh; latest pull: {fetched_date}.</p>

<div class="legend">
  <h3>Legend</h3>
  <div class="legend-grid">
{legend_items}
  </div>
</div>

<div class="months">
{months_html}
</div>

<div class="footer">
  Generated by <code>macro_monitor.charts.annual_calendar</code>.
  Schedule source: <a href="https://fred.stlouisfed.org/releases">FRED releases</a>.
  Page is self-contained — inline CSS only, no external assets.
</div>

</body>
</html>
"""


def _render_html(
    year: int,
    events: dict[date, list[tuple[str, str, str]]],
    family_color: dict[str, str],
    cal_families: dict[str, FamilyConfig],
    failed_families: list[str] | None = None,
) -> str:
    def _legend_label(fam: FamilyConfig) -> str:
        # Tier A (top-tier) families get a ★ + bold so the market-moving set
        # stands out from the routine Tier B (heartbeat-only) schedule — the
        # same denotation used on the event chips in the grid.
        if fam.tier == "A":
            return "&#9733; <strong>" + html.escape(fam.display_name) + "</strong>"
        return html.escape(fam.display_name) + " <span style='color:#999;font-size:0.85em'>(Tier B)</span>"

    legend_items = "\n".join(
        f"    <div class='legend-item'><span class='swatch' style='background:{family_color[fid]}'></span>"
        f"<span>{_legend_label(cal_families[fid])}</span></div>"
        for fid in sorted(cal_families)
    )

    # family_id -> tier, so the grid can mark Tier A chips (see _render_month).
    family_tier = {fid: fam.tier for fid, fam in cal_families.items()}

    months_html_parts = []
    for month in range(1, 13):
        months_html_parts.append(
            _render_month(year, month, events, family_color, family_tier)
        )
    months_html = "\n".join(months_html_parts)

    failed_html = ""
    if failed_families:
        failed_html = (
            f"<div style='background:#fef3c7;border-left:3px solid #f59e0b;"
            f"padding:0.5em 1em;margin-bottom:1em;font-size:0.9em;'>"
            f"⚠️ FRED calendar fetch failed for: "
            f"{', '.join(html.escape(n) for n in failed_families)}. "
            f"These families' events are missing from the grid below."
            f"</div>"
        )

    return _HTML_TEMPLATE.format(
        year=year,
        fetched_date=date.today().isoformat(),
        legend_items=legend_items,
        months_html=failed_html + months_html,
    )


def _render_month(
    year: int, month: int, events: dict[date, list[tuple[str, str, str]]],
    family_color: dict[str, str], family_tier: dict[str, str] | None = None,
) -> str:
    cal = calendar.Calendar(firstweekday=6)  # Sunday first
    month_name = calendar.month_name[month]

    # 6 rows max × 7 days
    weeks = cal.monthdatescalendar(year, month)

    rows_html = []
    rows_html.append(
        "<tr>" + "".join(f"<th>{d}</th>" for d in ["S", "M", "T", "W", "T", "F", "S"]) + "</tr>"
    )

    for week in weeks:
        cells = []
        for day in week:
            if day.month != month:
                # Day from prior/next month — render blank
                cells.append("<td class='weekend'></td>")
                continue
            is_weekend = day.weekday() >= 5
            day_events = events.get(day, [])
            event_html = ""
            for fid, name, _time in day_events:
                color = family_color.get(fid, "#666")
                # Tier A (top-tier) chips get a ★ prefix + bold styling so the
                # most market-moving releases stand out from routine Tier B.
                is_tier_a = (family_tier or {}).get(fid) == "A"
                chip_cls = "event tiera" if is_tier_a else "event"
                star = "&#9733; " if is_tier_a else ""
                tier_note = " (Tier A)" if is_tier_a else " (Tier B)"
                event_html += (
                    f"<span class='{chip_cls}' style='background:{color}' "
                    f"title='{html.escape(name)}{tier_note}'>"
                    f"{star}{html.escape(_abbrev(name))}</span>"
                )
            cls = " class='weekend'" if is_weekend and not day_events else ""
            cells.append(
                f"<td{cls}><div class='day-num'>{day.day}</div>"
                f"<div class='events'>{event_html}</div></td>"
            )
        rows_html.append("<tr>" + "".join(cells) + "</tr>")

    return (
        f"<div class='month'>"
        f"<h2>{month_name} {year}</h2>"
        f"<table>{''.join(rows_html)}</table>"
        f"</div>"
    )


# Tight name abbreviations so the calendar grid cells stay readable
ABBREVIATIONS = {
    # Tier A
    "CPI": "CPI",
    "PPI": "PPI",
    "Employment Situation": "Jobs",
    "JOLTS": "JOLTS",
    "Initial Jobless Claims": "Claims",
    "Retail Sales": "Retail",
    "GDP": "GDP",
    "Employment Cost Index": "ECI",
    "Consumer Spending — Personal Consumption Expenditures (PCE) / Personal Income & Outlays": "PCE",
    # Tier B
    "Industrial Production": "IndPro",
    "Housing Starts & Permits": "Housing",
    "Durable Goods Orders": "Durables",
    "Trade Balance": "Trade",
    "Consumer Credit": "Credit",
    "Productivity & Unit Labor Costs": "Prod",
    "UMich Consumer Sentiment": "UMich",
    "ADP National Employment Report": "ADP",
}


def _abbrev(display_name: str) -> str:
    return ABBREVIATIONS.get(display_name, display_name[:8])
