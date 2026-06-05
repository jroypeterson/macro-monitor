"""Drug-price-inflation benchmarks — consumer vs producer, overlaid.

A consolidated read on drug price inflation from the clean keyless (FRED)
series:
  - CPI Medical care commodities (consumer prices; mostly Rx + supplies)
  - PPI Pharmaceutical preparation mfg (producer Rx prices)
  - PPI Pharmaceutical & medicine mfg (broader producer)

Caveats (no fabrication): FRED does not carry the CPI *prescription-drugs*
sub-item (SEMF01) — only the broader medical-care-commodities aggregate —
so that's used as the consumer proxy. And these are LIST/transaction-price
indices; **net** drug prices (after rebates) diverge sharply and need a paid
source (SSR Health). AARP Rx Price Watch / 46brooklyn are non-FRED follow-ups.

Run: ``python -m macro_monitor.cli drug-prices``.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .collectors.fred import FREDClient
from .market import charts as C

_OUT = Path(__file__).parent / "readable" / "drug_prices"
_SRC = "Source: FRED/BLS — CPI Medical care commodities (consumer) + PPI Pharmaceutical preparation and Pharmaceutical & medicine manufacturing (producer). List/transaction prices, not net-of-rebate."

CPI_MED_COMMODITIES = "CUUR0000SAM1"      # consumer: medical care commodities (Rx + supplies)
PPI_PHARMA_PREP = "PCU325412325412"        # producer: pharmaceutical preparation mfg
PPI_PHARMA_MED = "PCU32543254"             # producer: pharmaceutical & medicine mfg


def _yoy(s: pd.Series) -> pd.Series:
    return (s.dropna().pct_change(12) * 100).dropna()


def build(out_dir: Path = _OUT) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    fred = FREDClient()
    cpi = _yoy(fred.get_observations(CPI_MED_COMMODITIES))
    ppi_prep = _yoy(fred.get_observations(PPI_PHARMA_PREP))
    ppi_med = _yoy(fred.get_observations(PPI_PHARMA_MED))

    rendered: dict[str, dict] = {}
    rendered["drug_inflation"] = dict(
        title="Drug Price Inflation — Consumer vs Producer (YoY)",
        sub="Consumer drug+supply prices (CPI) vs producer pharma prices (PPI), year-over-year. "
            f"Latest: CPI commodities {cpi.iloc[-1]:+.1f}%, PPI pharma prep {ppi_prep.iloc[-1]:+.1f}%.",
        path=C.render_line(
            {"CPI Medical care commodities": cpi,
             "PPI Pharmaceutical preparation mfg": ppi_prep,
             "PPI Pharmaceutical & medicine mfg": ppi_med},
            "Drug Price Inflation — Consumer vs Producer (YoY)",
            "List/transaction-price indices, YoY. Net (post-rebate) prices differ — needs a paid source.",
            out_dir / "drug_inflation.png", _SRC, latest_fmt="{:+.1f}%"),
    )

    _render_gallery(rendered, out_dir / "index.html")
    return {k: v["path"] for k, v in rendered.items()}


def _render_gallery(rendered: dict[str, dict], out_path: Path) -> Path:
    cards = []
    for r in rendered.values():
        cards.append(
            f'<section><h2>{r["title"]}</h2><p class="sub">{r["sub"]}</p>'
            f'<img src="{Path(r["path"]).name}" alt="{r["title"]}"/></section>')
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><title>Drug Price Inflation Benchmarks</title>
<style>
 body {{ font-family:-apple-system,Segoe UI,Roboto,sans-serif; max-width:980px; margin:2rem auto; padding:0 1rem; color:#222; }}
 h1 {{ font-size:1.5rem; }} .meta {{ color:#777; font-size:.85rem; margin-bottom:2rem; }}
 section {{ margin:2.5rem 0; }} h2 {{ font-size:1.1rem; margin-bottom:.2rem; }}
 .sub {{ color:#555; font-size:.9rem; margin:0 0 .6rem; }}
 img {{ width:100%; border:1px solid #e2e2e2; border-radius:6px; }}
 a {{ color:#1F4E79; }}
</style></head><body>
<h1>Drug Price Inflation Benchmarks</h1>
<p class="meta">Consumer vs producer drug-price inflation from FRED/BLS. CPI prescription-drug
sub-item isn't on FRED (medical-care-commodities used as the consumer proxy); these are
list/transaction prices — net (post-rebate) prices need a paid source. AARP Rx Price Watch /
46brooklyn are non-FRED follow-ups. · <a href="../index.html">↑ workspace hub</a> · {len(cards)} chart</p>
{''.join(cards)}
</body></html>"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    for k, p in build().items():
        print(f"  {k}: {p}")
