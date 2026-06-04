"""Render the Ahead-of-the-Curve figures to PNGs.

Pure-ish: takes pre-fetched FRED data ({series_id: pd.Series}) plus the parsed
figure/bear-market config, and writes one PNG per figure. The fetch lives in
build.py so this module stays testable without network.

Ellis's lens is year-over-year rate of change; real consumer spending leads the
cycle; bear markets are shaded behind the lines.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: no display needed for file output
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from ..charts.style import CYCLE, DEFAULT_DPI, DEFAULT_FIGSIZE  # noqa: E402

_BEAR_COLOR = "#9AA0A6"       # grey bands (bear markets, primary)
_RECESSION_COLOR = "#C0504D"  # muted red bands (NBER recessions, secondary)
_PCT_FORMATTER = plt.FuncFormatter(lambda v, _pos: f"{v:.0f}%")


# --------------------------------------------------------------------------- #
# Transforms
# --------------------------------------------------------------------------- #
def _infer_periods_per_year(series: pd.Series) -> int:
    """Guess observations-per-year from the index spacing so YoY uses the right
    period count (monthly -> 12, quarterly -> 4, weekly -> 52, annual -> 1)."""
    idx = series.dropna().index
    if len(idx) < 3:
        return 12
    median_days = float(pd.Series((idx[1:] - idx[:-1]).days).median())
    if median_days <= 10:
        return 52
    if median_days <= 45:
        return 12
    if median_days <= 100:
        return 4
    return 1


def yoy_pct(series: pd.Series) -> pd.Series:
    """Year-over-year percent change — the Ellis transform. Vectorized (unlike the
    scalar transforms.yoy_pct used for the digest); returns the whole YoY series."""
    s = series.dropna()
    periods = _infer_periods_per_year(s)
    return (s.pct_change(periods) * 100).dropna()


def real_deflate(nominal: pd.Series, deflator: pd.Series) -> pd.Series:
    """real = nominal / deflator, aligned on their shared index (both monthly here).
    Scaled to 100 at the deflator's first common point so the level is readable; the
    YoY transform applied downstream is scale-invariant anyway."""
    common = nominal.dropna().index.intersection(deflator.dropna().index)
    if common.empty:
        return pd.Series(dtype=float)
    ratio = nominal.reindex(common) / deflator.reindex(common)
    return (ratio / ratio.iloc[0] * 100.0).dropna()


# --------------------------------------------------------------------------- #
# Bands
# --------------------------------------------------------------------------- #
@dataclass
class BearMarket:
    start: pd.Timestamp
    end: pd.Timestamp
    name: str = ""


def parse_bear_markets(raw: dict) -> list[BearMarket]:
    out: list[BearMarket] = []
    for b in (raw or {}).get("bear_markets", []):
        out.append(
            BearMarket(
                start=pd.Timestamp(str(b["start"])),
                end=pd.Timestamp(str(b["end"])),
                name=str(b.get("name", "")),
            )
        )
    return out


def recession_ranges(usrec: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Collapse the FRED USREC 0/1 monthly flag into contiguous recession ranges."""
    s = usrec.dropna()
    ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    start: pd.Timestamp | None = None
    prev: pd.Timestamp | None = None
    for d, v in s.items():
        if v >= 0.5 and start is None:
            start = d
        elif v < 0.5 and start is not None:
            ranges.append((start, prev))
            start = None
        prev = d
    if start is not None and prev is not None:
        ranges.append((start, prev))
    return ranges


def _shade(ax, ranges, color, label) -> None:
    first = True
    for a, b in ranges:
        ax.axvspan(a, b, color=color, alpha=0.18, lw=0,
                   label=(label if first else None), zorder=0)
        first = False


# --------------------------------------------------------------------------- #
# Figure model + rendering
# --------------------------------------------------------------------------- #
@dataclass
class SeriesSpec:
    fred: str
    label: str
    transform: str = "yoy"
    divide_by: str | None = None


@dataclass
class FigureSpec:
    id: str
    title: str
    subtitle: str = ""
    bands: str = "bear"  # bear | recession | both | none
    lookback_years: int = 35
    series: list[SeriesSpec] = field(default_factory=list)

    def fred_ids(self) -> set[str]:
        ids: set[str] = set()
        for s in self.series:
            ids.add(s.fred)
            if s.divide_by:
                ids.add(s.divide_by)
        return ids


def parse_figures(raw: dict) -> tuple[list[FigureSpec], str]:
    default_lb = int(raw.get("default_lookback_years", 35))
    source_note = str(raw.get("source_note", ""))
    figs: list[FigureSpec] = []
    for f in raw.get("figures", []):
        series = [
            SeriesSpec(
                fred=s["fred"], label=s["label"],
                transform=s.get("transform", "yoy"),
                divide_by=s.get("divide_by"),
            )
            for s in f.get("series", [])
        ]
        figs.append(
            FigureSpec(
                id=f["id"], title=f["title"], subtitle=f.get("subtitle", ""),
                bands=f.get("bands", "bear"),
                lookback_years=int(f.get("lookback_years", default_lb)),
                series=series,
            )
        )
    return figs, source_note


def _plot_series(spec: SeriesSpec, fetched: dict[str, pd.Series]) -> tuple[pd.Series, bool]:
    """Return (values_series, is_pct) for one SeriesSpec. is_pct => format axis as %."""
    base = fetched.get(spec.fred)
    if base is None or base.dropna().empty:
        return pd.Series(dtype=float), spec.transform == "yoy"
    if spec.divide_by:
        deflator = fetched.get(spec.divide_by)
        if deflator is None or deflator.dropna().empty:
            return pd.Series(dtype=float), True
        base = real_deflate(base, deflator)
    if spec.transform == "yoy":
        return yoy_pct(base), True
    return base.dropna(), True  # 'raw' here is rate levels (also a percent)


def render_figure(
    fig_spec: FigureSpec,
    fetched: dict[str, pd.Series],
    bears: list[BearMarket],
    recessions: list[tuple[pd.Timestamp, pd.Timestamp]],
    end: pd.Timestamp,
    output_path: Path,
    source_note: str = "",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    start = end - pd.DateOffset(years=fig_spec.lookback_years)

    fig, ax = plt.subplots(figsize=DEFAULT_FIGSIZE, dpi=DEFAULT_DPI)

    # Bands first (behind the lines), clipped to window.
    def _clip(a, b):
        return max(a, start), min(b, end)

    if fig_spec.bands in ("bear", "both"):
        ranges = [_clip(b.start, b.end) for b in bears if b.end >= start and b.start <= end]
        _shade(ax, ranges, _BEAR_COLOR, "Bear market")
    if fig_spec.bands in ("recession", "both"):
        ranges = [_clip(a, b) for a, b in recessions if b >= start and a <= end]
        _shade(ax, ranges, _RECESSION_COLOR, "NBER recession")

    all_pct = True
    plotted_any = False
    for idx, s in enumerate(fig_spec.series):
        values, is_pct = _plot_series(s, fetched)
        all_pct = all_pct and is_pct
        win = values[(values.index >= start) & (values.index <= end)]
        if win.empty:
            continue
        plotted_any = True
        color = CYCLE[idx % len(CYCLE)]
        ax.plot(win.index, win.values, label=s.label, color=color, linewidth=2.0, zorder=3)
        # Annotate the latest point.
        last_d, last_v = win.index.max(), win.iloc[-1]
        ax.scatter([last_d], [last_v], color=color, s=45, zorder=5,
                   edgecolor="white", linewidth=1.3)
        ax.annotate(f"{last_v:.1f}%", xy=(last_d, last_v), xytext=(8, 0),
                    textcoords="offset points", fontsize=9, color=color,
                    weight="bold", va="center")

    if not plotted_any:
        raise ValueError(f"figure {fig_spec.id!r}: no series produced data in window")

    if all_pct:
        ax.axhline(0, color="#333333", linewidth=0.8, zorder=2)
        ax.yaxis.set_major_formatter(_PCT_FORMATTER)

    # Subtitle as a left-aligned axes title; main title as the figure suptitle
    # above it (avoids the two colliding at the top of the axes).
    if fig_spec.subtitle:
        ax.set_title(fig_spec.subtitle, fontsize=9.5, color="#444444", loc="left")
    fig.suptitle(fig_spec.title, fontsize=13, fontweight="bold", x=0.5, y=0.99)
    ax.legend(loc="best")
    ax.set_xlim(start, end)

    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    if source_note:
        fig.text(0.5, 0.005, source_note, ha="center", fontsize=7.5, color="#999999")
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path
