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

import pandas as pd

from ..config import FamilyConfig
from ..outputs import family_slug, outputs_root

ET = ZoneInfo("America/New_York")

# US Treasury curve, FRED daily constant-maturity series. Close-of-day levels
# (NOT intraday — sigma-alert owns live yields); the dashboard is a prior-close
# current-state view, so the daily FRED series is the right basis.
_CURVE_SERIES = [("DGS2", "2-Year"), ("DGS10", "10-Year"), ("DGS30", "30-Year")]


def fetch_treasury_curve(client=None) -> list[dict] | None:
    """Best-effort fetch of the US Treasury curve (2/10/30) from FRED.

    Returns a list of {label, level, chg_1d_bp, ytd_bp, asof} dicts, or None
    if the curve can't be fetched (the dashboard then renders no panel rather
    than failing). Never raises — the dashboard must always render.
    """
    try:
        if client is None:
            from ..collectors.fred import FREDClient
            client = FREDClient()
        today = datetime.now(ET).date()
        start = f"{today.year - 1}-01-01"
        year_start = pd.Timestamp(year=today.year, month=1, day=1)
        rows: list[dict] = []
        for series_id, label in _CURVE_SERIES:
            s = client.get_observations(series_id, observation_start=start).dropna()
            if s.empty:
                continue
            level = float(s.iloc[-1])
            chg_1d_bp = (level - float(s.iloc[-2])) * 100 if len(s) >= 2 else None
            # YTD = vs the last close of the prior calendar year.
            prior = s[s.index < year_start]
            ytd_bp = (level - float(prior.iloc[-1])) * 100 if not prior.empty else None
            rows.append({
                "label": label,
                "level": level,
                "chg_1d_bp": chg_1d_bp,
                "ytd_bp": ytd_bp,
                "asof": s.index[-1].strftime("%Y-%m-%d"),
            })
        return rows or None
    except Exception:  # noqa: BLE001 — curve panel is optional; never break the dashboard
        return None


def render_dashboard(
    families: dict[str, FamilyConfig],
    output_path: Path | None = None,
    curve: list[dict] | None = None,
    fetch_curve: bool = True,
) -> Path:
    """Render the dashboard HTML to outputs/dashboard/index.html (or
    `output_path` if provided). Returns the written path.

    The US Treasury curve (2/10/30) is fetched best-effort from FRED unless
    `curve` is supplied or `fetch_curve` is False (tests pass these to stay
    offline). A failed/empty fetch simply omits the panel.
    """
    if output_path is None:
        output_path = outputs_root() / "dashboard" / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if curve is None and fetch_curve:
        curve = fetch_treasury_curve()

    latest_dir = outputs_root() / "latest"

    # Order families by tier then by display name so the dashboard reads
    # consistently regardless of YAML order.
    sorted_families = sorted(
        families.items(),
        key=lambda kv: (kv[1].tier, kv[1].display_name),
    )

    stats = {"families_total": len(families), "with_data": 0, "stale": 0}

    # Bucket each card under its family.group (empty → the default section), so
    # consumer-related families render together under a "Consumer" header.
    group_cards: dict[str, list[str]] = {}

    def _add(group: str, card: str) -> None:
        group_cards.setdefault(group or "", []).append(card)

    for _family_key, family in sorted_families:
        # Artifacts are stored under the slugified display name (see
        # outputs.family_slug), NOT the YAML config key — the two only
        # coincidentally match for some families.
        slug = family_slug(family.display_name)
        latest_json = latest_dir / f"{slug}.json"
        if not latest_json.exists():
            _add(family.group, _render_card_no_data(slug, family))
            continue
        try:
            payload = json.loads(latest_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _add(family.group, _render_card_no_data(slug, family))
            continue

        stats["with_data"] += 1
        if payload.get("is_stale"):
            stats["stale"] += 1

        _add(family.group, _render_card(slug, family, payload))

    body_html = _HTML_TEMPLATE.format(
        generated_at=datetime.now(ET).strftime("%a %b %d %Y %H:%M ET"),
        families_total=stats["families_total"],
        families_with_data=stats["with_data"],
        families_stale=stats["stale"],
        stale_class=" warn" if stats["stale"] else "",
        curve_panel=_render_curve_panel(curve),
        sections=_render_sections(group_cards),
    )
    output_path.write_text(body_html, encoding="utf-8")
    return output_path


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>macro-monitor — US current state</title>
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
  .section {{ font-size: 1.15em; color: #1F4E79; margin: 1.6em 0 0.5em;
              border-bottom: 2px solid #e0e0e0; padding-bottom: 0.2em; }}
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
                  margin: 0.6em 0; border: 1px solid #eee; border-radius: 4px;
                  cursor: zoom-in; }}
  /* Click-to-zoom lightbox: hidden until an img is clicked (see <script>). */
  .lightbox {{ display: none; position: fixed; inset: 0; z-index: 1000;
               background: rgba(0,0,0,0.85); cursor: zoom-out;
               align-items: center; justify-content: center; padding: 2vh 2vw; }}
  .lightbox.open {{ display: flex; }}
  .lightbox img {{ max-width: 96vw; max-height: 96vh; object-fit: contain;
                   border-radius: 4px; box-shadow: 0 4px 30px rgba(0,0,0,0.5); }}
  .lightbox .close {{ position: absolute; top: 1rem; right: 1.4rem; color: #fff;
                      font-size: 2rem; line-height: 1; cursor: pointer; }}
  .links {{ display: flex; gap: 0.5em; font-size: 0.8em; margin-top: 0.6em; }}
  .links a {{ color: #1F4E79; text-decoration: none; padding: 0.2em 0.5em;
              background: #f0f4f8; border-radius: 3px; }}
  .links a:hover {{ background: #1F4E79; color: white; }}
  .footer {{ font-size: 0.8em; color: #888; margin-top: 2em; padding-top: 1em; border-top: 1px solid #e0e0e0; }}
  .stale-badge {{ display: inline-block; background: #FEE2E2; color: #B91C1C; font-size: 0.7em;
                  padding: 0.1em 0.4em; border-radius: 3px; margin-left: 0.5em; }}
  .hc-badge {{ display: inline-block; background: #E8F0E0; color: #2D5016; font-size: 0.7em;
               padding: 0.1em 0.4em; border-radius: 3px; margin-left: 0.4em; }}
  .wc-badge {{ display: inline-block; background: #E0EAF5; color: #1F4E79; font-size: 0.7em;
               padding: 0.1em 0.4em; border-radius: 3px; margin-left: 0.4em; }}
  .accel {{ font-size: 0.72em; font-weight: 400; margin-left: 0.35em; }}
  .accel.up {{ color: #2D7D2D; }}
  .accel.down {{ color: #C00000; }}
  .defs {{ font-size: 0.72em; color: #888; margin-top: 0.6em; line-height: 1.4;
           border-top: 1px dashed #eee; padding-top: 0.4em; }}
  .curve {{ background: white; border: 1px solid #e0e0e0; border-radius: 6px;
            padding: 1em; margin-bottom: 1.5em; }}
  .curve h2 {{ font-size: 1.05em; margin: 0 0 0.1em 0; color: #1F4E79; }}
  .curve .period {{ font-size: 0.8em; color: #888; margin-bottom: 0.7em; }}
  .curve-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 1em; }}
  .tenor {{ border: 1px solid #eee; border-radius: 5px; padding: 0.6em 0.8em; }}
  .tenor .t-label {{ font-size: 0.8em; color: #666; }}
  .tenor .t-level {{ font-size: 1.5em; font-weight: 600; color: #222;
                     font-variant-numeric: tabular-nums; }}
  .tenor .t-chg {{ font-size: 0.82em; font-variant-numeric: tabular-nums; }}
  /* Bond convention: a yield RISE is a price-negative event → red. */
  .t-up {{ color: #C00000; }}
  .t-down {{ color: #2D7D2D; }}
</style>
</head>
<body>

<h1>macro-monitor — US current state</h1>
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

{curve_panel}

{sections}

<div class="footer">
  Generated by <code>macro_monitor.charts.dashboard</code>.
  Each card links to the per-release HTML report and the agency PDF.
  Click any chart to zoom. Future GitHub Pages deploy = <code>git push</code> of <code>outputs/</code>.
</div>

<div class="lightbox" id="lightbox" role="dialog" aria-modal="true" aria-label="Enlarged chart">
  <span class="close" aria-hidden="true">&times;</span>
  <img id="lightbox-img" alt="enlarged chart">
</div>
<script>
(function () {{
  var box = document.getElementById('lightbox');
  var boxImg = document.getElementById('lightbox-img');
  function close() {{ box.classList.remove('open'); boxImg.removeAttribute('src'); }}
  document.querySelectorAll('img.chart-thumb').forEach(function (img) {{
    img.addEventListener('click', function () {{
      boxImg.src = img.getAttribute('src');
      box.classList.add('open');
    }});
  }});
  box.addEventListener('click', close);
  document.addEventListener('keydown', function (e) {{ if (e.key === 'Escape') close(); }});
}})();
</script>

</body>
</html>
"""


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _fmt_bp(bp: float | None) -> tuple[str, str]:
    """Return (text, css-class) for a basis-point change, colored bond-style
    (a yield rise is price-negative → red)."""
    if bp is None:
        return "—", ""
    sign = "+" if bp >= 0 else ""
    cls = "t-up" if bp > 0 else ("t-down" if bp < 0 else "")
    return f"{sign}{bp:.0f} bp", cls


# Preferred section order; named groups not listed here follow alphabetically,
# and the default (ungrouped) section renders last as "Other US macro".
_SECTION_ORDER = ["Consumer"]
_DEFAULT_SECTION_TITLE = "Other US macro"


def _render_sections(group_cards: dict[str, list[str]]) -> str:
    """Render each family group as a titled section (header + its own card
    grid). Consumer first, other named groups alphabetically, ungrouped last."""
    named = [g for g in group_cards if g]
    ordered = [g for g in _SECTION_ORDER if g in group_cards]
    ordered += sorted(g for g in named if g not in _SECTION_ORDER)
    if "" in group_cards:
        ordered.append("")  # default/ungrouped section last

    out: list[str] = []
    for g in ordered:
        cards = group_cards.get(g) or []
        if not cards:
            continue
        title = g if g else _DEFAULT_SECTION_TITLE
        out.append(f"<h2 class='section'>{html.escape(title)}</h2>")
        out.append("<div class='grid'>")
        out.append("\n".join(cards))
        out.append("</div>")
    return "\n".join(out)


def _render_curve_panel(curve: list[dict] | None) -> str:
    """Render the US Treasury curve (2/10/30) panel, or '' if no data."""
    if not curve:
        return ""
    asof = max((r.get("asof", "") for r in curve), default="")
    tenors = []
    for r in curve:
        d1_txt, d1_cls = _fmt_bp(r.get("chg_1d_bp"))
        ytd_txt, ytd_cls = _fmt_bp(r.get("ytd_bp"))
        tenors.append(
            f"<div class='tenor'>"
            f"<div class='t-label'>{html.escape(r['label'])}</div>"
            f"<div class='t-level'>{r['level']:.2f}%</div>"
            f"<div class='t-chg'>1d <span class='{d1_cls}'>{d1_txt}</span> · "
            f"YTD <span class='{ytd_cls}'>{ytd_txt}</span></div>"
            f"</div>"
        )
    return (
        f"<div class='curve' id='treasury-curve'>"
        f"<h2>US Treasury curve — 2 / 10 / 30-Year</h2>"
        f"<div class='period'>Constant-maturity close · FRED (DGS2/DGS10/DGS30) · "
        f"as of {html.escape(asof)}. Rising yield shown red (price-negative).</div>"
        f"<div class='curve-grid'>" + "".join(tenors) + "</div>"
        f"</div>"
    )


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
    if transform in {"mom_chg", "yoy_chg"}:
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
    "yoy_chg": "y/y chg",
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


def _accel_html(
    cur: float | None,
    prior: float | None,
    prior_3m: float | None = None,
    tol: float = 0.005,
) -> str:
    """Small accel/decel marker for a YoY read: is the growth RATE rising or
    falling? The glyph tracks the vs-prior-month comparison (space-constrained
    card row); the hover title carries BOTH comparisons — vs prior month AND
    vs 3 months ago (JP ask 2026-07-04). '' when cur/prior are missing."""
    if cur is None or prior is None:
        return ""

    def _dir(ref: float) -> str:
        if cur > ref + tol:
            return "rising"
        if cur < ref - tol:
            return "falling"
        return "unchanged"

    title = f"YoY pace vs prior month ({prior:+.2f}%): {_dir(prior)}"
    if prior_3m is not None:
        title += f"; vs 3m ago ({prior_3m:+.2f}%): {_dir(prior_3m)}"
    d1 = _dir(prior)
    if d1 == "rising":
        return f"<span class='accel up' title='{title}'>▲ accel</span>"
    if d1 == "falling":
        return f"<span class='accel down' title='{title}'>▼ decel</span>"
    return f"<span class='accel' title='{title}'>→ flat</span>"


def _render_card(family_id: str, family: FamilyConfig, payload: dict) -> str:
    stale = payload.get("is_stale", False)
    from_cache = payload.get("from_fallback_cache", False)
    card_class = "card stale" if (stale or from_cache) else "card"
    period_label = payload.get("period_label", payload.get("period", "?"))

    # Headline rows. Rate-LEVEL series (U-3, U-6, quits rate…) render their
    # level with its % and their mom_chg/yoy_chg context as percentage-point
    # ("pp") deltas — never a bare number (JP 2026-07-04). display_unit comes
    # from the payload (schema 1.2+) with a config fallback for older JSONs.
    unit_by_id = {s.id: s.display_unit for s in family.headline}
    headline_rows = []
    for h in payload.get("headline", []):
        label = html.escape(h.get("label", h.get("id", "?")))
        primary = h.get("primary", {})
        transform = primary.get("transform", "raw")
        unit = h.get("display_unit") or unit_by_id.get(h.get("id"))
        rate_level = transform == "raw" and unit == "%"
        value_str = _value_with_basis(primary.get("value"), transform)
        if rate_level and primary.get("value") is not None:
            value_str = (
                f"{_fmt_value(primary.get('value'), transform)}%"
                f"<span class='basis'>{html.escape(_basis_label(transform))}</span>"
            )

        def _also_str(ad, _rate_level=rate_level) -> str:
            if _rate_level and ad["transform"] in {"mom_chg", "yoy_chg"}:
                lbl = "m/m" if ad["transform"] == "mom_chg" else "y/y"
                return f"{ad['value']:+.1f}pp {lbl}"
            return f"{_fmt_value(ad['value'], ad['transform'])} {_basis_label(ad['transform'])}"

        also = h.get("also_display", [])
        also_str = (
            " · ".join(
                _also_str(ad) for ad in also if ad.get("value") is not None
            )
        )
        also_html = f"<span class='also'>{html.escape(also_str)}</span>" if also_str else ""
        headline_rows.append(
            f"<div class='headline'>"
            f"<span class='headline-label'>{label}</span>"
            f"<span class='headline-value'>{value_str}{also_html}</span>"
            f"</div>"
        )

    # Tagged context lines (computed aggregates + tagged components):
    # healthcare (HC badge) and white-collar (WC badge, with an accel/decel
    # marker on YoY reads — is the growth rate rising or falling?).
    _BADGES = {"healthcare": "<span class='hc-badge'>HC</span>",
               "white_collar": "<span class='wc-badge'>WC</span>"}
    hc_lines = []
    for tag, badge in _BADGES.items():
        for c in payload.get("computed", []) or []:
            if tag in (c.get("tags") or []):
                tv = c.get("transformed") or {}
                prior = c.get("prior_primary") or {}
                prior_3m = c.get("prior_3m_primary") or {}
                accel = (
                    _accel_html(
                        tv.get("value"), prior.get("value"), prior_3m.get("value")
                    )
                    if tv.get("transform") == "yoy_pct"
                    else ""
                )
                hc_lines.append(
                    f"<div class='headline'>"
                    f"<span class='headline-label'>{html.escape(c.get('label', '?'))} "
                    f"{badge}</span>"
                    f"<span class='headline-value'>{_value_with_basis(tv.get('value'), tv.get('transform', 'raw'))}{accel}</span>"
                    f"</div>"
                )
        for c in payload.get("components", []) or []:
            if tag in (c.get("tags") or []):
                prior = c.get("prior") or {}
                prior_3m = c.get("prior_3m") or {}
                accel = (
                    _accel_html(
                        c.get("value"), prior.get("value"), prior_3m.get("value")
                    )
                    if c.get("transform") == "yoy_pct"
                    else ""
                )
                hc_lines.append(
                    f"<div class='headline'>"
                    f"<span class='headline-label'>↳ {html.escape(c.get('label', '?'))}</span>"
                    f"<span class='headline-value'>{_value_with_basis(c.get('value'), c.get('transform', 'raw'))}{accel}</span>"
                    f"</div>"
                )

    # Plain-English definitions footnote (U-3 vs U-6, computed aggregates…)
    _defs: list[str] = []
    for coll in ("headline", "computed", "components"):
        for s in payload.get(coll) or []:
            d = s.get("definition")
            if d and d not in _defs:
                _defs.append(d)
    defs_html = (
        "<div class='defs'>"
        + "<br>".join(f"ℹ️ {html.escape(d)}" for d in _defs)
        + "</div>"
        if _defs
        else ""
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
        f"<div class='{card_class}' id='fam-{html.escape(family_id)}'>"
        f"<h2>{html.escape(family.display_name)}{stale_badge}{cache_badge}</h2>"
        f"<div class='period'>{html.escape(period_label)}</div>"
        + "".join(headline_rows)
        + "".join(hc_lines)
        + defs_html
        + chart_html
        + links_html
        + "</div>"
    )


def _render_card_no_data(family_id: str, family: FamilyConfig) -> str:
    return (
        f"<div class='card nodata' id='fam-{html.escape(family_id)}'>"
        f"<h2>{html.escape(family.display_name)}</h2>"
        f"<div class='period'>no data yet — first release post will populate</div>"
        f"</div>"
    )
