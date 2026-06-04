"""Render the macro data inventory (datasets.yaml) into a human-readable markdown table at
readable/MACRO_DATA_INVENTORY.md, grouped by status. Source of truth stays the YAML.

Run: ``python -m macro_monitor.data_inventory.render``
"""
from __future__ import annotations

from pathlib import Path

import yaml

_DIR = Path(__file__).parent
_YAML = _DIR / "datasets.yaml"
_OUT = _DIR.parent / "readable" / "MACRO_DATA_INVENTORY.md"

_STATUS_ORDER = ["in_charts", "shipped", "staged", "candidate", "rejected", "not_evaluated"]
_STATUS_LABEL = {
    "in_charts": "✅ In charts", "shipped": "✅ Shipped", "staged": "⏸ Staged (FRED path confirmed)",
    "candidate": "🔎 Candidate", "rejected": "✖ Rejected", "not_evaluated": "· Not evaluated",
}


def _esc(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def render(yaml_path: Path = _YAML, out_path: Path = _OUT) -> Path:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    rows = data.get("datasets", [])
    by_status: dict[str, list] = {}
    for r in rows:
        by_status.setdefault(r.get("status", "not_evaluated"), []).append(r)

    fred_ready = sum(
        1 for r in rows
        if (r.get("access", {}) or {}).get("method") == "fred"
    )
    lines = [
        "# Macro Data Inventory",
        "",
        f"_Generated from `data_inventory/datasets.yaml` — {len(rows)} datasets "
        f"({fred_ready} reachable via a single FRED id). Schema: `data_inventory/SCHEMA.md`. "
        "Edit the YAML, not this file._",
        "",
        "_Seeded from the \"Ahead of the Curve\" (Joseph Ellis) chart-recreation work. "
        "Ellis's lens is year-over-year rate of change (`yoy_roc`); real consumer spending "
        "(real PCE) is the leading indicator the rest of the cycle follows._",
        "",
    ]
    for status in _STATUS_ORDER:
        items = by_status.get(status)
        if not items:
            continue
        lines.append(f"## {_STATUS_LABEL.get(status, status)} ({len(items)})")
        lines.append("")
        lines.append(
            "| Dataset | Publisher | Category | Access (method · detail · effort) | "
            "Cadence · lag | Transform | Ellis fig(s) | Relevance |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in sorted(items, key=lambda x: x.get("id", "")):
            acc = r.get("access", {}) or {}
            access = f"{acc.get('method', '?')} · `{acc.get('detail', '?')}` · {acc.get('effort', '?')}"
            cats = ", ".join(_as_list(r.get("category")))
            cad = f"{r.get('cadence', '?')} · {r.get('lag', '?')}"
            name = _esc(r.get("name", r.get("id")))
            lines.append(
                f"| **{name}** | {_esc(r.get('publisher', ''))} | {_esc(cats)} | "
                f"{_esc(access)} | {_esc(cad)} | {_esc(r.get('transform', ''))} | "
                f"{_esc(r.get('ellis_figures', ''))} | {_esc(r.get('relevance', ''))} |")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    print("wrote", render())
