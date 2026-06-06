"""Config loader + validator for release_families.yaml.

Validator is a HARD Phase 1 requirement (not optional). Runs at every CLI
invocation to catch typos before they cause silent failures on a real
release morning.

Checks:
  - every dedupe series is declared in headline or components (or is a computed series)
  - every chart series exists in headline/components/computed
  - every transform is a known name (see transforms.TRANSFORMS)
  - every family has a release_calendar_id (numeric) or source: federal_reserve (event)
  - tier_b_gate is None for tier A; structured dict for tier B
  - agency.pdf_url_static is a well-formed URL or null
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .computed import SUPPORTED_METHODS as _COMPUTED_METHODS
from .transforms import TRANSFORMS

_VALID_TRANSFORMS = set(TRANSFORMS.keys())
_VALID_TIERS = {"A", "B", "C"}
_VALID_FAMILY_TYPES = {"numeric", "event"}
_VALID_CADENCES = {"weekly", "monthly", "quarterly", "per_meeting"}


class SeriesSpec(BaseModel):
    """A single FRED series declaration."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    primary_transform: str = "raw"
    also_display: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Optional display unit for the primary value. Used by the publisher
    # when rendering mom_chg etc. Common values: "K" (thousands), "M"
    # (millions), "$B" (billions). None means use the raw number.
    display_unit: str | None = None
    # Optional explicit basis label clarifying WHAT the printed number is —
    # a YoY rate, a level, a 3mo-average, a proportion, etc. When None the
    # publisher derives a default from primary_transform (see
    # publishers.slack.basis_label). Set this to override the default, e.g.
    # UNRATE is `raw` but the basis should read "(level)" not just a bare %.
    basis: str | None = None

    @field_validator("primary_transform")
    @classmethod
    def _check_primary(cls, v: str) -> str:
        if v not in _VALID_TRANSFORMS:
            raise ValueError(
                f"primary_transform {v!r} is not a known transform. "
                f"Valid: {sorted(_VALID_TRANSFORMS)}"
            )
        return v

    @field_validator("also_display")
    @classmethod
    def _check_also_display(cls, v: list[str]) -> list[str]:
        for t in v:
            if t not in _VALID_TRANSFORMS:
                raise ValueError(
                    f"also_display transform {t!r} is not known. "
                    f"Valid: {sorted(_VALID_TRANSFORMS)}"
                )
        return v


class ComputedSeriesSpec(BaseModel):
    """A series derived from one or more declared headline/component series.

    Computed series get a synthetic `id` that doesn't correspond to a FRED
    series. The orchestrator computes them after FRED fetches and adds
    them to the same series cache so charts + components can reference
    them by id like any other series.

    No recursion in v1 — `inputs` must all be real declared FRED series,
    not other computed series. Validator enforces this.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    method: str
    inputs: list[str]
    primary_transform: str = "raw"
    also_display: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    display_unit: str | None = None
    # See SeriesSpec.basis — explicit per-metric basis label override.
    basis: str | None = None

    @field_validator("method")
    @classmethod
    def _check_method(cls, v: str) -> str:
        if v not in _COMPUTED_METHODS:
            raise ValueError(
                f"computed method {v!r} is not known. "
                f"Supported: {sorted(_COMPUTED_METHODS)}"
            )
        return v

    @field_validator("primary_transform")
    @classmethod
    def _check_primary(cls, v: str) -> str:
        if v not in _VALID_TRANSFORMS:
            raise ValueError(
                f"primary_transform {v!r} is not a known transform"
            )
        return v

    @field_validator("inputs")
    @classmethod
    def _check_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("computed.inputs must not be empty")
        return v


class TrendSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_months: int
    stat: str
    label: str


class ContextSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_series: str
    anchor_transform: str
    trends: list[TrendSpec] = Field(default_factory=list)
    zscore_lookback_years: int = 5
    zscore_kind: Literal["level", "delta"] = "delta"


class ChartSeriesRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    transform: str
    label: str

    @field_validator("transform")
    @classmethod
    def _check(cls, v: str) -> str:
        if v not in _VALID_TRANSFORMS:
            raise ValueError(f"transform {v!r} not known")
        return v


class ReferenceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    label: str
    style: Literal["solid", "dashed", "dotted"] = "dashed"


class PaneSpec(BaseModel):
    """A single panel within a multi-pane chart (`type: panes`)."""

    model_config = ConfigDict(extra="forbid")

    title: str
    type: Literal["line", "stacked_bar"]
    series: list[ChartSeriesRef]
    reference_lines: list[ReferenceLine] = Field(default_factory=list)
    highlight_latest: bool = False


class ChartSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["line", "stacked_bar", "panes"]
    filename: str
    name: str | None = None
    lookback_years: int | None = None
    lookback_months: int | None = None

    # For type=line | stacked_bar:
    series: list[ChartSeriesRef] = Field(default_factory=list)
    reference_lines: list[ReferenceLine] = Field(default_factory=list)
    highlight_latest: bool = False

    # For type=panes (multi-pane, one PNG):
    panes: list[PaneSpec] = Field(default_factory=list)
    layout: Literal["vertical", "horizontal"] = "vertical"

    @model_validator(mode="after")
    def _check_lookback(self) -> "ChartSpec":
        if self.lookback_years is None and self.lookback_months is None:
            raise ValueError("chart must declare lookback_years or lookback_months")
        return self

    @model_validator(mode="after")
    def _check_type_consistency(self) -> "ChartSpec":
        if self.type == "panes":
            if not self.panes:
                raise ValueError("chart type=panes must declare panes:")
            if self.series:
                raise ValueError(
                    "chart type=panes uses panes:, not top-level series:"
                )
        else:
            if not self.series:
                raise ValueError(
                    f"chart type={self.type} must declare series:"
                )
            if self.panes:
                raise ValueError(
                    f"chart type={self.type} does not use panes:"
                )
        return self


class ChartsBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main: ChartSpec
    thread: list[ChartSpec] = Field(default_factory=list)


class DedupeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline_hash: list[str]
    component_hash: list[str] = Field(default_factory=list)


class AgencySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_page: str
    pdf_url_static: str | None = None
    pdf_url_dated: str | None = None
    archive_path: str


class TierBGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float
    vs: Literal["trailing_5y_volatility", "consensus"]


class FamilyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Metadata
    tier: Literal["A", "B", "C"]
    family_type: Literal["numeric", "event"] = "numeric"
    cadence: str
    release_calendar_id: int | None = None
    release_time_et: str
    source: str
    fallback_source: str | None = None

    # Display
    display_name: str
    period_label_format: str

    # Series
    headline: list[SeriesSpec]
    components: list[SeriesSpec] = Field(default_factory=list)
    computed: list[ComputedSeriesSpec] = Field(default_factory=list)

    # Context + charts + posting
    context: ContextSpec | None = None
    charts: ChartsBundle | None = None
    tier_b_gate: TierBGate | None = None

    # Dedupe + reference
    dedupe: DedupeSpec
    agency: AgencySpec

    @field_validator("cadence")
    @classmethod
    def _check_cadence(cls, v: str) -> str:
        if v not in _VALID_CADENCES:
            raise ValueError(f"cadence {v!r} not in {_VALID_CADENCES}")
        return v


def _real_series_ids(family: FamilyConfig) -> set[str]:
    """IDs of FRED-fetched series (headline + components). Used to validate
    that computed.inputs only reference real series."""
    return {s.id for s in family.headline} | {s.id for s in family.components}


def _computed_series_ids(family: FamilyConfig) -> set[str]:
    return {c.id for c in family.computed}


def _declared_series_ids(family: FamilyConfig) -> set[str]:
    """All series the family produces, real + computed. Used by the
    validator to ensure dedupe and chart refs are subsets."""
    return _real_series_ids(family) | _computed_series_ids(family)


def validate_family(family: FamilyConfig) -> list[str]:
    """Run the Phase 1 hard validation checks. Returns a list of human-
    readable error strings (empty list = valid).
    """
    errors: list[str] = []
    declared = _declared_series_ids(family)
    real_ids = _real_series_ids(family)
    computed_ids = _computed_series_ids(family)

    # Computed series IDs must not collide with real FRED series IDs.
    collisions = real_ids & computed_ids
    for sid in collisions:
        errors.append(
            f"{family.display_name}: computed series {sid!r} collides with "
            f"a declared headline/component FRED series — pick a unique id"
        )

    # Every computed.inputs entry must reference a real FRED series.
    # No recursion in v1.
    for cs in family.computed:
        for input_id in cs.inputs:
            if input_id not in real_ids:
                errors.append(
                    f"{family.display_name}: computed {cs.id!r} inputs "
                    f"includes {input_id!r}, which is not a declared FRED "
                    f"series (must be in headline or components, not "
                    f"another computed)"
                )

    # Dedupe series must be declared (real or computed both okay).
    for sid in family.dedupe.headline_hash:
        if sid not in declared:
            errors.append(
                f"{family.display_name}: dedupe.headline_hash refers to "
                f"{sid!r}, which is not in headline / components / computed"
            )
    for sid in family.dedupe.component_hash:
        if sid not in declared:
            errors.append(
                f"{family.display_name}: dedupe.component_hash refers to "
                f"{sid!r}, which is not in headline / components / computed"
            )

    # Chart series must be declared.
    if family.charts is not None:
        for chart_ref in [family.charts.main] + list(family.charts.thread):
            chart_series_refs = list(chart_ref.series) + [
                s for pane in (chart_ref.panes or []) for s in pane.series
            ]
            for s in chart_series_refs:
                if s.id not in declared:
                    errors.append(
                        f"{family.display_name}: chart "
                        f"{chart_ref.name or 'main'!r} references {s.id!r} "
                        f"which is not in headline / components / computed"
                    )

    # Context anchor must be declared.
    if family.context is not None:
        if family.context.anchor_series not in declared:
            errors.append(
                f"{family.display_name}: context.anchor_series "
                f"{family.context.anchor_series!r} not in headline / components / computed"
            )

    # Numeric families need a calendar source; event families source from FRB
    if family.family_type == "numeric":
        if family.release_calendar_id is None:
            errors.append(
                f"{family.display_name}: numeric families must declare "
                f"release_calendar_id (FRED release_id)"
            )
    elif family.family_type == "event":
        if family.source != "federal_reserve":
            errors.append(
                f"{family.display_name}: event families must have "
                f"source: federal_reserve (got {family.source!r})"
            )

    # Tier-A families must not have a tier_b_gate; Tier B must.
    if family.tier == "A" and family.tier_b_gate is not None:
        errors.append(
            f"{family.display_name}: tier A families post unconditionally; "
            f"tier_b_gate must be null"
        )
    if family.tier == "B" and family.tier_b_gate is None:
        errors.append(
            f"{family.display_name}: tier B families require tier_b_gate"
        )

    return errors


def load_config(path: str | Path) -> dict[str, FamilyConfig]:
    """Load and parse release_families.yaml. Does NOT run validate_family;
    call validate_all_or_raise() for that.
    """
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    families_raw = raw.get("families") or {}
    families: dict[str, FamilyConfig] = {}
    for family_id, family_dict in families_raw.items():
        families[family_id] = FamilyConfig.model_validate(family_dict)
    return families


def validate_all_or_raise(families: dict[str, FamilyConfig]) -> None:
    """Run validate_family across every family; raise ValueError listing
    all errors if any are found. Idiomatic boundary for the CLI's
    validate-config command.
    """
    all_errors: list[str] = []
    for family in families.values():
        all_errors.extend(validate_family(family))
    if all_errors:
        msg = "Config validation failed:\n  - " + "\n  - ".join(all_errors)
        raise ValueError(msg)


def calendar_families(
    families: dict[str, FamilyConfig],
) -> dict[str, FamilyConfig]:
    """The single definition of "what belongs on a calendar surface".

    A family appears on the schedule calendars (the Google Calendar
    backfill AND the annual HTML grid) iff it has a FRED
    `release_calendar_id` to pull release dates from. Both surfaces must
    route through this so their family scope can never silently diverge
    — that divergence is the bug class that previously left the annual
    HTML showing only Tier A while the Google Calendar carried all 17.

    Tier is deliberately NOT filtered here: both surfaces show all tiers.
    To curate a surface by tier later, do it at the call site, not here,
    so the shared baseline stays the same.
    """
    return {
        fid: f
        for fid, f in families.items()
        if f.release_calendar_id is not None
    }


def default_config_path() -> Path:
    return Path(__file__).parent / "config" / "release_families.yaml"
