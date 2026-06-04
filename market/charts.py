"""Parse the mirrored market data (Shiller / Damodaran / Ken French) and render
top-down valuation + factor charts. Reuses macro_monitor's matplotlib style.

Parsers are defensive about the quirky source layouts (Shiller's YYYY.MM dates, the
Damodaran header offset, the Ken French monthly-then-annual CSV blocks).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from ..charts.style import COLOR_PRIMARY, COLOR_SECONDARY, CYCLE, DEFAULT_DPI, DEFAULT_FIGSIZE  # noqa: E402

_MKT = Path(__file__).parent / "data" / "latest"
_DAM = Path(__file__).parent.parent / "damodaran" / "data" / "latest"


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #
def parse_shiller(path: Path | None = None) -> pd.DataFrame:
    """Shiller ie_data 'Data' sheet → monthly DataFrame [cape, long_rate]."""
    path = path or _MKT / "ie_data.xls"
    df = pd.read_excel(path, sheet_name="Data", header=None)
    rows = []
    for i in range(8, len(df)):
        d = df.iat[i, 0]
        if pd.isna(d):
            break
        try:
            f = float(d)
            year = int(f)
            month = round((f - year) * 100) or 1
            if not (1 <= month <= 12):
                continue
            ts = pd.Timestamp(year=year, month=month, day=1)
        except (ValueError, TypeError):
            continue
        cape = pd.to_numeric(df.iat[i, 12], errors="coerce")
        lr = pd.to_numeric(df.iat[i, 6], errors="coerce")
        rows.append((ts, cape, lr))
    out = pd.DataFrame(rows, columns=["date", "cape", "long_rate"]).set_index("date")
    return out


def parse_damodaran_erp(path: Path | None = None) -> pd.DataFrame:
    """Damodaran histimpl → annual DataFrame [implied_erp, riskfree] (decimals)."""
    path = path or _DAM / "histimpl.xls"
    df = pd.read_excel(path, sheet_name="Historical Impl Premiums", header=None)
    rows = []
    for i in range(7, len(df)):
        y = df.iat[i, 0]
        try:
            year = int(y)
        except (ValueError, TypeError):
            continue
        if not (1900 <= year <= 2100):
            continue
        erp = pd.to_numeric(df.iat[i, 15], errors="coerce")   # Implied ERP (FCFE)
        if pd.isna(erp):
            erp = pd.to_numeric(df.iat[i, 13], errors="coerce")  # fallback: Implied Premium (DDM)
        rf = pd.to_numeric(df.iat[i, 10], errors="coerce")    # T.Bond rate
        rows.append((pd.Timestamp(year, 1, 1), erp, rf))
    return pd.DataFrame(rows, columns=["date", "implied_erp", "riskfree"]).set_index("date")


def parse_ff_factors(zip_path: Path, csv_name: str | None = None) -> pd.DataFrame:
    """Ken French factor zip → monthly DataFrame of factor returns (decimals)."""
    z = zipfile.ZipFile(zip_path)
    name = csv_name or z.namelist()[0]
    lines = z.read(name).decode("latin1").splitlines()
    cols, rows, started = None, [], False
    for ln in lines:
        parts = [p.strip() for p in ln.split(",")]
        if not started:
            # Header is the first line that starts with a comma then column labels
            # (e.g. ",Mkt-RF,SMB,HML,RF" or ",Mom") — prose lines don't start with ",".
            if parts[0] == "" and len(parts) >= 2 and parts[1]:
                cols = [c for c in parts[1:] if c]
                started = True
            continue
        if not parts[0].isdigit() or len(parts[0]) != 6:
            break  # blank line / annual (YYYY) section ends the monthly block
        ym = parts[0]
        ts = pd.Timestamp(int(ym[:4]), int(ym[4:6]), 1)
        vals = [pd.to_numeric(x, errors="coerce") / 100 for x in parts[1:1 + len(cols)]]
        rows.append((ts, *vals))
    return pd.DataFrame(rows, columns=["date", *cols]).set_index("date")


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _decade_ticks(ax, start, end):
    span = (end - start).days / 365.25
    step = 20 if span > 120 else (10 if span > 60 else 5)
    ax.xaxis.set_major_locator(mdates.YearLocator(step))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_minor_locator(mdates.YearLocator(step // 2 or 1))


def render_line(series_map: dict[str, pd.Series], title: str, subtitle: str, out: Path,
                source_note: str = "", logy: bool = False, mean_band: pd.Series | None = None,
                pct_axis: bool = False, latest_fmt: str = "{:.1f}") -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=DEFAULT_FIGSIZE, dpi=DEFAULT_DPI)
    start = min(s.dropna().index.min() for s in series_map.values())
    end = max(s.dropna().index.max() for s in series_map.values())

    # Mean / ±1σ reference bands (e.g. CAPE vs its own history).
    if mean_band is not None:
        m, sd = float(mean_band.mean()), float(mean_band.std())
        ax.axhline(m, color="#888888", lw=1, ls="--", zorder=1, label=f"mean {m:.1f}")
        ax.axhspan(m - sd, m + sd, color="#888888", alpha=0.10, zorder=0, label="±1σ")

    for i, (label, s) in enumerate(series_map.items()):
        s = s.dropna()
        color = CYCLE[i % len(CYCLE)]
        ax.plot(s.index, s.values, label=label, color=color, lw=1.8, zorder=3)
        last_d, last_v = s.index.max(), s.iloc[-1]
        ax.scatter([last_d], [last_v], color=color, s=40, zorder=5, edgecolor="white", lw=1.2)
        ax.annotate(f"{latest_fmt.format(last_v)} ({last_d:%Y})", xy=(last_d, last_v),
                    xytext=(8, 0), textcoords="offset points", fontsize=9, color=color,
                    weight="bold", va="center")

    if logy:
        ax.set_yscale("log")
    if pct_axis:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v*100:.0f}%"))
    ax.set_xlim(start, end)
    _decade_ticks(ax, start, end)
    if subtitle:
        ax.set_title(subtitle, fontsize=9.5, color="#444444", loc="left")
    fig.suptitle(title, fontsize=13, fontweight="bold", x=0.5, y=0.99)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    if source_note:
        fig.text(0.5, 0.005, source_note, ha="center", fontsize=7.5, color="#999999")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def render_dual(left: pd.Series, left_label: str, right: pd.Series, right_label: str,
                title: str, subtitle: str, out: Path, source_note: str = "",
                left_pct: bool = False, right_pct: bool = False) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=DEFAULT_FIGSIZE, dpi=DEFAULT_DPI)
    ax2 = ax.twinx()
    ax2.patch.set_visible(False)
    ls, rs = left.dropna(), right.dropna()
    ax.plot(ls.index, ls.values, color=COLOR_PRIMARY, lw=1.8, label=left_label, zorder=3)
    ax2.plot(rs.index, rs.values, color=COLOR_SECONDARY, lw=1.8, label=right_label, zorder=3)
    ax.set_ylabel(left_label, color=COLOR_PRIMARY, fontsize=10)
    ax2.set_ylabel(right_label, color=COLOR_SECONDARY, fontsize=10)
    if left_pct:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v*100:.0f}%"))
    if right_pct:
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v*100:.0f}%"))
    start = min(ls.index.min(), rs.index.min())
    end = max(ls.index.max(), rs.index.max())
    ax.set_xlim(start, end)
    _decade_ticks(ax, start, end)
    if subtitle:
        ax.set_title(subtitle, fontsize=9.5, color="#444444", loc="left")
    fig.suptitle(title, fontsize=13, fontweight="bold", x=0.5, y=0.99)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="best", fontsize=9)
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    if source_note:
        fig.text(0.5, 0.005, source_note, ha="center", fontsize=7.5, color="#999999")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out
