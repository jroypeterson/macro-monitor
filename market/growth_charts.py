"""Render the YoY growth views into readable/market/:

  • growth.html — the six-figure trailing-3-year quarterly page (PROJECT_IDEAS #31):
    real GDP · real consumer spending (PCE) · industrial production · real capex ·
    S&P 500 EPS · unemployment — each as a % change vs the prior year, by quarter.
  • growth_sp500_earnings.png — S&P 500 earnings YoY with a whole-economy
    corporate-profits companion (the *actual* half of #7; the FactSet forward
    overlay is a deferred enhancement).

Data + transforms live in `macro_growth.py`; this module only draws + assembles.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from ..charts.style import COLOR_PRIMARY, COLOR_SECONDARY, DEFAULT_DPI, DEFAULT_FIGSIZE  # noqa: E402
from ..collectors.fred import FREDClient  # noqa: E402
from . import factset_forward as FF  # noqa: E402
from . import macro_growth as G  # noqa: E402

_FWD = "#2E8B57"  # forward-consensus green

_OUT = Path(__file__).parent.parent / "readable" / "market"
_TRAILING_QUARTERS = 12  # JP #31: trailing 3 years, quarterly
_POS = COLOR_PRIMARY
_NEG = "#B23A48"


def _q_label(ts: pd.Timestamp) -> str:
    return f"{ts.year} Q{(ts.month - 1) // 3 + 1}"


def render_growth_bar(
    series: pd.Series, label: str, source: str, out: Path,
    quarters: int = _TRAILING_QUARTERS,
) -> Path:
    """One trailing-`quarters` YoY% bar chart (green up / red down, zero line)."""
    s = series.dropna().iloc[-quarters:]
    fig, ax = plt.subplots(figsize=DEFAULT_FIGSIZE, dpi=DEFAULT_DPI)
    x = list(range(len(s)))
    ax.bar(x, s.values, width=0.7, zorder=3,
           color=[_POS if v >= 0 else _NEG for v in s.values])
    ax.axhline(0, color="#444444", lw=1, zorder=2)
    for xi, v in zip(x, s.values):
        ax.annotate(f"{v:+.1f}", (xi, v), textcoords="offset points",
                    xytext=(0, 4 if v >= 0 else -12), ha="center",
                    fontsize=8, color="#333333", weight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([_q_label(d) for d in s.index], rotation=45, ha="right", fontsize=8)
    # Integer-percent tick locations so a small range (e.g. all bars 2–3.4%)
    # doesn't render duplicate rounded labels (+2%, +2%, +3%).
    ax.yaxis.set_major_locator(MaxNLocator(nbins=7, integer=True))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
    ax.margins(y=0.18)
    ax.set_title(f"% change vs prior year · trailing {quarters // 4} years (quarterly)",
                 fontsize=9.5, color="#444444", loc="left")
    fig.suptitle(label, fontsize=13, fontweight="bold", x=0.5, y=0.99)
    fig.text(0.5, 0.005, f"Source: {source}. YoY % change of the quarterly series.",
             ha="center", fontsize=7.5, color="#999999")
    fig.tight_layout(rect=[0, 0.05, 1, 0.96])
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def render_sp500_earnings(
    eps_yoy: pd.Series, profits_yoy: pd.Series, out: Path, years: int = 10,
    forward: dict | None = None,
) -> Path:
    """S&P 500 EPS YoY + whole-economy corporate-profits YoY (last `years`),
    plus the FactSet forward-consensus quarterly EPS-growth overlay if provided."""
    fig, ax = plt.subplots(figsize=DEFAULT_FIGSIZE, dpi=DEFAULT_DPI)
    for s, lab, color in (
        (eps_yoy, "S&P 500 EPS, reported TTM (YoY)", COLOR_PRIMARY),
        (profits_yoy, "US corporate profits, after tax (YoY)", COLOR_SECONDARY),
    ):
        s = s.dropna().iloc[-years * 4:]
        ax.plot(s.index, s.values, label=lab, color=color, lw=1.8, zorder=3)
        last = s.index[-1]
        ax.scatter([last], [s.iloc[-1]], color=color, s=40, zorder=5,
                   edgecolor="white", lw=1.2)
        ax.annotate(f"{s.iloc[-1]:+.1f}% ({_q_label(last)})",
                    (last, s.iloc[-1]), xytext=(8, 0), textcoords="offset points",
                    fontsize=9, color=color, weight="bold", va="center")

    # Forward consensus overlay (FactSet Earnings Insight). Plotted as a distinct
    # dashed series — it's bottom-up *operating*-EPS consensus by quarter, a
    # different basis than the reported-TTM actual, so it isn't joined to it.
    if forward:
        fwd = FF.forward_quarterly_series(forward)
        if not fwd.empty:
            ax.plot(fwd.index, fwd.values, color=_FWD, lw=1.8, ls="--", marker="o",
                    ms=5, zorder=4, label="S&P 500 EPS — FactSet consensus (fwd, operating)")
            for ts, v in fwd.items():
                ax.annotate(f"{v:+.0f}%", (ts, v), textcoords="offset points",
                            xytext=(0, 7), ha="center", fontsize=8, color=_FWD, weight="bold")
            cy = forward.get("cy", {})
            pe = forward.get("forward_pe")
            bits = []
            if cy.get("2026") is not None:
                bits.append(f"CY2026 {cy['2026']:+.1f}%")
            if cy.get("2027") is not None:
                bits.append(f"CY2027 {cy['2027']:+.1f}%")
            if pe:
                bits.append(f"fwd 12m P/E {pe:.1f}")
            cap = "FactSet Earnings Insight " + forward.get("report_date", "")
            if bits:
                cap += " — " + " · ".join(bits)
            ax.text(0.01, 0.02, cap, transform=ax.transAxes, fontsize=8,
                    color=_FWD, va="bottom", weight="bold")

    ax.axhline(0, color="#444444", lw=1, zorder=2)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
    ax.set_title("S&P 500 earnings growth — reported actual, corporate-profits companion, forward consensus",
                 fontsize=9.5, color="#444444", loc="left")
    fig.suptitle("S&P 500 Earnings — YoY Growth", fontsize=13, fontweight="bold", x=0.5, y=0.99)
    ax.legend(loc="best", fontsize=8.5)
    fig.text(0.5, 0.005,
             "Sources: S&P 500 reported TTM EPS via multpl.com; BEA corporate profits "
             "(FRED CP); forward consensus = FactSet Earnings Insight (operating EPS, quarterly).",
             ha="center", fontsize=7.5, color="#999999")
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def build_growth_page(
    out_dir: Path = _OUT, *, client: FREDClient | None = None, prefer_live: bool = True,
) -> dict[str, Path]:
    """Build the six #31 charts + the #7 S&P 500-earnings chart and the page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    client = client or FREDClient()
    series = G.build_growth_series(client=client, prefer_live=prefer_live)

    rendered: dict[str, dict] = {}
    for spec in G.SERIES:
        if spec.key not in series:
            continue
        path = render_growth_bar(series[spec.key], spec.label, spec.source,
                                 out_dir / f"growth_{spec.key}.png")
        rendered[spec.key] = dict(title=spec.label, source=spec.source, path=path)

    # #7 — S&P 500 earnings YoY + corporate-profits companion + FactSet forward.
    if "sp500_eps" in series:
        try:
            cp = G.yoy_pct(G.to_quarterly(client.get_observations(G.CORPORATE_PROFITS.fred_id)))
            forward = FF.load_forward(prefer_live=prefer_live)
            path = render_sp500_earnings(series["sp500_eps"], cp,
                                         out_dir / "growth_sp500_earnings.png",
                                         forward=forward)
            rendered["sp500_earnings"] = dict(
                title="S&P 500 Earnings — YoY Growth (+ corporate profits)",
                source="S&P 500 (multpl.com) + BEA", path=path)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] sp500_earnings chart failed: {type(exc).__name__}: {exc}")

    _render_growth_gallery(rendered, out_dir / "growth.html")
    return {k: v["path"] for k, v in rendered.items()}


def _render_growth_gallery(rendered: dict[str, dict], out_path: Path) -> Path:
    cards = []
    for r in rendered.values():
        cards.append(
            f'<section><h2>{r["title"]}</h2>'
            f'<p class="sub">Source: {r["source"]}</p>'
            f'<img src="{Path(r["path"]).name}" alt="{r["title"]}"/></section>')
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><title>Growth — YoY % change (quarterly)</title>
<style>
 body {{ font-family:-apple-system,Segoe UI,Roboto,sans-serif; max-width:980px; margin:2rem auto; padding:0 1rem; color:#222; }}
 h1 {{ font-size:1.5rem; }} .meta {{ color:#777; font-size:.85rem; margin-bottom:2rem; }}
 section {{ margin:2.5rem 0; }} h2 {{ font-size:1.1rem; margin-bottom:.2rem; }}
 .sub {{ color:#555; font-size:.9rem; margin:0 0 .6rem; }}
 img {{ width:100%; border:1px solid #e2e2e2; border-radius:6px; }}
 a {{ color:#1F4E79; }}
</style></head><body>
<h1>Growth — year-over-year % change (quarterly)</h1>
<p class="meta">Real GDP · real consumer spending (PCE) · industrial production · real capital
spending · S&amp;P 500 EPS · unemployment — each as a % change versus the prior year, by quarter
(trailing 3 years), plus S&amp;P 500 earnings growth vs whole-economy corporate profits.
Sources: BEA, Federal Reserve Board, BLS, S&amp;P 500 (multpl.com). ·
<a href="index.html">← market charts</a> · <a href="../index.html">↑ workspace hub</a> · {len(cards)} charts</p>
{''.join(cards)}
</body></html>"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    out = build_growth_page()
    for k, p in out.items():
        print(f"  {k}: {p}")
