"""U-6 unemployment + white-collar employment + definitions (JP ask 2026-06-30).

Three adds to the Employment Situation family, locked here:
  1. U-6 (U6RATE) reported alongside U-3 (UNRATE), each with a plain-English
     definition ("Full Name (ABBR): …" convention — no bare abbreviations).
  2. Definitions render wherever the series does: Slack release footnote
     (a Block Kit `context` block, which takes elements[] NOT text), the
     archive HTML report, and the dashboard card.
  3. White-collar employment = USPBS + USINFO + USFIRE (CES supersectors),
     each cut + the computed sum shown as YoY % with an explicit
     accelerating / decelerating read on two horizons — vs the prior month
     AND vs 3 months ago (JP ask 2026-07-04).

Also locks the rate-level pp convention (JP ask 2026-07-04): series whose
level IS a percent (U-3, U-6…) render change context as percentage-point
("pp") deltas, never a relative %-of-a-%.
"""

from __future__ import annotations

from macro_monitor.charts.dashboard import _accel_html, _render_card
from macro_monitor.config import default_config_path, load_config
from macro_monitor.outputs import (
    _render_definitions_section,
    _serialize_component,
    _serialize_computed,
    _serialize_headline,
)
from macro_monitor.publishers.slack import (
    _format_definition_lines,
    _format_white_collar_components,
    accel_note,
    build_release_blocks,
    render_release_text,
)
from macro_monitor.release_runner import (
    ComponentSeriesResult,
    ComputedSeriesResult,
    HeadlineSeriesResult,
    ReleaseResult,
    TransformedValue,
)


# --- config wiring ---------------------------------------------------------

def _payrolls():
    return load_config(default_config_path())["payrolls"]


def test_u6_headline_declared_with_definition():
    fam = _payrolls()
    by_id = {h.id: h for h in fam.headline}
    assert "U6RATE" in by_id, "U-6 must ride the Employment Situation headline"
    u6 = by_id["U6RATE"]
    assert u6.basis == "level"
    assert set(u6.also_display) == {"mom_chg", "yoy_chg"}  # never a bare level
    # Full Name (ABBR) convention + the three ingredients of U-6.
    assert u6.definition and u6.definition.startswith("U-6 Underemployment Rate (U6RATE):")
    for phrase in ("marginally attached", "part-time for economic reasons"):
        assert phrase in u6.definition


def test_u3_relabeled_and_defined():
    fam = _payrolls()
    u3 = {h.id: h for h in fam.headline}["UNRATE"]
    assert "U-3" in u3.label
    assert u3.definition and u3.definition.startswith("U-3 Unemployment Rate (UNRATE):")
    assert "labor force" in u3.definition


def test_white_collar_computed_sum_wired():
    fam = _payrolls()
    comp_ids = {c.id for c in fam.components}
    assert {"USPBS", "USINFO", "USFIRE"} <= comp_ids
    wc = {c.id: c for c in fam.computed}["WC_TOTAL"]
    assert wc.method == "sum_of"
    assert set(wc.inputs) == {"USPBS", "USINFO", "USFIRE"}
    assert wc.primary_transform == "yoy_pct"
    assert "white_collar" in wc.tags
    assert wc.definition and "(USPBS)" in wc.definition
    # Revisions to the new series must surface (component-revision post).
    assert {"U6RATE", "USPBS", "USINFO", "USFIRE", "WC_TOTAL"} <= set(
        fam.dedupe.component_hash
    )


def test_unemployment_chart_carries_both_u3_and_u6():
    fam = _payrolls()
    chart = {c.name: c for c in fam.charts.thread}["unemployment_5y"]
    assert {s.id for s in chart.series} == {"UNRATE", "U6RATE"}


def test_white_collar_chart_declared():
    fam = _payrolls()
    chart = {c.name: c for c in fam.charts.thread}["white_collar_employment"]
    pane_ids = {s.id for pane in chart.panes for s in pane.series}
    assert {"WC_TOTAL", "USPBS", "USINFO", "USFIRE"} <= pane_ids


# --- accel/decel helpers ---------------------------------------------------

def test_accel_note_directions():
    assert accel_note(1.50, 1.20) == "accelerating vs prior month (+1.20%)"
    assert accel_note(0.80, 1.20) == "decelerating vs prior month (+1.20%)"
    assert accel_note(-1.00, -1.40) == "accelerating vs prior month (-1.40%)"
    assert accel_note(1.20, 1.20) == "unchanged vs prior month (+1.20%)"
    assert accel_note(None, 1.0) is None
    assert accel_note(1.0, None) is None


def test_accel_note_carries_both_comparisons():
    # BOTH horizons (JP ask 2026-07-04): vs prior month AND vs 3 months ago.
    assert accel_note(-0.29, -0.48, -0.61) == (
        "accelerating vs prior month (-0.48%), accelerating vs 3m ago (-0.61%)"
    )
    # Horizons may disagree — each gets its own word.
    assert accel_note(1.00, 0.80, 1.40) == (
        "accelerating vs prior month (+0.80%), decelerating vs 3m ago (+1.40%)"
    )
    # Missing 3m leg degrades to the prior-month comparison only.
    assert accel_note(1.00, 0.80, None) == "accelerating vs prior month (+0.80%)"
    # Missing prior-month leg still renders the 3m comparison.
    assert accel_note(1.00, None, 1.40) == "decelerating vs 3m ago (+1.40%)"
    # 0.005pp tolerance still absorbs sub-display-precision noise.
    assert accel_note(1.204, 1.20, 1.20) == (
        "unchanged vs prior month (+1.20%), unchanged vs 3m ago (+1.20%)"
    )


def test_accel_html_directions():
    assert "▲" in _accel_html(1.5, 1.2)
    assert "▼" in _accel_html(0.8, 1.2)
    assert "flat" in _accel_html(1.2, 1.2)
    assert _accel_html(None, 1.2) == ""


def test_accel_html_title_carries_both_comparisons():
    # One glyph (vs prior month drives it); hover title carries BOTH reads.
    tag = _accel_html(-0.29, -0.48, -0.61)
    assert "▲ accel" in tag
    assert "vs prior month (-0.48%): rising" in tag
    assert "vs 3m ago (-0.61%): rising" in tag
    # Disagreeing horizons: glyph still tracks prior month, title shows both.
    tag = _accel_html(1.00, 0.80, 1.40)
    assert "▲ accel" in tag
    assert "vs prior month (+0.80%): rising" in tag
    assert "vs 3m ago (+1.40%): falling" in tag
    # No 3m data → title only mentions the prior-month comparison.
    tag = _accel_html(1.00, 0.80)
    assert "3m ago" not in tag


# --- Slack rendering -------------------------------------------------------

def _wc_result():
    computed = ComputedSeriesResult(
        id="WC_TOTAL",
        label="White-collar employment (Prof & Business + Info + Financial)",
        method="sum_of", inputs=["USPBS", "USINFO", "USFIRE"],
        transformed=TransformedValue(transform="yoy_pct", value=0.55),
        also_display=[],
        prior_primary=TransformedValue(transform="yoy_pct", value=0.62),
        prior_3m_primary=TransformedValue(transform="yoy_pct", value=0.71),
        tags=["white_collar"],
        definition=(
            "White-Collar Employment (WC_TOTAL, computed): sum of USPBS + "
            "USINFO + USFIRE payrolls."
        ),
    )
    info = ComponentSeriesResult(
        id="USINFO", label="Information",
        transformed=TransformedValue(transform="yoy_pct", value=-1.20),
        tags=["white_collar"],
        prior_transformed=TransformedValue(transform="yoy_pct", value=-1.50),
        prior_3m_transformed=TransformedValue(transform="yoy_pct", value=-1.10),
    )
    u3 = HeadlineSeriesResult(
        id="UNRATE", label="Unemployment rate (U-3)",
        primary=TransformedValue(transform="raw", value=4.30),
        also_display=[], prior_primary=None,
        display_unit="%", basis="level",
        definition="U-3 Unemployment Rate (UNRATE): the official rate.",
    )
    u6 = HeadlineSeriesResult(
        id="U6RATE", label="Underemployment rate (U-6)",
        primary=TransformedValue(transform="raw", value=7.80),
        also_display=[
            TransformedValue(transform="mom_chg", value=-0.20),
            TransformedValue(transform="yoy_chg", value=0.40),
        ],
        prior_primary=TransformedValue(transform="raw", value=8.00),
        display_unit="%", basis="level",
        prior_period_label="April 2026",
        prior_mom=TransformedValue(transform="mom_chg", value=0.10),
        prior_yoy=TransformedValue(transform="yoy_chg", value=0.60),
        definition="U-6 Underemployment Rate (U6RATE): the broadest measure.",
    )
    return ReleaseResult(
        family_id="payrolls", family_display_name="Employment Situation",
        period="2026-05", period_label="May 2026",
        headline=[u3, u6], components=[info], computed=[computed], context=None,
        source="fred", source_fetched_at="", latest_observation_period="2026-05",
        expected_observation_period="2026-05", is_stale=False,
        source_lag_minutes=None,
    )


def test_white_collar_lines_carry_yoy_and_both_accel_reads():
    lines = _format_white_collar_components(_wc_result())
    assert lines[0] == (
        "White-collar employment (Prof & Business + Info + Financial): "
        "+0.55% YoY — decelerating vs prior month (+0.62%), "
        "decelerating vs 3m ago (+0.71%)"
    )
    # Less-negative YoY = the growth rate is RISING = accelerating (vs prior
    # month); vs 3 months ago it's more negative = decelerating. Both shown.
    assert lines[1] == (
        "  ↳ Information: -1.20% YoY — accelerating vs prior month (-1.50%), "
        "decelerating vs 3m ago (-1.10%)"
    )


def test_definition_lines_ordered_and_deduped():
    lines = _format_definition_lines(_wc_result())
    assert lines[0].startswith("U-3 Unemployment Rate (UNRATE):")
    assert lines[1].startswith("U-6 Underemployment Rate (U6RATE):")
    assert lines[2].startswith("White-Collar Employment (WC_TOTAL")
    assert len(lines) == len(set(lines))


def test_release_text_carries_wc_section_and_definitions():
    text = render_release_text(_wc_result())
    assert "Underemployment rate (U-6): 7.80% level" in text
    assert "decelerating vs prior month (+0.62%)" in text
    assert "ℹ️ U-6 Underemployment Rate (U6RATE):" in text


# --- rate-level pp convention (JP ask 2026-07-04) --------------------------

def test_rate_level_headline_change_context_renders_pp():
    # U-6's mom_chg/yoy_chg context must read as percentage points, labelled
    # "pp" — never a bare "-0.2" or a relative %-of-a-%.
    text = render_release_text(_wc_result())
    assert "Underemployment rate (U-6): 7.80% level (-0.20pp MoM, +0.40pp YoY)" in text


def test_prior_line_uses_pp_for_rate_level_series():
    # The PRIOR line for a rate level carries pp deltas as of the prior
    # period — "(+0.10pp MoM, +0.60pp YoY)" — not "(+3.85% YoY)".
    text = render_release_text(_wc_result())
    assert (
        "Prior (April 2026): Underemployment rate (U-6) 8.00% level "
        "(+0.10pp MoM, +0.60pp YoY)"
    ) in text
    assert "% YoY)" not in text.split("Prior (April 2026)")[1].split("\n")[0]


def test_is_rate_level_detection():
    from macro_monitor.release_runner import is_rate_level

    assert is_rate_level("raw", "%")            # U-3 / U-6 / quits rate / TCU
    assert not is_rate_level("raw", None)       # index level (UMich, JTSJOL)
    assert not is_rate_level("raw", "K")        # count level
    assert not is_rate_level("yoy_pct", "%")    # already a relative change
    assert not is_rate_level("mom_chg", "%")


def test_blocks_definitions_use_context_elements():
    """Slack `context` blocks take elements[] — a `text` field is an
    invalid_blocks HTTP 400 (killed scheduled_jobs_monitor 2026-06-08)."""
    blocks = build_release_blocks(_wc_result())
    ctx = [b for b in blocks if b["type"] == "context"]
    assert len(ctx) == 1
    assert "text" not in ctx[0]
    texts = [e["text"] for e in ctx[0]["elements"]]
    assert any("U-6 Underemployment Rate (U6RATE)" in t for t in texts)
    wc_sections = [
        b for b in blocks
        if b["type"] == "section"
        and "White-collar employment" in b["text"]["text"]
    ]
    assert len(wc_sections) == 1


# --- outputs serialization (feeds archive HTML + dashboard) ----------------

def test_serialization_carries_definitions_prior_and_computed():
    r = _wc_result()
    h = _serialize_headline(r.headline[1])
    assert h["definition"].startswith("U-6 Underemployment Rate")
    assert h["display_unit"] == "%"  # lets the dashboard spot rate levels

    c = _serialize_component(r.components[0])
    assert c["prior"] == {"transform": "yoy_pct", "value": -1.50}
    assert c["prior_3m"] == {"transform": "yoy_pct", "value": -1.10}

    cmp_ = _serialize_computed(r.computed[0])
    assert cmp_["transformed"]["value"] == 0.55
    assert cmp_["prior_primary"]["value"] == 0.62
    assert cmp_["prior_3m_primary"]["value"] == 0.71
    assert cmp_["tags"] == ["white_collar"]
    assert cmp_["definition"].startswith("White-Collar Employment")


def _payload():
    r = _wc_result()
    return {
        "is_stale": False,
        "period": "2026-05",
        "period_label": "May 2026",
        "headline": [_serialize_headline(h) for h in r.headline],
        "components": [_serialize_component(c) for c in r.components],
        "computed": [_serialize_computed(c) for c in r.computed],
        "charts": {},
    }


def test_archive_html_definitions_section():
    html = _render_definitions_section(_payload())
    assert "Definitions" in html
    assert "U-6 Underemployment Rate (U6RATE)" in html
    assert "White-Collar Employment (WC_TOTAL" in html


def test_dashboard_card_renders_wc_badge_accel_and_definitions():
    fam = _payrolls()
    card = _render_card("employment_situation", fam, _payload())
    assert "wc-badge" in card                 # WC aggregate line present
    assert "▼ decel" in card                  # +0.55 vs prior +0.62
    assert "▲ accel" in card                  # Information -1.20 vs -1.50
    assert "U-6 Underemployment Rate (U6RATE)" in card
    # Hover titles carry BOTH accel comparisons (prior month + 3m ago).
    assert "vs prior month (+0.62%): falling" in card
    assert "vs 3m ago (+0.71%): falling" in card
    assert "vs prior month (-1.50%): rising" in card
    assert "vs 3m ago (-1.10%): falling" in card
    # Rate-level headline (U-6): level shows its %, changes show as pp.
    assert "7.80%" in card
    assert "-0.20pp m/m" in card
    assert "+0.40pp y/y" in card
