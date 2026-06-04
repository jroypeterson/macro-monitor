"""Render the Damodaran data inventory to readable/DAMODARAN_DATA_INVENTORY.md, grouped
by category, annotated with the latest download status from the manifest."""
from __future__ import annotations

import json
from pathlib import Path

from .datasets import all_datasets

_OUT = Path(__file__).parent.parent / "readable" / "DAMODARAN_DATA_INVENTORY.md"
_MANIFEST = Path(__file__).parent / "data" / "manifest_latest.json"

_CATEGORY_ORDER = [
    ("returns", "Historical returns (risk-free + equity)"),
    ("erp", "Equity risk premium"),
    ("country_risk", "Country risk premiums"),
    ("country", "Country statistics"),
    ("macro", "Macro / risk-free rates"),
    ("multiples", "Valuation multiples (PE · EV/EBITDA · P/BV · P/S)"),
    ("discount_rate", "Discount-rate inputs (betas · WACC · tax · ratings)"),
    ("fundamentals", "Fundamentals & profitability"),
    ("growth", "Growth rates"),
    ("cashflows", "Cash flows"),
    ("payout", "Dividends & payout"),
    ("capital_structure", "Capital structure"),
    ("governance", "Governance / holdings"),
    ("other", "Other"),
]


def _esc(s) -> str:
    return str(s).replace("|", "\\|")


def render(out_path: Path = _OUT) -> Path:
    recs = all_datasets()
    by_cat: dict[str, list] = {}
    for r in recs:
        by_cat.setdefault(r["category"], []).append(r)

    ok_ids: set[str] = set()
    manifest = None
    if _MANIFEST.exists():
        manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        ok_ids = {o["id"] for o in manifest.get("ok", [])}

    lines = [
        "# Aswath Damodaran — Data Inventory",
        "",
        f"_Mirror of Prof. Damodaran's NYU Stern datasets ({len(recs)} files). "
        "Source: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html — refreshed "
        "the first two weeks of each January. Raw files archived under `damodaran/data/raw/<date>/` "
        "+ `damodaran/data/latest/`._",
        "",
    ]
    if manifest:
        lines.append(
            f"_Last download: **{manifest.get('date', '?')}** — "
            f"{len(manifest.get('ok', []))} ok · {len(manifest.get('missing', []))} not-found · "
            f"{len(manifest.get('error', []))} error._")
        lines.append("")

    # Group families so we show one row per family with its region coverage.
    for cat, label in _CATEGORY_ORDER:
        items = by_cat.get(cat)
        if not items:
            continue
        lines.append(f"## {label} ({len(items)} files)")
        lines.append("")
        lines.append("| Dataset | Regions | Relevance | Time series | Downloaded |")
        lines.append("|---|---|---|:--:|:--:|")
        fams: dict[str, list] = {}
        for r in items:
            fams.setdefault(r["family"], []).append(r)
        for fam, frecs in sorted(fams.items()):
            name = _esc(frecs[0]["name"])
            regions = [r["region"] for r in frecs if r["region"] != "—"]
            region_str = f"{len(regions)} regions" if regions else "single file"
            rel = frecs[0]["relevance"]
            ts = "✓" if frecs[0]["timeseries"] else ""
            got = sum(1 for r in frecs if r["id"] in ok_ids)
            dl = f"{got}/{len(frecs)}" if ok_ids else "—"
            lines.append(f"| {name} | {region_str} | {rel} | {ts} | {dl} |")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    print("wrote", render())
