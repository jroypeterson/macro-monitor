"""Output writers: JSON snapshot + HTML report per release.

Both live under outputs/archive/<family>/<period>.{json,html} with
pointers in outputs/latest/. The HTML report is a human-readable sibling
of the same data — embedded chart images, agency PDF link, source
freshness footer — designed to be viewed by double-clicking the file
in Explorer / Finder.
"""

from __future__ import annotations

import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .release_runner import ReleaseResult

SCHEMA_VERSION = "1.0"


def outputs_root() -> Path:
    """Project-relative outputs directory."""
    return Path(__file__).parent / "outputs"


def archive_paths(family_id: str, period: str) -> tuple[Path, Path]:
    root = outputs_root() / "archive" / family_id
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{period}.json", root / f"{period}.html"


def latest_paths(family_id: str) -> tuple[Path, Path]:
    root = outputs_root() / "latest"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{family_id}.json", root / f"{family_id}.html"


def write_release_artifacts(
    result: ReleaseResult,
    chart_paths: dict[str, Path],
    agency_pdf_url: str | None,
) -> tuple[Path, Path]:
    """Write the JSON snapshot + HTML report for a release.

    `chart_paths` is {chart_name: Path}. The HTML references each chart by
    its filename via a relative path so the report is self-contained when
    the user opens it from outputs/archive/<family>/.

    Returns (json_path, html_path) of the archive entries.
    """
    family_id = _family_id(result.family_display_name)
    json_archive, html_archive = archive_paths(family_id, result.period)
    json_latest, html_latest = latest_paths(family_id)

    # === JSON snapshot ===
    payload = {
        "schema_version": SCHEMA_VERSION,
        "family_id": family_id,
        "family_display_name": result.family_display_name,
        "period": result.period,
        "period_label": result.period_label,
        "posted_at": datetime.now(timezone.utc).isoformat(),

        # Source freshness (per plan §3)
        "source": result.source,
        "source_fetched_at": result.source_fetched_at,
        "latest_observation_period": result.latest_observation_period,
        "expected_observation_period": result.expected_observation_period,
        "is_stale": result.is_stale,
        "source_lag_minutes": result.source_lag_minutes,
        # Defensive-cache fallback (true if FRED was unreachable and we
        # served last-known-good from data/fred_cache.db).
        "from_fallback_cache": result.from_fallback_cache,
        "cache_age_hours": result.cache_age_hours,

        # Data
        "headline": [_serialize_headline(h) for h in result.headline],
        "components": [_serialize_component(c) for c in result.components],
        "context": _serialize_context(result.context) if result.context else None,

        # Charts (paths relative to the archive directory)
        "charts": {
            name: str(path.name) for name, path in chart_paths.items()
        },
        "agency_pdf_url": agency_pdf_url,
    }
    json_archive.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )

    # === HTML report ===
    html_archive.write_text(_render_html(result, payload, chart_paths), encoding="utf-8")

    # === Latest pointers (copies, not symlinks — Windows-friendly) ===
    shutil.copy2(json_archive, json_latest)
    shutil.copy2(html_archive, html_latest)

    return json_archive, html_archive


def family_slug(display_name: str) -> str:
    """Slugify a family display name to the stable id used as the
    filesystem path for archive/ and latest/ artifacts.

    This is the single source of truth for how a family maps to its
    on-disk filename — readers (e.g. the dashboard) must use this rather
    than the YAML config key, which only coincidentally matches the slug
    for some families.
    """
    return (
        display_name.lower()
        .replace(" ", "_")
        .replace("&", "and")
        .replace("/", "_")
    )


# Backwards-compatible private alias (kept for existing call sites).
_family_id = family_slug


def _serialize_headline(h) -> dict:
    return {
        "id": h.id,
        "label": h.label,
        "primary": {
            "transform": h.primary.transform,
            "value": h.primary.value,
            "raw_value": h.primary.raw_value,
        },
        "also_display": [
            {"transform": tv.transform, "value": tv.value} for tv in h.also_display
        ],
        "prior_primary": (
            {
                "transform": h.prior_primary.transform,
                "value": h.prior_primary.value,
            }
            if h.prior_primary
            else None
        ),
    }


def _serialize_component(c) -> dict:
    return {
        "id": c.id,
        "label": c.label,
        "transform": c.transformed.transform,
        "value": c.transformed.value,
        "tags": c.tags,
    }


def _serialize_context(ctx) -> dict:
    return {
        "anchor_series": ctx.anchor_series,
        "anchor_transform": ctx.anchor_transform,
        "zscore": ctx.zscore,
        "zscore_kind": ctx.zscore_kind,
        "zscore_lookback_years": ctx.zscore_lookback_years,
        "trends": [
            {
                "label": t.label,
                "value": t.value,
                "window_months": t.window_months,
                "stat": t.stat,
            }
            for t in ctx.trends
        ],
    }


# ---------------------------------------------------------------------------
# HTML rendering — small inline-CSS template; no external deps.
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{display_name} — {period_label}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
          max-width: 900px; margin: 2em auto; padding: 0 1em; color: #222; }}
  h1 {{ font-size: 1.8em; margin-bottom: 0.2em; }}
  h2 {{ font-size: 1.2em; margin-top: 1.6em; border-bottom: 1px solid #ddd; padding-bottom: 0.2em; }}
  .period-label {{ color: #555; font-weight: normal; }}
  .freshness {{ background: #f6f8fa; border-left: 3px solid #1F4E79;
                padding: 0.5em 1em; margin: 1em 0; font-size: 0.9em; color: #444; }}
  .stale {{ border-left-color: #C00000; }}
  table {{ width: 100%; border-collapse: collapse; margin: 0.6em 0; }}
  th, td {{ text-align: left; padding: 0.4em 0.6em; border-bottom: 1px solid #eee; }}
  th {{ background: #fafafa; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .chart {{ margin: 1em 0; }}
  .chart img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; }}
  .agency-link {{ display: inline-block; margin-top: 0.6em; padding: 0.4em 0.8em;
                  background: #1F4E79; color: white; text-decoration: none; border-radius: 4px; }}
  .agency-link:hover {{ background: #163955; }}
  .footer {{ font-size: 0.8em; color: #666; margin-top: 2em; padding-top: 1em; border-top: 1px solid #eee; }}
  .tag {{ display: inline-block; background: #E8F0E0; color: #2D5016; font-size: 0.7em;
          padding: 0.1em 0.4em; border-radius: 3px; margin-left: 0.4em; }}
</style>
</head>
<body>

<h1>{display_name} <span class="period-label">— {period_label}</span></h1>

<div class="freshness{stale_class}">
  <strong>Source:</strong> {source} ·
  <strong>Fetched:</strong> {source_fetched_at} ·
  <strong>Latest observation:</strong> {latest_observation_period} ·
  <strong>Expected:</strong> {expected_observation_period} ·
  <strong>Stale:</strong> {is_stale}
</div>

<h2>Headline</h2>
{headline_table}

{context_section}

{components_section}

<h2>Charts</h2>
{charts_section}

{agency_section}

<div class="footer">
  Generated by <a href="https://github.com/jroypeterson/macro-monitor">macro-monitor</a>
  · schema {schema_version} · period {period}
</div>

</body>
</html>
"""


def _fmt_value(value: float | None, transform: str) -> str:
    if value is None:
        return "—"
    if transform in {"yoy_pct", "mom_pct", "annualized_mom", "qoq_pct_saar"}:
        return f"{value:.2f}%"
    if transform == "mom_chg":
        # Levels — payrolls in thousands, etc. Caller's label clarifies units.
        return f"{value:+,.1f}"
    if transform == "raw":
        return f"{value:.2f}"
    return f"{value:.3f}"


def _render_headline_table(payload: dict) -> str:
    rows = []
    for h in payload["headline"]:
        primary = h["primary"]
        primary_str = _fmt_value(primary["value"], primary["transform"])
        also = " · ".join(
            f"{ad['transform']} {_fmt_value(ad['value'], ad['transform'])}"
            for ad in h["also_display"]
        )
        prior = h.get("prior_primary")
        prior_str = (
            _fmt_value(prior["value"], prior["transform"]) if prior else "—"
        )
        rows.append(
            f"<tr><td><strong>{html.escape(h['label'])}</strong> "
            f"<small style='color:#888'>({html.escape(h['id'])})</small></td>"
            f"<td class='num'>{primary_str}</td>"
            f"<td>{html.escape(also)}</td>"
            f"<td class='num'>{prior_str}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Series</th><th>Primary</th>"
        "<th>Also</th><th>Prior</th></tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table>"
    )


def _render_components_section(payload: dict) -> str:
    components = payload["components"]
    if not components:
        return ""
    rows = []
    for c in components:
        tag_html = "".join(
            f"<span class='tag'>{html.escape(t)}</span>" for t in c.get("tags", [])
        )
        rows.append(
            f"<tr><td>{html.escape(c['label'])} "
            f"<small style='color:#888'>({html.escape(c['id'])})</small> {tag_html}</td>"
            f"<td>{html.escape(c['transform'])}</td>"
            f"<td class='num'>{_fmt_value(c['value'], c['transform'])}</td></tr>"
        )
    return (
        "<h2>Components (thread)</h2>"
        "<table><thead><tr><th>Series</th><th>Transform</th><th>Value</th></tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table>"
    )


def _render_context_section(payload: dict) -> str:
    ctx = payload.get("context")
    if not ctx:
        return ""
    rows = []
    for t in ctx["trends"]:
        rows.append(
            f"<tr><td>{html.escape(t['label'])}</td>"
            f"<td>{html.escape(t['stat'])}</td>"
            f"<td class='num'>{_fmt_value(t['value'], 'yoy_pct')}</td></tr>"
        )
    zscore_str = (
        f"{ctx['zscore']:+.2f}σ" if ctx["zscore"] is not None else "—"
    )
    return (
        "<h2>Context</h2>"
        f"<p><strong>Anchor:</strong> {html.escape(ctx['anchor_series'])} "
        f"({html.escape(ctx['anchor_transform'])}) · "
        f"<strong>{html.escape(ctx['zscore_kind'])} z-score vs {ctx['zscore_lookback_years']}y:</strong> "
        f"{zscore_str}</p>"
        "<table><thead><tr><th>Trend</th><th>Stat</th><th>Value</th></tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table>"
    )


def _render_charts_section(chart_paths: dict[str, Path]) -> str:
    """Reference each chart by filename so the HTML works when opened from
    outputs/archive/<family>/."""
    blocks = []
    for name, path in chart_paths.items():
        # Charts live in outputs/charts/; archive entries in outputs/archive/<family>/.
        # We need a relative href from the archive dir to the charts dir.
        rel = f"../../charts/{path.name}"
        blocks.append(
            f"<div class='chart'><h3 style='font-size:1em;color:#555'>"
            f"{html.escape(name)}</h3>"
            f"<img src='{html.escape(rel)}' alt='{html.escape(name)}'></div>"
        )
    return "\n".join(blocks)


def _render_agency_section(agency_pdf_url: str | None) -> str:
    if not agency_pdf_url:
        return ""
    return (
        "<h2>Official release</h2>"
        f"<a class='agency-link' href='{html.escape(agency_pdf_url)}' target='_blank'>"
        f"View on agency site (PDF) ↗</a>"
    )


def _render_html(
    result: ReleaseResult, payload: dict, chart_paths: dict[str, Path]
) -> str:
    return _HTML_TEMPLATE.format(
        display_name=html.escape(payload["family_display_name"]),
        period_label=html.escape(payload["period_label"]),
        period=html.escape(payload["period"]),
        source=html.escape(payload["source"]),
        source_fetched_at=html.escape(payload["source_fetched_at"]),
        latest_observation_period=html.escape(payload["latest_observation_period"]),
        expected_observation_period=html.escape(payload["expected_observation_period"]),
        is_stale="yes" if payload["is_stale"] else "no",
        stale_class=" stale" if payload["is_stale"] else "",
        headline_table=_render_headline_table(payload),
        context_section=_render_context_section(payload),
        components_section=_render_components_section(payload),
        charts_section=_render_charts_section(chart_paths),
        agency_section=_render_agency_section(payload.get("agency_pdf_url")),
        schema_version=SCHEMA_VERSION,
    )
