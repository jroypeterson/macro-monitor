"""Ahead-of-the-Curve chart ride-along: post the figure(s) a release drives
into chat when its data lands. Network-free — the build + Slack client are
stubbed."""
from __future__ import annotations

import pytest

from macro_monitor.ahead_of_curve import post


# --- release -> figures mapping -----------------------------------------

def test_figures_for_release_matches_primary_series():
    pce = {f.id for f in post.figures_for_release(54)}      # Personal Income & Outlays
    assert "real_pce_yoy" in pce                            # PCE-headed figure
    cpi = [f.id for f in post.figures_for_release(10)]
    assert cpi == ["inflation_vs_rates"]                    # CPI-headed figure


def test_figure_not_double_counted_across_its_series_releases():
    # pce_vs_employment has both PCE (rel 54) and employment (rel 50) series;
    # it must post only under its HEADLINE (first) series' release, not both.
    in_pce = {f.id for f in post.figures_for_release(54)}
    in_emp = {f.id for f in post.figures_for_release(50)}
    assert "pce_vs_employment" in in_pce
    assert "pce_vs_employment" not in in_emp


def test_figures_for_unknown_release_is_empty():
    assert post.figures_for_release(999999) == []


# --- dry-run -------------------------------------------------------------

def test_post_for_release_dry_run_lists_without_building(monkeypatch):
    # _build_once must NOT be called on a dry-run.
    monkeypatch.setattr(post, "_build_once", lambda key: pytest.fail("built on dry-run"))
    ids = post.post_for_release(10, dry_run=True)
    assert ids == ["inflation_vs_rates"]


def test_post_for_unknown_release_returns_empty(monkeypatch):
    monkeypatch.setattr(post, "_build_once", lambda key: pytest.fail("built with no figs"))
    assert post.post_for_release(999999) == []


# --- live post (stubbed Slack) ------------------------------------------

class _FakePublisher:
    bot_token = "xoxb-test"
    channel_id = "C_MACRO"

    def __init__(self):
        self.alerts = []

    def _alert_status_reports(self, msg):
        self.alerts.append(msg)


class _FakeWebClient:
    last = {}

    def __init__(self, token=None):
        self.token = token

    def files_upload_v2(self, **kwargs):
        _FakeWebClient.last = kwargs
        return {"ok": True}


def test_post_for_release_uploads_one_threaded_reply(monkeypatch, tmp_path):
    png = tmp_path / "inflation_vs_rates.png"
    png.write_bytes(b"\x89PNG fake")
    monkeypatch.setattr(post, "_build_once", lambda key: {"inflation_vs_rates": png})
    monkeypatch.setattr("slack_sdk.WebClient", _FakeWebClient)

    pub = _FakePublisher()
    posted = post.post_for_release(
        10, thread_ts="123.45", channel="C_REL", dry_run=False, publisher=pub
    )

    assert posted == ["inflation_vs_rates"]
    up = _FakeWebClient.last
    assert up["channel"] == "C_REL"
    assert up["thread_ts"] == "123.45"
    assert len(up["file_uploads"]) == 1
    assert "Ahead of the Curve" in up["initial_comment"]
    assert not pub.alerts


def test_post_for_release_skips_missing_png(monkeypatch):
    # Build produced no png for the figure -> nothing uploaded, no crash.
    monkeypatch.setattr(post, "_build_once", lambda key: {})
    monkeypatch.setattr("slack_sdk.WebClient", _FakeWebClient)
    _FakeWebClient.last = {}
    assert post.post_for_release(10, dry_run=False, publisher=_FakePublisher()) == []


def test_post_for_release_upload_failure_is_nonfatal(monkeypatch, tmp_path):
    from slack_sdk.errors import SlackApiError

    png = tmp_path / "inflation_vs_rates.png"
    png.write_bytes(b"x")

    class _BoomClient:
        def __init__(self, token=None):
            pass

        def files_upload_v2(self, **kwargs):
            raise SlackApiError("boom", {"error": "upload_failed"})

    monkeypatch.setattr(post, "_build_once", lambda key: {"inflation_vs_rates": png})
    monkeypatch.setattr("slack_sdk.WebClient", _BoomClient)
    pub = _FakePublisher()
    assert post.post_for_release(10, dry_run=False, publisher=pub) == []
    assert pub.alerts and "upload failed" in pub.alerts[0]
