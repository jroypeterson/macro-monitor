"""Build the Ahead-of-the-Curve charts: fetch FRED series, render each figure to a
PNG, and write an index.html gallery so the set can be viewed from one file.

Run: ``python -m macro_monitor.ahead_of_curve.build``
  or ``python -m macro_monitor.cli ahead-of-curve``

Outputs land in ``macro_monitor/readable/ahead_of_curve/`` (per OUTPUT_CONVENTIONS:
human-openable, one level below project root, flat filenames).
"""
from __future__ import annotations

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

_DIR = Path(__file__).parent
_FIGURES_YAML = _DIR / "figures.yaml"
_BEARS_YAML = _DIR / "bear_markets.yaml"
_OUT_DIR = _DIR.parent / "readable" / "ahead_of_curve"
# Pull deep history so the 35-year windows + YoY lookback are fully covered.
_OBS_START = "1945-01-01"


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
                         out_path: Path, generated_label: str) -> Path:
    cards = []
    for f in figs:
        png = rendered.get(f.id)
        if png is None:
            continue
        cards.append(
            f'<section><h2>{f.title}</h2>'
            f'<p class="sub">{f.subtitle}</p>'
            f'<img src="{png.name}" alt="{f.title}"/></section>'
        )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Ahead of the Curve — Charts</title>
<style>
 body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 980px;
        margin: 2rem auto; padding: 0 1rem; color: #222; }}
 h1 {{ font-size: 1.5rem; }}
 .meta {{ color: #777; font-size: .85rem; margin-bottom: 2rem; }}
 section {{ margin: 2.5rem 0; }}
 h2 {{ font-size: 1.1rem; margin-bottom: .2rem; }}
 .sub {{ color: #555; font-size: .9rem; margin: 0 0 .6rem; }}
 img {{ width: 100%; border: 1px solid #e2e2e2; border-radius: 6px; }}
</style></head><body>
<h1>Ahead of the Curve — Charts</h1>
<p class="meta">Recreation of Joseph Ellis's charts · year-over-year rate of change ·
shaded bands = S&amp;P 500 bear markets · {generated_label} · {len(cards)} charts</p>
{''.join(cards)}
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
    fetched = fetch_series(client, needed)
    recessions = recession_ranges(fetched["USREC"]) if "USREC" in fetched else []

    # Anchor the right edge of every chart to the latest available real-PCE point,
    # falling back to the newest date across all fetched series.
    end = None
    for anchor in ("PCEC96",):
        s = fetched.get(anchor)
        if s is not None and not s.dropna().empty:
            end = s.dropna().index.max()
            break
    if end is None:
        all_idx = [s.dropna().index.max() for s in fetched.values() if not s.dropna().empty]
        end = max(all_idx) if all_idx else pd.Timestamp.today().normalize()

    out_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, Path] = {}
    for f in figs:
        try:
            rendered[f.id] = render_figure(
                f, fetched, bears, recessions, end,
                out_dir / f"{f.id}.png", source_note=source_note,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] ahead-of-curve: figure {f.id} failed: {exc}")

    generated_label = f"data through {end.date()}"
    index = _render_gallery_html(figs, rendered, out_dir / "index.html", generated_label)
    rendered["index"] = index
    return rendered


if __name__ == "__main__":
    out = build()
    for name, path in out.items():
        print(f"  {name}: {path}")
    if "index" in out:
        print(f"\nOpen: file://{out['index'].absolute()}")
