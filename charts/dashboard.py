"""Static "current state" dashboard — Phase 1.5.

Renders outputs/dashboard/index.html from the artifacts already on disk:
  outputs/latest/<family>.json  — current value + transforms for each family
  outputs/charts/*.png          — chart images

The dashboard reads, never fetches. It's the "what's the current state of
my macro coverage?" view that complements the per-release Slack posts.

Future GitHub Pages deploy is just `git push` of outputs/ — this HTML is
self-contained, uses inline CSS, and references chart images by relative
path so it works from a static-file server.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import FamilyConfig
from ..outputs import family_slug, outputs_root

ET = ZoneInfo("America/New_York")


def render_dashboard(
    families: dict[str, FamilyConfig],
    output_path: Path | None = None,
) -> Path:
    """Render the dashboard HTML to outputs/dashboard/index.html (or
    `output_path` if provided). Returns the written path."""
    if output_path is None:
        output_path = outputs_root() / "dashboard" / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    latest_dir = outputs_root() / "latest"
    family_cards: list[str] = []

    # Order families by tier then by display name so the dashboard reads
    # consistently regardless of YAML order.
    sorted_families = sorted(
        families.items(),
        key=lambda kv: (kv[1].tier, kv[1].display_name),
    )

    stats = {"families_total": len(families), "with_data": 0, "stale": 0}

    for _family_key, family in sorted_families:
        # Artifacts are stored under the slugified display name (see
        # outputs.family_slug), NOT the YAML config key — the two only
        # coincidentally match for some families.
        slug = family_slug(family.display_name)
        latest_json = latest_dir / f"{slug}.json"
        if not latest_json.exists():
            family_cards.append(_render_card_no_data(slug, family))
            continue
        try:
            payload = json.loads(latest_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            family_cards.append(_render_card_no_data(slug, family))
            continue

        stats["with_data"] += 1
        if payload.get("is_stale"):
            stats["stale"] += 1

        family_cards.append(_render_card(slug, family, payload))

    body_html = _HTML_TEMPLATE.format(
        generated_at=datetime.now(ET).strftime("%a %b %d %Y %H:%M ET"),
        families_total=stats["families_total"],
        families_with_data=stats["with_data"],
        families_stale=stats["stale"],
        stale_class=" warn" if stats["stale"] else "",
        cards="\n".join(family_cards),
    )
    output_path.write_text(body_html, encoding="utf-8")
    return output_path


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>macro-monitor — current state</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
          max-width: 1400px; margin: 1em auto; padding: 0 1em; color: #222; background: #fafafa; }}
  h1 {{ font-size: 1.7em; margin-bottom: 0.1em; }}
  .subtitle {{ color: #666; margin-bottom: 1.5em; font-size: 0.95em; }}
  .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
              gap: 1em; margin-bottom: 1.5em; }}
  .stat {{ background: white; padding: 1em; border-radius: 6px; border: 1px solid #e0e0e0; }}
  .stat .label {{ font-size: 0.75em; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }}
  .stat .value {{ font-size: 1.6em; font-weight: 600; color: #1F4E79; margin-top: 0.2em; }}
  .stat.warn .value {{ color: #C00000; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 1em; }}
  .card {{ background: white; border-radius: 6px; padding: 1em; border: 1px solid #e0e0e0; }}
  .card h2 {{ font-size: 1.05em; margin: 0 0 0.3em 0; color: #1F4E79; }}
  .card .period {{ font-size: 0.85em; color: #666; margin-bottom: 0.6em; }}
  .card.stale {{ border-left: 3px solid #C00000; }}
  .card.nodata {{ border-left: 3px solid #ccc; }}
  .card.nodata h2 {{ color: #888; }}
  .headline {{ display: flex; justify-content: space-between; align-items: baseline;
               padding: 0.3em 0; border-bottom: 1px solid #f0f0f0; }}
  .headline-label {{ font-size: 0.9em; color: #555; }}
  .headline-value {{ font-variant-numeric: tabular-nums; font-weight: 600; color: #222; }}
  .also {{ font-size: 0.75em; color: #888; margin-left: 0.5em; }}
  .basis {{ font-size: 0.62em; color: #999; font-weight: 400; margin-left: 0.3em;
            text-transform: none; letter-spacing: 0; }}
  .chart-thumb {{ width: 100%; height: auto; max-height: 200px; object-fit: contain;
                  margin: 0.6em 0; border: 1px solid #eee; border-radius: 4px; }}
  .links {{ display: flex; gap: 0.5em; font-size: 0.8em; margin-top: 0.6em; }}
  .links a {{ color: #1F4E79; text-decoration: none; padding: 0.2em 0.5em;
              background: #f0f4f8; border-radius: 3px; }}
  .links a:hover {{ background: #1F4E79; color: white; }}
  .footer {{ font-size: 0.8em; color: #888; margin-top: 2em; padding-top: 1em; border-top: 1px solid #e0e0e0; }}
  .stale-badge {{ display: inline-block; background: #FEE2E2; color: #B91C1C; font-size: 0.7em;
                  padding: 0.1em 0.4em; border-radius: 3px; margin-left: 0.5em; }}
  .hc-badge {{ display: inline-block; background: #E8F0E0; color: #2D5016; font-size: 0.7em;
               padding: 0.1em 0.4em; border-radius: 3px; margin-left: 0.4em; }}
</style>
</head>
<body>

<h1>macro-monitor — current state</h1>
<p class="subtitle">Latest values per Tier A family. Generated {generated_at}.<br>
Each figure is tagged with its basis — <b>y/y</b> (year-over-year) · <b>m/m</b> (month-over-month) ·
<b>m/m ann.</b> (annualized monthly) · <b>q/q ann.</b> (annualized quarterly) ·
<b>m/m chg</b> (level change, e.g. payrolls in thousands) · <b>level</b> (the raw level).</p>

<div class="summary">
  <div class="stat">
    <div class="label">Families tracked</div>
    <div class="value">{families_total}</div>
  </div>
  <div class="stat">
    <div class="label">Families with data</div>
    <div class="value">{families_with_data}</div>
  </div>
  <div class="stat{stale_class}">
    <div class="label">Stale (FRED behind expected)</div>
    <div class="value">{families_stale}</div>
  </div>
</div>

<div class="grid">
{cards}
</div>

<div class="footer">
  Generated by <code>macro_monitor.charts.dashboard</code>.
  Each card links to the per-release HTML report and the agency PDF.
  Future GitHub Pages deploy = <code>git push</code> of <code>outputs/</code>.
</div>

</body>
</html>
"""


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _fmt_value(value: float | None, transform: str) -> str:
    if value is None:
        return "—"
    if transform in {
        "yoy_pct",
        "mom_pct",
        "annualized_mom",
        "qoq_pct_saar",
        "yoy_pct_weekly",
        "mom_pct_weekly",
    }:
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.2f}%"
    if transform == "mom_chg":
        sign = "+" if value >= 0 else ""
        if abs(value) >= 1000:
            return f"{sign}{value:,.0f}"
        return f"{sign}{value:.1f}"
    # raw
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:.2f}"


# Short, human-readable basis for each transform — the figures are NOT all
# y/y (CPI headline is annualized m/m, payrolls is the m/m change in
# thousands, unemployment is a level, etc.), so every value is labelled.
_BASIS_LABELS = {
    "yoy_pct": "y/y",
    "mom_pct": "m/m",
    "annualized_mom": "m/m ann.",
    "qoq_pct_saar": "q/q ann.",
    "mom_chg": "m/m chg",
    "yoy_pct_weekly": "y/y",
    "mom_pct_weekly": "4wk",
    "raw": "level",
}


def _basis_label(transform: str) -> str:
    return _BASIS_LABELS.get(transform, transform)


def _value_with_basis(value: float | None, transform: str) -> str:
    """Formatted value followed by a small muted basis tag (e.g. 'y/y')."""
    if value is None:
        return "—"
    return (
        f"{_fmt_value(value, transform)}"
        f"<span class='basis'>{html.escape(_basis_label(transform))}</span>"
    )


def _render_card(family_id: str, family: FamilyConfig, payload: dict) -> str:
    stale = payload.get("is_stale", False)
    from_cache = payload.get("from_fallback_cache", False)
    card_class = "card stale" if (stale or from_cache) else "card"
    period_label = payload.get("period_label", payload.get("period", "?"))

    # Headline rows
    headline_rows = []
    for h in payload.get("headline", []):
        label = html.escape(h.get("label", h.get("id", "?")))
        primary = h.get("primary", {})
        value_str = _value_with_basis(primary.get("value"), primary.get("transform", "raw"))
        also = h.get("also_display", [])
        also_str = (
            " · ".join(
                f"{_fmt_value(ad['value'], ad['transform'])} {_basis_label(ad['transform'])}"
                for ad in also if ad.get("value") is not None
            )
        )
        also_html = f"<span class='also'>{html.escape(also_str)}</span>" if also_str else ""
        headline_rows.append(
            f"<div class='headline'>"
            f"<span class='headline-label'>{label}</span>"
            f"<span class='headline-value'>{value_str}{also_html}</span>"
            f"</div>"
        )

    # Healthcare context (computed + tagged components)
    hc_lines = []
    for c in payload.get("computed", []) or []:
        if "healthcare" in (c.get("tags") or []):
            tv = c.get("transformed") or {}
            hc_lines.append(
                f"<div class='headline'>"
                f"<span class='headline-label'>{html.escape(c.get('label', '?'))} "
                f"<span class='hc-badge'>HC</span></span>"
                f"<span class='headline-value'>{_value_with_basis(tv.get('value'), tv.get('transform', 'raw'))}</span>"
                f"</div>"
            )
    for c in payload.get("components", []) or []:
        if "healthcare" in (c.get("tags") or []):
            hc_lines.append(
                f"<div class='headline'>"
                f"<span class='headline-label'>↳ {html.escape(c.get('label', '?'))}</span>"
                f"<span class='headline-value'>{_value_with_basis(c.get('value'), c.get('transform', 'raw'))}</span>"
                f"</div>"
            )

    # Main chart (relative path from outputs/dashboard/ to outputs/charts/)
    charts = payload.get("charts", {}) or {}
    main_chart_name = charts.get("main")
    chart_html = ""
    if main_chart_name:
        chart_html = f"<img class='chart-thumb' src='../charts/{html.escape(main_chart_name)}' alt='main chart'>"

    # Links — to per-release HTML + agency PDF
    period = payload.get("period", "")
    release_html_path = f"../archive/{family_id}/{period}.html"
    agency_url = payload.get("agency_pdf_url")
    links = [
        f"<a href='{html.escape(release_html_path)}'>Release report</a>"
    ]
    if agency_url:
        links.append(f"<a href='{html.escape(agency_url)}' target='_blank'>Official PDF ↗</a>")
    links_html = "<div class='links'>" + " ".join(links) + "</div>"

    stale_badge = "<span class='stale-badge'>STALE</span>" if stale else ""
    cache_badge = ""
    if from_cache:
        age = payload.get("cache_age_hours")
        age_str = f"{age:.0f}h old" if age is not None else "from cache"
        cache_badge = (
            f"<span class='stale-badge' style='background:#FEF3C7;color:#92400E'>"
            f"CACHE {html.escape(age_str)}</span>"
        )

    return (
        f"<div class='{card_class}'>"
        f"<h2>{html.escape(family.display_name)}{stale_badge}{cache_badge}</h2>"
        f"<div class='period'>{html.escape(period_label)}</div>"
        + "".join(headline_rows)
        + "".join(hc_lines)
        + chart_html
        + links_html
        + "</div>"
    )


def _render_card_no_data(family_id: str, family: FamilyConfig) -> str:
    return (
        f"<div class='card nodata'>"
        f"<h2>{html.escape(family.display_name)}</h2>"
        f"<div class='period'>no data yet — first release post will populate</div>"
        f"</div>"
    )
