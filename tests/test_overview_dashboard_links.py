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
