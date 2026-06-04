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
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import NullFormatter, ScalarFormatter  # noqa: E402

from ..charts.style import CYCLE, DEFAULT_DPI, DEFAULT_FIGSIZE  # noqa: E402

_BEAR_COLOR = "#9AA0A6"       # grey bands (bear markets, primary)
_RECESSION_COLOR = "#C0504D"  # muted red bands (NBER recessions, secondary)
_PCT_FORMATTER = plt.FuncFormatter(lambda v, _pos: f"{v:.0f}%")
_PP_FORMATTER = plt.FuncFormatter(lambda v, _pos: f"{v:+.0f}pp")


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


def yoy_accel(series: pd.Series) -> pd.Series:
    """Rate of change of the YoY growth rate: the 12-month change in the YoY series,
    in percentage points. Positive => growth is accelerating, negative => decelerating.
    Answers the book's 'is the rate of change increasing or decreasing?' The 12-month
    differencing smooths the otherwise-noisy month-to-month derivative."""
    s = series.dropna()
    periods = _infer_periods_per_year(s)
    return yoy_pct(s).diff(periods).dropna()


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
        # End is given as a month (e.g. "2020-03"); run it through the LAST day of that
        # month so the band + peak-to-trough decline capture the full end month (the 2020
        # COVID trough was late March, not the 1st).
        end = pd.Timestamp(str(b["end"])).to_period("M").end_time.normalize()
        out.append(
            BearMarket(
                start=pd.Timestamp(str(b["start"])),
                end=end,
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
    """Solid translucent band — used for bear markets (the primary overlay)."""
    first = True
    for a, b in ranges:
        ax.axvspan(a, b, color=color, alpha=0.18, lw=0,
                   label=(label if first else None), zorder=0)
        first = False


def _mark_recessions(ax, ranges, label) -> None:
    """NBER recessions, drawn distinctly from the grey bear bands: a faint red wash
    bracketed by dotted vertical lines at the official peak and trough. Reads clearly
    even where it overlaps a grey bear-market band."""
    first = True
    for a, b in ranges:
        ax.axvspan(a, b, color=_RECESSION_COLOR, alpha=0.06, lw=0,
                   label=(label if first else None), zorder=0)
        for x in (a, b):
            ax.axvline(x, color=_RECESSION_COLOR, linestyle=":", linewidth=1.1, zorder=1)
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
    unit: str | None = None  # override: 'pct' | 'pp' | 'index' | 'level'. None => inferred.
    axis: str = "left"       # 'left' | 'right' (secondary y-axis, e.g. an S&P 500 overlay)
    scale: str = "linear"    # 'linear' | 'log' (used for the right axis)


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
                unit=s.get("unit"),
                axis=s.get("axis", "left"),
                scale=s.get("scale", "linear"),
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


def _fmt_value(v: float, unit: str) -> str:
    if unit == "pp":
        return f"{v:+.1f}pp"
    if unit == "pct":
        return f"{v:.1f}%"
    if unit == "level":
        return f"{v:,.0f}"   # e.g. an S&P 500 level: "7,209"
    return f"{v:,.1f}"       # index (e.g. a sentiment index): "49.8"


def _apply_unit_formatter(axis, units: set[str]) -> None:
    """Format an axis as percent / percentage-points when its series are uniformly that
    unit; leave index/level/mixed axes with the default numeric formatter."""
    if units == {"pp"}:
        axis.yaxis.set_major_formatter(_PP_FORMATTER)
    elif units == {"pct"}:
        axis.yaxis.set_major_formatter(_PCT_FORMATTER)


def _plot_series(spec: SeriesSpec, fetched: dict[str, pd.Series]) -> tuple[pd.Series, str]:
    """Return (values_series, unit) for one SeriesSpec. unit is 'pct' (percent: yoy
    growth or rate levels), 'pp' (percentage points: yoy acceleration), or 'index'/'level'
    (plain numbers, e.g. a sentiment index). An explicit spec.unit overrides the default."""
    unit = spec.unit or ("pp" if spec.transform == "yoy_accel" else "pct")
    base = fetched.get(spec.fred)
    if base is None or base.dropna().empty:
        return pd.Series(dtype=float), unit
    if spec.divide_by:
        deflator = fetched.get(spec.divide_by)
        if deflator is None or deflator.dropna().empty:
            return pd.Series(dtype=float), unit
        base = real_deflate(base, deflator)
    if spec.transform == "yoy":
        return yoy_pct(base), unit
    if spec.transform == "yoy_accel":
        return yoy_accel(base), unit
    return base.dropna(), unit  # 'raw' = rate level (pct) or index/level


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

    # Timeline mode: no economic series — a bands-only reference chart that spans the
    # full available band history ("as far back as the data go").
    is_timeline = len(fig_spec.series) == 0
    if is_timeline:
        band_starts = [b.start for b in bears] + [a for a, _ in recessions]
        start = min(band_starts) if band_starts else end - pd.DateOffset(years=fig_spec.lookback_years)
    else:
        start = end - pd.DateOffset(years=fig_spec.lookback_years)

    fig, ax = plt.subplots(figsize=DEFAULT_FIGSIZE, dpi=DEFAULT_DPI)

    # Bands first (behind the lines), clipped to window.
    def _clip(a, b):
        return max(a, start), min(b, end)

    if fig_spec.bands in ("bear", "both"):
        ranges = [_clip(b.start, b.end) for b in bears if b.end >= start and b.start <= end]
        _shade(ax, ranges, _BEAR_COLOR, "S&P 500 bear market")
    if fig_spec.bands in ("recession", "both"):
        ranges = [_clip(a, b) for a, b in recessions if b >= start and a <= end]
        _mark_recessions(ax, ranges, "NBER recession")

    left_units: set[str] = set()
    right_units: set[str] = set()
    ax_right = None
    plotted_any = is_timeline  # timeline has no series but is still a valid (bands-only) chart
    for idx, s in enumerate(fig_spec.series):
        values, unit = _plot_series(s, fetched)
        win = values[(values.index >= start) & (values.index <= end)]
        if win.empty:
            continue
        plotted_any = True
        if s.axis == "right":
            if ax_right is None:
                ax_right = ax.twinx()
                ax_right.patch.set_visible(False)  # let ax's bands show through
            target, target_units = ax_right, right_units
        else:
            target, target_units = ax, left_units
        target_units.add(unit)
        color = CYCLE[idx % len(CYCLE)]
        target.plot(win.index, win.values, label=s.label, color=color, linewidth=2.0, zorder=3)
        # Annotate the latest point with its value AND its date.
        last_d, last_v = win.index.max(), win.iloc[-1]
        target.scatter([last_d], [last_v], color=color, s=45, zorder=5,
                       edgecolor="white", linewidth=1.3)
        target.annotate(f"{_fmt_value(last_v, unit)}  ({last_d:%b %Y})", xy=(last_d, last_v),
                        xytext=(8, 0), textcoords="offset points", fontsize=9, color=color,
                        weight="bold", va="center")

    if not plotted_any:
        raise ValueError(f"figure {fig_spec.id!r}: no series produced data in window")

    if is_timeline:
        # No data axis — hide the y-scale; bands span the full height.
        ax.set_ylim(0, 1)
        ax.set_yticks([])
    else:
        # Zero reference line on the left axis + unit-appropriate formatting.
        ax.axhline(0, color="#333333", linewidth=0.8, zorder=2)
        _apply_unit_formatter(ax, left_units)

    if ax_right is not None:
        right_log = any(s.axis == "right" and s.scale == "log" for s in fig_spec.series)
        if right_log:
            ax_right.set_yscale("log")
            ax_right.yaxis.set_major_formatter(ScalarFormatter())  # plain numbers, not 10^n
            ax_right.yaxis.set_minor_formatter(NullFormatter())
        else:
            _apply_unit_formatter(ax_right, right_units)
        rlabel = next((s.label for s in fig_spec.series if s.axis == "right"), "")
        ax_right.set_ylabel(rlabel, fontsize=9, color="#555555")

    # Major tick marks (labeled) + yearly minor ticks. 5-yr by default; 10-yr for the
    # very long timeline span so labels don't collide.
    span_years = (end - start).days / 365.25
    major_step = 10 if span_years > 80 else 5
    ax.xaxis.set_major_locator(mdates.YearLocator(major_step))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_minor_locator(mdates.YearLocator(5 if major_step == 10 else 1))
    ax.tick_params(axis="x", which="major", length=6, labelrotation=0)
    ax.tick_params(axis="x", which="minor", length=3)

    # Subtitle as a left-aligned axes title; main title as the figure suptitle
    # above it (avoids the two colliding at the top of the axes).
    if fig_spec.subtitle:
        ax.set_title(fig_spec.subtitle, fontsize=9.5, color="#444444", loc="left")
    fig.suptitle(fig_spec.title, fontsize=13, fontweight="bold", x=0.5, y=0.99)
    handles, labels = ax.get_legend_handles_labels()
    if ax_right is not None:
        h2, l2 = ax_right.get_legend_handles_labels()
        handles, labels = handles + h2, labels + l2
    if handles:  # skip empty legend (e.g. bands-off timeline)
        ax.legend(handles, labels, loc="best")
    ax.set_xlim(start, end)

    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    if source_note:
        fig.text(0.5, 0.005, source_note, ha="center", fontsize=7.5, color="#999999")
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path
