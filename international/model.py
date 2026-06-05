"""Normalized data model for international series.

Every source (Eurostat / ECB / OECD / ONS / BoE / e-Stat / BoJ) is parsed
down to a list of `IntlObservation`, so the digest and dashboard never
need to know which dialect a number came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IntlObservation:
    """One (period, value). `period` is the source's native period label,
    normalized to one of: 'YYYY-MM' (monthly), 'YYYY-Qn' (quarterly),
    'YYYY' (annual), or 'YYYY-MM-DD' (daily). Observations within a result
    are stored oldest→newest."""

    period: str
    value: float


@dataclass
class IntlSeriesResult:
    """The outcome of fetching one configured series. On failure, `error`
    is set and `observations` is empty — the collector never raises, so a
    single dead source can't sink the whole digest."""

    spec_id: str
    region: str
    indicator: str
    label: str
    unit: str
    source: str
    freq: str
    decimals: int = 1
    invert: bool = False
    observations: list[IntlObservation] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.observations)

    @property
    def latest(self) -> IntlObservation | None:
        return self.observations[-1] if self.observations else None

    @property
    def previous(self) -> IntlObservation | None:
        return self.observations[-2] if len(self.observations) >= 2 else None

    @property
    def change(self) -> float | None:
        """Latest minus previous (in the series' own units — for a rate
        series this is the change in percentage points)."""
        if self.latest is not None and self.previous is not None:
            return self.latest.value - self.previous.value
        return None
