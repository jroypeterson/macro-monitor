"""compute_release staleness guard (C2) + trend-unit fidelity (H4).

C2 — partial FRED ingest: when a leading headline series has the new period
but a laggard still ends a period back, compute_release used to jump
target_period forward, render the laggard as a blank "—", and (because the
stale guard was dead code) post an apparently-fresh release with a missing
headline. It must now flag `is_stale` so the poller skips + retries.

H4 — a `mean` trend on payrolls/ADP averages the family's anchor transform
(`mom_chg`, a jobs count), NOT a hardcoded `mom_pct`, and renders in the
anchor's display unit ("+150K"), never a bogus "%".
"""

from __future__ import annotations

import pandas as pd

from macro_monitor.config import FamilyConfig
from macro_monitor.publishers.slack import _format_trend_lines
from macro_monitor.release_runner import compute_release


class _MockFRED:
    """Minimal stand-in for FREDClient — serves canned monthly series."""

    def __init__(self, series: dict[str, pd.Series]):
        self._series = series

    def get_observations(
        self, series_id: str, observation_start: str | None = None,
        observation_end: str | None = None,
    ) -> pd.Series:
        return self._series[series_id].copy()


def _monthly(values: list[float], start: str = "2025-06-01") -> pd.Series:
    idx = pd.date_range(start=start, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


def _family(headline: list[dict], context: dict | None = None) -> FamilyConfig:
    payload = {
        "tier": "A",
        "family_type": "numeric",
        "cadence": "monthly",
        "release_calendar_id": 1,
        "release_time_et": "08:30",
        "source": "fred",
        "display_name": "Test Family",
        "period_label_format": "{month_name} {year}",
        "headline": headline,
        "dedupe": {"headline_hash": [h["id"] for h in headline], "component_hash": []},
        "agency": {"release_page": "http://test", "archive_path": "x"},
    }
    if context is not None:
        payload["context"] = context
    return FamilyConfig.model_validate(payload)


# --- C2: partial-ingest staleness ------------------------------------------

def test_partial_ingest_flags_stale():
    # LEAD has the new month (2026-01), LAG still ends 2025-12 → target_period
    # jumps to 2026-01 and LAG would render blank. Must be flagged stale.
    fam = _family([
        {"id": "LEAD", "label": "lead", "primary_transform": "mom_chg"},
        {"id": "LAG", "label": "lag", "primary_transform": "mom_chg"},
    ])
    client = _MockFRED({
        "LEAD": _monthly([100, 110, 120, 130, 140, 150, 160, 170]),   # → 2026-01
        "LAG": _monthly([200, 210, 220, 230, 240, 250, 260]),         # → 2025-12
    })
    result = compute_release(fam, client)
    assert result.is_stale is True


def test_full_ingest_is_not_stale():
    # Both headline series carry the same latest period → healthy, not stale.
    fam = _family([
        {"id": "LEAD", "label": "lead", "primary_transform": "mom_chg"},
        {"id": "LAG", "label": "lag", "primary_transform": "mom_chg"},
    ])
    client = _MockFRED({
        "LEAD": _monthly([100, 110, 120, 130, 140, 150, 160, 170]),   # → 2026-01
        "LAG": _monthly([200, 210, 220, 230, 240, 250, 260, 270]),    # → 2026-01
    })
    result = compute_release(fam, client)
    assert result.is_stale is False


# --- H4: trend averages the anchor transform + honors its unit -------------

def _payrolls_like() -> tuple[FamilyConfig, _MockFRED]:
    fam = _family(
        headline=[{
            "id": "PAYEMS", "label": "Nonfarm payrolls",
            "primary_transform": "mom_chg", "display_unit": "K",
        }],
        context={
            "anchor_series": "PAYEMS",
            "anchor_transform": "mom_chg",
            "trends": [
                {"window_months": 3, "stat": "mean", "label": "3mo avg change"},
            ],
            "zscore_kind": "delta",
        },
    )
    # Level rising exactly +150/mo → every mom_chg is +150 → 3mo mean = +150.
    vals = [1000.0 + 150 * i for i in range(8)]
    return fam, _MockFRED({"PAYEMS": _monthly(vals)})


def test_mean_trend_averages_mom_chg_not_pct():
    fam, client = _payrolls_like()
    result = compute_release(fam, client)
    trend = result.context.trends[0]
    # Value is a jobs COUNT (~+150), not a fraction-of-a-percent (~0.1).
    assert trend.value == 150.0
    assert trend.transform == "mom_chg"
    assert trend.display_unit == "K"


def test_mean_trend_renders_as_count_with_unit():
    fam, client = _payrolls_like()
    result = compute_release(fam, client)
    lines = _format_trend_lines(result)
    assert lines[0] == "3mo avg change: +150K"
    assert "%" not in lines[0]
