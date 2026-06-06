"""Build the Ahead-of-the-Curve charts: fetch FRED series, render each figure to a
PNG, and write an index.html gallery so the set can be viewed from one file.

Run: ``python -m macro_monitor.ahead_of_curve.build``
  or ``python -m macro_monitor.cli ahead-of-curve``

Outputs land in ``macro_monitor/readable/ahead_of_curve/`` (per OUTPUT_CONVENTIONS:
human-openable, one level below project root, flat filenames).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd
import yaml

from ..collectors.fred import FREDClient
from .charts import (
    FigureSpec,
    parse_bear_markets,
    parse_figures,
    recession_ranges,
    render_figure,
)
from .schedule import SERIES_RELEASE_ID, figure_footnotes, next_release_dates
from .sp500 import SP500_KEY, fetch_sp500_daily, to_monthly
from .stats import series_average_lines, timeline_stat_lines
from .summary import key_takeaways

_DIR = Path(__file__).parent
_FIGURES_YAML = _DIR / "figures.yaml"
_BEARS_YAML = _DIR / "bear_markets.yaml"
_OUT_DIR = _DIR.parent / "readable" / "ahead_of_curve"
# Pull deep history: USREC reaches back to 1854 (for the full bear/recession timeline);
# the economic series return their own natural start. The long windows + YoY lookback
# are thus always fully covered.
_OBS_START = "1854-01-01"

# Band variants rendered per figure (for the gallery's on/off image-swap toggle).
# Suffix "" is the default "both" image the gallery shows first.
BAND_VARIANTS = {"both": "", "bear": "_bear", "recession": "_rec", "none": "_none"}

# Glossary of the terms used across this chartpack — rendered at the bottom of the
# page so a reader new to Ellis's lens can decode the charts without leaving it.
# (term, definition) pairs, kept static; HTML-escape-safe plain text.
_GLOSSARY_TERMS: list[tuple[str, str]] = [
    ("Year-over-year (YoY) rate of change",
     "Each series is plotted as its percent change versus the same month one year "
     "earlier, not the raw level. This is Ellis's core lens — turning points in the "
     "<em>rate of change</em> tend to lead the level (and the market)."),
    ("Acceleration / deceleration",
     "The change in the YoY rate itself (its direction of travel). Ellis watches "
     "whether growth is speeding up or slowing down, even while still positive — "
     "deceleration is the early warning, not an outright decline."),
    ("Real (vs nominal)",
     "Inflation-adjusted. A nominal dollar series is divided by a price deflator so the "
     "chart shows volume/quantity growth rather than price growth."),
    ("Deflator",
     "The price index used to convert a nominal ($) series into a real (inflation-"
     "adjusted) one — e.g. the PCE price index for real consumer spending."),
    ("S&amp;P 500 bear markets (grey bands)",
     "Shaded peak-to-trough declines of roughly 20% or more in the S&amp;P 500, dated "
     "from the index's monthly closes. They show how the macro rate-of-change led or "
     "lagged equity drawdowns. Toggle on/off per chart or for all charts."),
    ("NBER recessions (dotted red)",
     "Official US recession periods as dated by the National Bureau of Economic "
     "Research (FRED series USREC). Toggle on/off alongside the bear bands."),
    ("Averages (1-yr · 10-yr · full history)",
     "Each data chart's footnote lists the trailing mean of the plotted series over "
     "the last year, the last ten years, and its full available history — context for "
     "whether the latest reading is hot or cold versus its own past."),
    ("Release schedule",
     "Where shown, the date the next data point for that series is expected and the "
     "reference period it will cover — so you know how stale the right edge is."),
    ("Band toggles",
     "The checkboxes above each chart (and the 'show on ALL charts' pair at the top) "
     "switch the bear-market and recession overlays on or off by swapping the image."),
]


def _glossary_html() -> str:
    rows = "".join(f"<dt>{term}</dt><dd>{defn}</dd>" for term, defn in _GLOSSARY_TERMS)
    return (
        '<section id="glossary" class="glossary"><h2>Glossary</h2>'
        f'<dl>{rows}</dl>'
        '<p class="back"><a href="#top">↑ back to index</a></p></section>'
    )


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def fetch_series(client: FREDClient, ids: set[str]) -> dict[str, pd.Series]:
    """Fetch every needed series once. USREC is always pulled for the recession-band
    option. Missing/failed series are skipped (the figure renderer warns if a figure
    ends up empty)."""
    fetched: dict[str, pd.Series] = {}
    for sid in sorted(ids):
        try:
            fetched[sid] = client.get_observations(sid, observation_start=_OBS_START)
        except Exception as exc:  # noqa: BLE001 — one bad series shouldn't kill the run
            print(f"[WARN] ahead-of-curve: failed to fetch {sid}: {exc}")
    return fetched


def _render_gallery_html(figs: list[FigureSpec], rendered: dict[str, Path],
                         out_path: Path, generated_label: str,
                         note_blocks: dict[str, list[tuple[str, list[str]]]],
                         headline: str = "", takeaways: list[str] | None = None) -> Path:
    toc_items, cards = [], []
    for f in figs:
        png = rendered.get(f.id)
        if png is None:
            continue
        toc_items.append(f'<li><a href="#{f.id}">{f.title}</a></li>')
        foot_html = ""
        for header, lines in note_blocks.get(f.id, []):
            rows = "".join(f"<li>{line}</li>" for line in lines)
            foot_html += (f'<p class="foot-label">{header}</p>'
                          f'<ul class="foot">{rows}</ul>')
        toggles = (
            f'<div class="toggles">'
            f'<label><input type="checkbox" class="bear" data-base="{f.id}" checked '
            f'onchange="upd(this)"> S&amp;P bear bands</label>'
            f'<label><input type="checkbox" class="rec" data-base="{f.id}" checked '
            f'onchange="upd(this)"> NBER recessions</label></div>'
        )
        cards.append(
            f'<section id="{f.id}"><h2>{f.title}</h2>'
            f'<p class="sub">{f.subtitle}</p>'
            f'{toggles}'
            f'<img id="img_{f.id}" src="{png.name}" alt="{f.title}"/>'
            f'{foot_html}'
            f'<p class="back"><a href="#top">↑ back to index</a></p></section>'
        )
    toc_items.append('<li><a href="#glossary">Glossary of terms</a></li>')
    toc = f'<nav class="toc"><strong>Charts on this page</strong><ol>{"".join(toc_items)}</ol></nav>'
    summary_html = ""
    if takeaways:
        items = "".join(f"<li>{t}</li>" for t in takeaways)
        head = f'<p class="summary-head">{headline}</p>' if headline else ""
        summary_html = (
            f'<section class="summary"><h2>Key takeaways</h2>{head}'
            f'<ul>{items}</ul>'
            f'<p class="summary-note">Auto-generated from the latest data each build · '
            f'Ellis\'s lens: watch the <em>rate of change</em> of real consumer spending, '
            f'not just the level · not investment advice.</p></section>'
        )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Ahead of the Curve — Charts</title>
<style>
 body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 980px;
        margin: 2rem auto; padding: 0 1rem; color: #222; }}
 h1 {{ font-size: 1.5rem; margin-bottom: .2rem; }}
 .meta {{ color: #777; font-size: .85rem; margin-bottom: 1.5rem; }}
 .controls {{ background: #eef3f8; border: 1px solid #cfe0ef; border-radius: 8px;
              padding: .7rem 1.2rem; margin-bottom: 1.2rem; font-size: .9rem; }}
 .controls label {{ margin-right: 1.2rem; font-weight: 600; }}
 .toc {{ background: #f7f8fa; border: 1px solid #e2e2e2; border-radius: 8px;
         padding: .8rem 1.2rem; margin-bottom: 2.5rem; }}
 .toc ol {{ margin: .4rem 0 0; padding-left: 1.4rem; }}
 .toc li {{ margin: .2rem 0; }}
 .toc a {{ color: #1F4E79; text-decoration: none; }}
 .toc a:hover {{ text-decoration: underline; }}
 .summary {{ background: #fbfcfd; border: 1px solid #e2e2e2; border-left: 4px solid #1F4E79;
             border-radius: 8px; padding: 1rem 1.4rem; margin-bottom: 2.5rem; }}
 .summary h2 {{ margin: 0 0 .5rem; font-size: 1.05rem; }}
 .summary-head {{ font-size: .98rem; font-weight: 600; color: #1F4E79; margin: 0 0 .7rem; }}
 .summary ul {{ margin: 0; padding-left: 1.2rem; }}
 .summary li {{ margin: .35rem 0; font-size: .9rem; color: #333; }}
 .summary-note {{ font-size: .76rem; color: #999; margin: .8rem 0 0; }}
 section {{ margin: 2.5rem 0; scroll-margin-top: 1rem; }}
 h2 {{ font-size: 1.15rem; margin-bottom: .2rem; }}
 .sub {{ color: #555; font-size: .9rem; margin: 0 0 .5rem; }}
 .toggles {{ font-size: .82rem; color: #555; margin-bottom: .5rem; }}
 .toggles label {{ margin-right: 1.1rem; }}
 img {{ width: 100%; border: 1px solid #e2e2e2; border-radius: 6px; }}
 .foot-label {{ font-size: .75rem; text-transform: uppercase; letter-spacing: .04em;
                color: #999; margin: .8rem 0 .2rem; }}
 ul.foot {{ margin: 0; padding-left: 1.2rem; color: #555; font-size: .82rem; }}
 ul.foot li {{ margin: .15rem 0; }}
 .back {{ font-size: .8rem; margin-top: .6rem; }}
 .back a {{ color: #999; text-decoration: none; }}
 .glossary {{ background: #f7f8fa; border: 1px solid #e2e2e2; border-radius: 8px;
              padding: 1rem 1.4rem; margin-top: 3rem; }}
 .glossary h2 {{ margin: 0 0 .6rem; font-size: 1.1rem; }}
 .glossary dl {{ margin: 0; }}
 .glossary dt {{ font-weight: 600; color: #1F4E79; margin: .7rem 0 .15rem; font-size: .92rem; }}
 .glossary dd {{ margin: 0 0 .2rem; padding-left: 0; color: #444; font-size: .86rem; }}
</style></head><body>
<a id="top"></a>
<h1>Ahead of the Curve — Charts</h1>
<p class="meta">Recreation of Joseph Ellis's charts · year-over-year rate of change ·
grey bands = S&amp;P 500 bear markets · dotted red = NBER recessions · {generated_label} ·
{len(cards)} charts · <a href="../index.html">↑ workspace hub</a></p>
<div class="controls">Show bands on ALL charts:
 <label><input type="checkbox" id="allBear" checked onchange="setAll('bear', this.checked)"> S&amp;P bear bands</label>
 <label><input type="checkbox" id="allRec" checked onchange="setAll('rec', this.checked)"> NBER recessions</label>
</div>
{toc}
{summary_html}
{''.join(cards)}
{_glossary_html()}
<script>
function suffix(base){{
  var bear = document.querySelector('.bear[data-base="'+base+'"]').checked;
  var rec  = document.querySelector('.rec[data-base="'+base+'"]').checked;
  if (bear && rec) return '';
  if (bear) return '_bear';
  if (rec)  return '_rec';
  return '_none';
}}
function upd(el){{
  var base = el.dataset.base;
  document.getElementById('img_'+base).src = base + suffix(base) + '.png';
}}
function setAll(cls, on){{
  document.querySelectorAll('input.'+cls).forEach(function(b){{ b.checked = on; upd(b); }});
}}
</script>
</body></html>"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


def build(client: FREDClient | None = None, out_dir: Path = _OUT_DIR) -> dict[str, Path]:
    """Fetch + render every figure. Returns {figure_id: png_path} plus 'index' -> html."""
    figs, source_note = parse_figures(_load_yaml(_FIGURES_YAML))
    bears = parse_bear_markets(_load_yaml(_BEARS_YAML))

    needed: set[str] = {"USREC"}
    for f in figs:
        needed |= f.fred_ids()

    client = client or FREDClient()
    fetched = fetch_series(client, needed - {SP500_KEY})
    # S&P 500 long history comes from yfinance, not FRED (FRED's SP500 is ~10yr only).
    # Keep the daily series for accurate bear-market peak-to-trough stats; the charts use
    # the monthly resample.
    sp_daily = None
    if SP500_KEY in needed:
        try:
            sp_daily = fetch_sp500_daily()
            fetched[SP500_KEY] = to_monthly(sp_daily)
        except Exception as exc:  # noqa: BLE001 — S&P figures degrade gracefully
            print(f"[WARN] ahead-of-curve: S&P 500 (yfinance) fetch failed: {exc}")
    recessions = recession_ranges(fetched["USREC"]) if "USREC" in fetched else []

    # Anchor the right edge of every chart to the latest available real-PCE point,
    # falling back to the newest date across all fetched series.
    end = None
    for anchor in ("PCE",):
        s = fetched.get(anchor)
        if s is not None and not s.dropna().empty:
            end = s.dropna().index.max()
            break
    if end is None:
        all_idx = [s.dropna().index.max() for s in fetched.values() if not s.dropna().empty]
        end = max(all_idx) if all_idx else pd.Timestamp.today().normalize()

    out_dir.mkdir(parents=True, exist_ok=True)
    # Render four band variants per figure so the gallery can toggle overlays on/off
    # (image-swap): both (default), bear-only, recession-only, none.
    rendered: dict[str, Path] = {}
    for f in figs:
        for bands_val, suffix in BAND_VARIANTS.items():
            fv = dataclasses.replace(f, bands=bands_val)
            try:
                p = render_figure(
                    fv, fetched, bears, recessions, end,
                    out_dir / f"{f.id}{suffix}.png", source_note=source_note,
                )
                if bands_val == "both":
                    rendered[f.id] = p  # the default image shown in the gallery
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] ahead-of-curve: figure {f.id} ({bands_val}) failed: {exc}")

    # Release-schedule footnotes (when the next data point is expected, for what period).
    release_ids = {SERIES_RELEASE_ID[s.fred] for f in figs for s in f.series
                   if s.fred in SERIES_RELEASE_ID}
    next_dates = next_release_dates(client, release_ids)
    release = figure_footnotes(figs, fetched, next_dates)
    headline, takeaways = key_takeaways(fetched)
    timeline_stats = timeline_stat_lines(
        bears, recessions, sp_daily if sp_daily is not None else fetched.get(SP500_KEY))

    # Assemble per-figure note blocks: (header, [lines]). Release schedule + trailing
    # averages on the data charts; bear/recession statistics under the timeline.
    note_blocks: dict[str, list[tuple[str, list[str]]]] = {}
    for f in figs:
        blocks: list[tuple[str, list[str]]] = []
        if release.get(f.id):
            blocks.append(("Release schedule", release[f.id]))
        avg_lines = series_average_lines(f, fetched, end)
        if avg_lines:
            blocks.append(("Averages (short-term 1-yr · 10-yr · full history)", avg_lines))
        if f.id == "bear_recession_timeline" and timeline_stats:
            blocks.append(("Bear-market & recession statistics", timeline_stats))
        if blocks:
            note_blocks[f.id] = blocks

    generated_label = f"data through {end.date()}"
    index = _render_gallery_html(
        figs, rendered, out_dir / "index.html", generated_label, note_blocks,
        headline, takeaways)
    rendered["index"] = index
    return rendered


if __name__ == "__main__":
    out = build()
    for name, path in out.items():
        print(f"  {name}: {path}")
    if "index" in out:
        print(f"\nOpen: file://{out['index'].absolute()}")
