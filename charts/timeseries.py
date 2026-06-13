"""Matplotlib chart factory. Renders ChartSpec objects to PNG files.

The factory takes pre-fetched FRED data (a dict series_id -> pd.Series) so
it doesn't need to know about the FREDClient — keeps it pure and testable.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from ..config import ChartSpec
from ..transforms import TRANSFORMS, apply_transform
from .style import (
    COLOR_REFERENCE,
    CYCLE,
    DEFAULT_DPI,
    DEFAULT_FIGSIZE,
)

# Friendly names for the data PROVIDER (the API we pull from) and the
# original AGENCY (the body that publishes the data), derived from a family's
# `source` and `agency.release_page`. Used to stamp a provenance footer on
# every chart so a reader always knows where the data came from AND that the
# chart is macro-monitor-rendered (not an agency graphic lifted as a PNG).
_SOURCE_NAMES = {"fred": "FRED", "yf": "Yahoo Finance", "yfinance": "Yahoo Finance"}
_AGENCY_DOMAINS = {
    "bls.gov": "BLS",
    "bea.gov": "BEA",
    "census.gov": "Census Bureau",
    "federalreserve.gov": "Federal Reserve",
    "conference-board.org": "Conference Board",
    "umich.edu": "U. Michigan",
    "adpemploymentreport.com": "ADP",
    "eia.gov": "EIA",
    "treasurydirect.gov": "Treasury",
    "cms.gov": "CMS",
}


def _agency_from_url(url: str | None) -> str | None:
    if not url:
        return None
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for dom, name in _AGENCY_DOMAINS.items():
        if host == dom or host.endswith("." + dom):
            return name
    return None


def provenance_label(source: str, agency_url: str | None = None) -> str:
    """One-line provenance footer: where the data comes from + that the chart
    is macro-monitor-rendered. e.g. 'Data: BLS via FRED · Chart by
    macro-monitor'. macro-monitor charts are always self-rendered from the
    source series — never an agency PNG — which is exactly what the 'Chart by
    macro-monitor' tag asserts."""
    src = _SOURCE_NAMES.get((source or "").lower(), (source or "source").upper())
    agency = _agency_from_url(agency_url)
    data = f"Data: {agency} via {src}" if agency and agency != src else f"Data: {src}"
    return f"{data} · Chart by macro-monitor"


def _stamp_provenance(fig, provenance: str | None) -> None:
    if provenance:
        fig.text(0.995, 0.004, provenance, ha="right", va="bottom",
                 fontsize=6.5, color="#9a9a9a")


def render_chart(
    spec: ChartSpec,
    fetched_series: dict[str, pd.Series],
    target_period: pd.Timestamp,
    output_path: Path,
    title: str | None = None,
    provenance: str | None = None,
) -> Path:
    """Render a single ChartSpec to a PNG file.

    `fetched_series` is a {series_id: pd.Series} dict already pulled from
    FRED. Each series in `spec.series` must be present.
    `target_period` is the latest point on the chart (the release period).
    `provenance`, when given, is stamped as a small footer (see
    provenance_label) so the data source + made-by-macro-monitor is on-chart.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=DEFAULT_FIGSIZE, dpi=DEFAULT_DPI)

    # Determine lookback start
    if spec.lookback_years is not None:
        start = target_period - pd.DateOffset(years=spec.lookback_years)
    elif spec.lookback_months is not None:
        start = target_period - pd.DateOffset(months=spec.lookback_months)
    else:
        raise ValueError("ChartSpec must declare lookback_years or lookback_months")

    if spec.type == "panes":
        # Discard the single-axes figure we created; panes builds its own.
        plt.close(fig)
        return _render_panes(spec, fetched_series, start, target_period, output_path, title, provenance)

    if spec.type == "line":
        _render_line_into(spec.series, spec.highlight_latest, fetched_series, start, target_period, ax,
                          label_extremes=spec.label_extremes)
    elif spec.type == "stacked_bar":
        _render_stacked_bar_into(spec.series, fetched_series, start, target_period, ax)
    else:
        raise ValueError(f"Unsupported chart type: {spec.type}")

    # Reference lines (e.g. 2% inflation target)
    for ref in spec.reference_lines:
        linestyle = {"solid": "-", "dashed": "--", "dotted": ":"}.get(ref.style, "--")
        ax.axhline(
            y=ref.value,
            color=COLOR_REFERENCE,
            linestyle=linestyle,
            linewidth=1,
            label=ref.label,
            zorder=1,
        )

    if title:
        ax.set_title(title)

    # Y-axis as percent (we mostly chart % transforms; harmless if raw values)
    # Only format as % if all displayed series are percent-style transforms
    pct_transforms = {"yoy_pct", "mom_pct", "annualized_mom", "qoq_pct_saar"}
    if all(s.transform in pct_transforms for s in spec.series):
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _pos: f"{v:.1f}%")
        )

    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    _stamp_provenance(fig, provenance)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return output_path


def _transform_series_to_window(
    series: pd.Series,
    transform: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    """Apply a transform pointwise across the [start, end] window of the
    series. Returns a new Series of transformed values indexed by date.
    """
    fn = TRANSFORMS[transform]
    rows: list[tuple[pd.Timestamp, float]] = []
    for d in series.index:
        if start <= d <= end:
            v = fn(series, d)
            if v is not None:
                rows.append((d, v))
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.DatetimeIndex([r[0] for r in rows])
    return pd.Series([r[1] for r in rows], index=idx, dtype=float)


def _fmt_point_value(val: float, transform: str) -> str:
    """Significant-figure-aware label for a single plotted point. Percents get
    one decimal; raw levels keep a decimal at index scale (so e.g. a UMich
    reading shows 52.7, not a rounded 53) and drop decimals once large."""
    is_pct = transform in {
        "yoy_pct", "mom_pct", "annualized_mom", "qoq_pct_saar",
        "yoy_pct_weekly", "mom_pct_weekly",
    }
    if is_pct:
        return f"{val:.1f}%"
    if abs(val) < 100:
        return f"{val:,.1f}"
    return f"{val:,.0f}"


def _annotate_point(ax, date, val, color, transform, dy_points: float, va: str) -> None:
    ax.scatter([date], [val], color=color, s=60, zorder=5,
               edgecolor="white", linewidth=1.5)
    ax.annotate(
        _fmt_point_value(val, transform),
        xy=(date, val),
        xytext=(8, dy_points),
        textcoords="offset points",
        fontsize=9, color=color, weight="bold", va=va,
    )


def _render_line_into(
    series_refs,
    highlight_latest: bool,
    fetched_series: dict[str, pd.Series],
    start: pd.Timestamp,
    end: pd.Timestamp,
    ax,
    label_extremes: bool = False,
) -> None:
    for idx, s in enumerate(series_refs):
        if s.id not in fetched_series:
            raise KeyError(f"Chart series {s.id!r} not in fetched data")
        transformed = _transform_series_to_window(fetched_series[s.id], s.transform, start, end)
        if transformed.empty:
            continue
        color = CYCLE[idx % len(CYCLE)]
        ax.plot(transformed.index, transformed.values, label=s.label, color=color, linewidth=2.0)

        last_date = transformed.index.max()

        # Peak + trough of the window — the "significant figures" on the curve.
        if label_extremes:
            hi_date = transformed.idxmax()
            lo_date = transformed.idxmin()
            if hi_date != last_date:
                _annotate_point(ax, hi_date, transformed.loc[hi_date], color, s.transform, 6, "bottom")
            if lo_date != last_date and lo_date != hi_date:
                _annotate_point(ax, lo_date, transformed.loc[lo_date], color, s.transform, -6, "top")

        if highlight_latest:
            _annotate_point(ax, last_date, transformed.loc[last_date], color, s.transform, 0, "center")


def _render_stacked_bar_into(
    series_refs,
    fetched_series: dict[str, pd.Series],
    start: pd.Timestamp,
    end: pd.Timestamp,
    ax,
) -> None:
    # Build a DataFrame of transformed monthly values across the window
    transformed_cols: dict[str, pd.Series] = {}
    for s in series_refs:
        if s.id not in fetched_series:
            raise KeyError(f"Chart series {s.id!r} not in fetched data")
        transformed_cols[s.label] = _transform_series_to_window(
            fetched_series[s.id], s.transform, start, end
        )

    if not transformed_cols:
        return

    df = pd.DataFrame(transformed_cols)
    df = df.dropna(how="all")
    if df.empty:
        return

    # Stack
    bottoms_pos = pd.Series(0.0, index=df.index)
    bottoms_neg = pd.Series(0.0, index=df.index)
    width = 22  # days; one bar per month, roughly

    for i, (col, color) in enumerate(zip(df.columns, CYCLE)):
        vals = df[col].fillna(0.0)
        pos_mask = vals >= 0
        neg_mask = vals < 0
        ax.bar(
            df.index[pos_mask],
            vals[pos_mask].values,
            bottom=bottoms_pos[pos_mask].values,
            width=width,
            color=color,
            label=col,
            edgecolor="white",
            linewidth=0.5,
        )
        ax.bar(
            df.index[neg_mask],
            vals[neg_mask].values,
            bottom=bottoms_neg[neg_mask].values,
            width=width,
            color=color,
            edgecolor="white",
            linewidth=0.5,
        )
        bottoms_pos = bottoms_pos.add(vals.where(pos_mask, 0.0), fill_value=0.0)
        bottoms_neg = bottoms_neg.add(vals.where(neg_mask, 0.0), fill_value=0.0)


def _render_panes(
    spec: ChartSpec,
    fetched_series: dict[str, pd.Series],
    start: pd.Timestamp,
    end: pd.Timestamp,
    output_path: Path,
    title: str | None,
    provenance: str | None = None,
) -> Path:
    """Multi-pane chart — one PNG, N matplotlib subplots stacked vertically
    (or horizontally). Used for HC employment (absolute + 12mo change in
    one pane, HC vs total nonfarm normalized in the other)."""
    n = len(spec.panes)
    if spec.layout == "horizontal":
        figsize = (DEFAULT_FIGSIZE[0] * n / 1.5, DEFAULT_FIGSIZE[1])
        fig, axes = plt.subplots(1, n, figsize=figsize, dpi=DEFAULT_DPI)
    else:
        figsize = (DEFAULT_FIGSIZE[0], DEFAULT_FIGSIZE[1] * n / 1.5)
        fig, axes = plt.subplots(n, 1, figsize=figsize, dpi=DEFAULT_DPI)

    if n == 1:
        axes = [axes]  # ensure iterable

    pct_transforms = {"yoy_pct", "mom_pct", "annualized_mom", "qoq_pct_saar"}

    for pane, ax in zip(spec.panes, axes):
        if pane.type == "line":
            _render_line_into(pane.series, pane.highlight_latest, fetched_series, start, end, ax)
        elif pane.type == "stacked_bar":
            _render_stacked_bar_into(pane.series, fetched_series, start, end, ax)
        else:
            raise ValueError(f"Unsupported pane type: {pane.type}")

        for ref in pane.reference_lines:
            linestyle = {"solid": "-", "dashed": "--", "dotted": ":"}.get(ref.style, "--")
            ax.axhline(
                y=ref.value,
                color="#666666",
                linestyle=linestyle,
                linewidth=1,
                label=ref.label,
                zorder=1,
            )

        ax.set_title(pane.title, fontsize=11, weight="bold")

        if all(s.transform in pct_transforms for s in pane.series):
            ax.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda v, _pos: f"{v:.1f}%")
            )

        ax.legend(loc="best", fontsize=9)

    if title:
        fig.suptitle(title, fontsize=13, weight="bold")

    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0, 1, 0.97] if title else None)
    _stamp_provenance(fig, provenance)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return output_path


def render_family_charts(
    family_charts,  # ChartsBundle (Pydantic model)
    fetched_series: dict[str, pd.Series],
    target_period: pd.Timestamp,
    period_key: str,
    output_dir: Path,
    family_display_name: str,
    period_label: str,
    provenance: str | None = None,
) -> dict[str, Path]:
    """Render every chart declared by a family. Returns {chart_name: path}
    keyed by `'main'` for the main chart and chart `.name` for each thread chart.

    `provenance` (see provenance_label) is stamped on every chart so the data
    source + made-by-macro-monitor is visible on the image itself.
    """
    rendered: dict[str, Path] = {}

    # Main chart
    main_path = output_dir / family_charts.main.filename.format(period=period_key)
    rendered["main"] = render_chart(
        spec=family_charts.main,
        fetched_series=fetched_series,
        target_period=target_period,
        output_path=main_path,
        title=f"{family_display_name} — {period_label}",
        provenance=provenance,
    )

    # Thread charts
    for chart in family_charts.thread:
        path = output_dir / chart.filename.format(period=period_key)
        name = chart.name or chart.filename
        rendered[name] = render_chart(
            spec=chart,
            fetched_series=fetched_series,
            target_period=target_period,
            output_path=path,
            title=f"{family_display_name} — {chart.name or ''} — {period_label}".strip(" —"),
            provenance=provenance,
        )

    return rendered
