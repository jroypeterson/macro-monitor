"""Pinned-comment family lines deep-link to their dashboard card; the
current-state dashboard renders anchored cards + a click-to-zoom lightbox."""

from __future__ import annotations

from macro_monitor.config import FamilyConfig
from macro_monitor.charts.dashboard import _render_sections
from macro_monitor.outputs import family_slug
from macro_monitor.publishers.overview import build_overview_blocks


def test_render_sections_orders_consumer_first_default_last():
    out = _render_sections({
        "": ["<div class='card'><h2>X</h2></div>"],
        "Consumer": ["<div class='card'><h2>C</h2></div>"],
        "Zebra": ["<div class='card'><h2>Z</h2></div>"],
    })
    assert "<h2 class='section'>Consumer</h2>" in out
    # Consumer (preferred) → Zebra (other named, alpha) → Other US macro (default)
    assert out.index(">Consumer<") < out.index(">Zebra<") < out.index("Other US macro")
    assert out.count("<div class='grid'>") == 3


def test_render_sections_default_only_titled_other():
    out = _render_sections({"": ["<div class='card'><h2>X</h2></div>"]})
    assert "Other US macro" in out
    assert "<div class='grid'>" in out


def _family(display_name: str, tier: str) -> FamilyConfig:
    return FamilyConfig.model_validate({
        "tier": tier,
        "family_type": "numeric",
        "cadence": "monthly",
        "release_calendar_id": 1,
        "release_time_et": "08:30",
        "source": "fred",
        "display_name": display_name,
        "period_label_format": "{month_name} {year}",
        "headline": [{"id": "TEST", "label": "test", "primary_transform": "raw"}],
        "dedupe": {"headline_hash": ["TEST"], "component_hash": []},
        "agency": {"release_page": "http://test", "archive_path": "x"},
    })


def _all_text(blocks: list[dict]) -> str:
    return "\n".join(
        b.get("text", {}).get("text", "")
        for b in blocks
        if isinstance(b.get("text"), dict)
    )


def test_family_lines_deeplink_to_dashboard_card_anchor():
    fams = {
        "cpi": _family("Consumer Price Index", "A"),
        "umich": _family("UMich Sentiment", "B"),
    }
    _text, blocks = build_overview_blocks(fams)
    txt = _all_text(blocks)

    # Each family name is now a Slack mrkdwn link to its dashboard anchor.
    cpi_anchor = f"#fam-{family_slug('Consumer Price Index')}"
    assert f"dashboard/{cpi_anchor}|Consumer Price Index>" in txt
    umich_anchor = f"#fam-{family_slug('UMich Sentiment')}"
    assert f"dashboard/{umich_anchor}|UMich Sentiment>" in txt


def test_dashboard_card_carries_matching_anchor_and_lightbox(tmp_path):
    from macro_monitor.charts import dashboard

    fams = {"cpi": _family("Consumer Price Index", "A")}
    out = tmp_path / "index.html"
    dashboard.render_dashboard(fams, output_path=out, fetch_curve=False)
    htmltext = out.read_text(encoding="utf-8")

    # The anchor id the overview link points at must exist on the card.
    assert f"id='fam-{family_slug('Consumer Price Index')}'" in htmltext
    # Lightbox scaffolding is present so charts can expand on click.
    assert 'id="lightbox"' in htmltext
    assert "img.chart-thumb" in htmltext   # the click-binding script
    assert "cursor: zoom-in" in htmltext


def test_treasury_curve_panel_renders_and_colors_bond_style(tmp_path):
    from macro_monitor.charts import dashboard

    curve = [
        {"label": "2-Year", "level": 4.85, "chg_1d_bp": 3.0, "ytd_bp": -12.0, "asof": "2026-06-12"},
        {"label": "10-Year", "level": 4.40, "chg_1d_bp": -2.0, "ytd_bp": 25.0, "asof": "2026-06-12"},
        {"label": "30-Year", "level": 4.55, "chg_1d_bp": 0.0, "ytd_bp": 0.0, "asof": "2026-06-12"},
    ]
    fams = {"cpi": _family("Consumer Price Index", "A")}
    out = tmp_path / "index.html"
    dashboard.render_dashboard(fams, output_path=out, curve=curve, fetch_curve=False)
    htmltext = out.read_text(encoding="utf-8")

    assert "US Treasury curve" in htmltext
    assert "id='treasury-curve'" in htmltext
    assert "4.85%" in htmltext and "4.40%" in htmltext and "4.55%" in htmltext
    assert "DGS2/DGS10/DGS30" in htmltext


def test_treasury_curve_panel_omitted_when_no_data(tmp_path):
    from macro_monitor.charts import dashboard

    fams = {"cpi": _family("Consumer Price Index", "A")}
    out = tmp_path / "index.html"
    dashboard.render_dashboard(fams, output_path=out, curve=None, fetch_curve=False)
    htmltext = out.read_text(encoding="utf-8")
    assert "US Treasury curve" not in htmltext


def test_fmt_bp_bond_coloring():
    from macro_monitor.charts.dashboard import _fmt_bp

    up_txt, up_cls = _fmt_bp(5.0)
    assert up_txt == "+5 bp" and up_cls == "t-up"      # rise → red
    dn_txt, dn_cls = _fmt_bp(-4.0)
    assert dn_txt == "-4 bp" and dn_cls == "t-down"    # fall → green
    assert _fmt_bp(None) == ("—", "")


# ── Tier A / Tier B explainer notes ────────────────────────────────────────
# The pin states what each tier MEANS, including the Tier B gate. Those
# numbers are derived from the family config, never hand-written prose --
# a literal "1σ vs trailing 5y" in the pin silently becomes a lie the
# moment a family ships with a different gate. These tests are the pin.

def _gated_family(display_name: str, *, threshold: float, lookback: int,
                  zscore_kind: str) -> FamilyConfig:
    fam = _family(display_name, "B").model_dump()
    fam["tier_b_gate"] = {"vs": "trailing_5y_volatility", "threshold": threshold}
    fam["context"] = {
        "anchor_series": "TEST",
        "anchor_transform": "raw",
        "zscore_lookback_years": lookback,
        "zscore_kind": zscore_kind,
    }
    return FamilyConfig.model_validate(fam)


def test_tier_headers_carry_series_counts():
    fams = {
        "cpi": _family("Consumer Price Index", "A"),
        "gdp": _family("Gross Domestic Product", "A"),
        "umich": _gated_family("UMich Sentiment", threshold=1.0, lookback=5,
                               zscore_kind="delta"),
    }
    _text, blocks = build_overview_blocks(fams)
    txt = _all_text(blocks)
    assert "*Tier A (2 series)" in txt
    assert "*Tier B (1 series)" in txt


def test_tier_b_note_derives_gate_from_config_not_prose():
    """Change the threshold/lookback in config and the pin must follow."""
    fams = {
        "cpi": _family("Consumer Price Index", "A"),
        "umich": _gated_family("UMich Sentiment", threshold=2.5, lookback=10,
                               zscore_kind="delta"),
    }
    txt = _all_text(build_overview_blocks(fams)[1])
    assert "|z| ≥ 2.5σ" in txt, "gate threshold must come from tier_b_gate"
    assert "trailing 10y" in txt, "lookback must come from context"
    assert "1σ" not in txt.split("Tier B")[1].split("•")[0], "no hardcoded 1σ"
    # All-delta => the note claims the move, and names no level exception.
    assert "the test is on the *move*" in txt
    assert "gated on the level instead" not in txt


def test_tier_b_note_names_the_level_gated_minority():
    """A level-gated family must be called out by name, not averaged away."""
    fams = {
        "cpi": _family("Consumer Price Index", "A"),
        "umich": _gated_family("UMich Sentiment", threshold=1.0, lookback=5,
                               zscore_kind="delta"),
        "ip": _gated_family("Industrial Production", threshold=1.0, lookback=5,
                            zscore_kind="delta"),
        "delinq": _gated_family("Loan Delinquency Rates", threshold=1.0, lookback=5,
                                zscore_kind="level"),
    }
    txt = _all_text(build_overview_blocks(fams)[1])
    assert "for 2 of 3 the test is on the *move*" in txt
    assert "Loan Delinquency Rates is gated on the level instead" in txt


def test_tier_b_note_reports_a_mixed_threshold_range():
    fams = {
        "a": _gated_family("Alpha", threshold=1.0, lookback=5, zscore_kind="delta"),
        "b": _gated_family("Beta", threshold=2.0, lookback=5, zscore_kind="delta"),
    }
    txt = _all_text(build_overview_blocks(fams)[1])
    assert "|z| ≥ 1–2σ (varies by family)" in txt


def test_tier_notes_survive_families_without_gate_or_context():
    """FamilyConfig.context and .tier_b_gate are both Optional. A family
    missing either must degrade the note, never raise."""
    fams = {
        "cpi": _family("Consumer Price Index", "A"),
        "bare": _family("Bare Tier B", "B"),          # no gate, no context
    }
    _text, blocks = build_overview_blocks(fams)      # must not raise
    txt = _all_text(blocks)
    assert "*Tier B (1 series)" in txt
    assert "Notably," not in txt.split("Tier B")[1].split("•")[0]


def test_tier_a_note_states_what_membership_earns():
    fams = {"cpi": _family("Consumer Price Index", "A")}
    txt = _all_text(build_overview_blocks(fams)[1])
    assert "curated, not exhaustive" in txt
    assert "Google Calendar" in txt
