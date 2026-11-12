"""The release post is labelled with its tier, like its preview.

JP 2026-11-12: the weekly preview and the release reminder say `[Tier A]`
but the print itself did not. Both the Block Kit header and the text
fallback must carry it, and the runner must actually populate the field
(a title helper fed `tier=None` renders nothing and would stay green).
"""

from __future__ import annotations

import pytest

from macro_monitor.posts_ledger import PostDecision
from macro_monitor.publishers.slack import build_release_blocks, render_release_text
from macro_monitor.release_runner import ReleaseResult, compute_release


def _result(tier):
    return ReleaseResult(
        family_id="x", family_display_name="New Home Sales", period="2026-10",
        period_label="October 2026", headline=[], components=[], computed=[],
        context=None, source="fred", source_fetched_at="",
        latest_observation_period="2026-10", expected_observation_period="2026-10",
        is_stale=False, source_lag_minutes=None, tier=tier,
    )


@pytest.mark.parametrize("tier", ["A", "B"])
def test_header_and_text_fallback_carry_the_tier(tier):
    r = _result(tier)
    want = f"🔴 RELEASED — New Home Sales October 2026 [Tier {tier}]"
    assert build_release_blocks(r)[0]["text"]["text"] == want
    assert render_release_text(r).splitlines()[0] == want


def test_revision_post_carries_the_tier_too():
    r = _result("A")
    title = build_release_blocks(r, PostDecision.REVISED_HEADLINE)[0]["text"]["text"]
    assert title.endswith("[Tier A]")


def test_no_tier_renders_the_old_title():
    r = _result(None)
    assert build_release_blocks(r)[0]["text"]["text"] == (
        "🔴 RELEASED — New Home Sales October 2026"
    )


def test_runner_populates_tier_from_the_family():
    """The seam: the real runner -> the real header, no hand-built result."""
    from tests.test_release_stale_and_trends import _MockFRED, _family, _monthly

    fam = _family([{"id": "S", "label": "s", "primary_transform": "mom_chg"}])
    result = compute_release(fam, _MockFRED({"S": _monthly([1, 2, 3, 4, 5, 6, 7, 8])}))
    assert result.tier == "A"
    assert build_release_blocks(result)[0]["text"]["text"].endswith("[Tier A]")
