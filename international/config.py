"""International series config — loads international/series.yaml.

Declarative like the US `release_families.yaml`: each entry names a region,
an indicator, the source to pull from, and the source-specific locator in
`params`. Adding a series is a YAML edit, not a code change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# Display order for regions and indicators (drives digest/dashboard layout).
REGION_ORDER = ["eurozone", "uk", "china", "japan"]
REGION_LABELS = {
    "eurozone": "🇪🇺 Eurozone",
    "uk": "🇬🇧 United Kingdom",
    "china": "🇨🇳 China",
    "japan": "🇯🇵 Japan",
}
INDICATOR_ORDER = [
    "cpi_yoy", "core_cpi_yoy", "gdp_yoy", "unemployment", "policy_rate",
    "yield_2y", "yield_10y",
]
INDICATOR_LABELS = {
    "cpi_yoy": "CPI (YoY)",
    "core_cpi_yoy": "Core CPI (YoY)",
    "gdp_yoy": "GDP (YoY)",
    "unemployment": "Unemployment",
    "policy_rate": "Policy rate",
    "yield_2y": "2Y gov't yield",
    "yield_10y": "10Y gov't yield",
}
# Bond-yield indicators render as a combined "Gov't yield" line with YTD
# change (in bps), handled separately from the single-value indicators above.
YIELD_INDICATORS = ("yield_2y", "yield_10y")

VALID_SOURCES = {"eurostat", "ecb", "oecd", "ons", "boe", "estat", "boj", "fred"}
VALID_FREQ = {"monthly", "quarterly", "annual", "daily"}


class IntlSeriesSpec(BaseModel):
    """One configured international series."""

    id: str
    region: str
    indicator: str
    label: str
    source: str
    params: dict[str, Any] = Field(default_factory=dict)
    unit: str = "%"
    freq: str = "monthly"
    decimals: int = 1
    # If true, render with sign flipped (rare; reserved for balance-type series).
    invert: bool = False

    def validate_semantics(self) -> list[str]:
        errs: list[str] = []
        if self.region not in REGION_ORDER:
            errs.append(f"{self.id}: unknown region {self.region!r}")
        if self.source not in VALID_SOURCES:
            errs.append(f"{self.id}: unknown source {self.source!r}")
        if self.freq not in VALID_FREQ:
            errs.append(f"{self.id}: unknown freq {self.freq!r}")
        if not self.params:
            errs.append(f"{self.id}: empty params (no source locator)")
        return errs


def default_series_path() -> Path:
    return Path(__file__).parent / "series.yaml"


def load_series(path: str | Path | None = None) -> list[IntlSeriesSpec]:
    p = Path(path) if path else default_series_path()
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return [IntlSeriesSpec.model_validate(s) for s in (raw.get("series") or [])]


def validate_series_or_raise(specs: list[IntlSeriesSpec]) -> None:
    errs: list[str] = []
    seen: set[str] = set()
    for s in specs:
        if s.id in seen:
            errs.append(f"duplicate series id {s.id!r}")
        seen.add(s.id)
        errs.extend(s.validate_semantics())
    if errs:
        raise ValueError("International series config invalid:\n  - " + "\n  - ".join(errs))
