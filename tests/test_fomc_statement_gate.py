"""FOMC statement posting gate: "what is owed", not "what time is it".

2026-09-16: GitHub started the 14:05 ET cron at 17:13 and 17:56 ET. The bash
step in fomc_statement.yml required ET_HOUR == 14, so both runs exited green
and the decision-day statement was never posted. The gate now lives in Python
(`cmd_fomc_statement`): a decision on/before today within a short lookback,
non-empty statement text, and no posts-ledger row for
('fomc_statement', decision date). Slack and the Fed fetch are stubbed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from macro_monitor import cli
from macro_monitor import fomc_statement as fs
from macro_monitor.posts_ledger import PostsLedger

ET = ZoneInfo("America/New_York")
REPO = Path(cli.__file__).parent
DECISION = "2026-09-16"
STATEMENT_HTML = (
    "<html><body><nav>menu</nav><p>Recent indicators suggest that economic "
    "activity has continued to expand at a solid pace.</p>"
    "<p>Implementation Note</p></body></html>"
)


# What a completed analysis looks like coming back from the model.
ANALYSIS_JSON = json.dumps({
    "target_range": "3-1/2 to 3-3/4 percent",
    "action": "hike",
    "stance": "hawkish",
    "summary": "The Committee raised rates to support a timelier return to 2 percent.",
    "changes": ["inflation characterization: supply-shock language dropped"],
    "dissents": "",
})


@pytest.fixture
def harness(monkeypatch, tmp_path):
    import macro_monitor.posts_ledger as pl

    state = {"posts": [], "post_ok": True, "html": STATEMENT_HTML,
             "now": _dt.datetime(2026, 9, 16, 17, 0, tzinfo=ET),
             "analysis_json": ANALYSIS_JSON}
    db = tmp_path / "posts.db"
    state["db"] = db
    monkeypatch.setattr(pl, "PostsLedger", lambda: PostsLedger(db))
    monkeypatch.setattr(fs, "_fetch", lambda url, timeout=20: state["html"])
    monkeypatch.setattr(fs, "_now_et", lambda: state["now"])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # no LLM call

    # The analysis is stubbed through the REAL parser, so these tests exercise a
    # genuinely SUCCESSFUL analysis (`analysed=True`) without an API call.
    #
    # They used to rely on `delenv` alone, which made `analyze_statement` return
    # its "ANTHROPIC_API_KEY not set" fallback -- `action="hold"`,
    # `stance="neutral"`, no target -- and then asserted that the lane POSTED it
    # and WROTE A LEDGER ROW. The suite was certifying the defect Codex found on
    # 2026-09-21: a failed analysis published to #macro-and-markets as a real
    # Fed decision, then recorded so the correction never fires. Every one of
    # these tests passed BECAUSE the bug was there.
    # Mirrors all three branches of the real `analyze_statement` contract --
    # no text, analysis failed, analysis succeeded -- so a test can select one
    # without the stub quietly making the other two unreachable.
    def fake_analyze(current_text, prior_text, decision_date, sep=False,
                     client=None, model=None):
        iso = decision_date.isoformat()
        if not (current_text or "").strip():
            return fs.StatementVerdict(decision_date=iso, sep=sep, has_text=False,
                                       why="statement text unavailable")
        if state.get("analysis_fails"):
            return fs.StatementVerdict(decision_date=iso, sep=sep,
                                       why=state["analysis_fails"])
        return fs._parse(state["analysis_json"], iso, sep)

    monkeypatch.setattr(fs, "analyze_statement", fake_analyze)

    def fake_post(text, blocks):
        state["posts"].append(text)
        # the ledger must not be written before Slack has the message
        with PostsLedger(db) as led:
            state.setdefault("row_at_post", []).append(
                led.get(fs.LEDGER_FAMILY, DECISION))
        return (True, "posted ts=1.0") if state["post_ok"] else (False, "slack error: x")

    monkeypatch.setattr(fs, "post_to_macro", fake_post)
    return state


def _args(**kw) -> argparse.Namespace:
    base = dict(date=None, model=None, dry_run=False, force=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _row(state):
    with PostsLedger(state["db"]) as led:
        return led.get(fs.LEDGER_FAMILY, DECISION)


def test_late_run_on_decision_day_posts(harness):
    """17:00 ET on decision day (the 2026-09-16 failure) must post."""
    assert cli.cmd_fomc_statement(_args()) == 0
    assert len(harness["posts"]) == 1
    assert _row(harness) is not None


def test_run_two_days_later_still_posts(harness):
    harness["now"] = _dt.datetime(2026, 9, 18, 9, 0, tzinfo=ET)
    assert cli.cmd_fomc_statement(_args()) == 0
    assert len(harness["posts"]) == 1


def test_empty_statement_text_fails_red_without_ledger_or_post(harness):
    """Fed page not up yet: exit non-zero so the run is visibly red and the
    next run retries; no row, so that retry is not deduped away."""
    harness["html"] = ""
    assert cli.cmd_fomc_statement(_args()) != 0
    assert harness["posts"] == []
    assert _row(harness) is None


def test_second_run_after_success_does_not_repost(harness):
    assert cli.cmd_fomc_statement(_args()) == 0
    assert cli.cmd_fomc_statement(_args()) == 0
    assert len(harness["posts"]) == 1


def test_force_reposts(harness):
    assert cli.cmd_fomc_statement(_args()) == 0
    assert cli.cmd_fomc_statement(_args(force=True)) == 0
    assert len(harness["posts"]) == 2


def test_failed_slack_post_writes_no_ledger_row(harness):
    harness["post_ok"] = False
    assert cli.cmd_fomc_statement(_args()) != 0
    assert len(harness["posts"]) == 1
    assert harness["row_at_post"] == [None]
    assert _row(harness) is None


def test_ledger_row_is_written_after_the_post(harness):
    assert cli.cmd_fomc_statement(_args()) == 0
    assert harness["row_at_post"] == [None]
    assert _row(harness) is not None


def test_non_decision_day_no_post_exit_zero(harness):
    harness["now"] = _dt.datetime(2026, 9, 25, 14, 5, tzinfo=ET)
    assert cli.cmd_fomc_statement(_args()) == 0
    assert harness["posts"] == []
    assert _row(harness) is None


def test_dry_run_neither_posts_nor_records(harness):
    assert cli.cmd_fomc_statement(_args(dry_run=True)) == 0
    assert harness["posts"] == []
    assert _row(harness) is None


def test_cli_parser_has_force():
    ns = cli.build_parser().parse_args(["fomc-statement", "--post", "--force"])
    assert ns.force is True and ns.dry_run is False


# --- workflow (static) ------------------------------------------------------

def _wf_text() -> str:
    return (REPO / ".github" / "workflows" / "fomc_statement.yml").read_text(encoding="utf-8")


def test_workflow_has_no_wallclock_gate():
    """No step may read the clock or skip the post: the gate is Python's."""
    steps = yaml.safe_load(_wf_text())["jobs"]["statement"]["steps"]
    for s in steps:
        run = s.get("run", "")
        assert "ET_HOUR" not in run and "+%H" not in run, s.get("name")
    post = [s for s in steps if "fomc-statement --post" in s.get("run", "")]
    assert len(post) == 1 and "if" not in post[0], "post step is conditional"


def test_workflow_persists_the_ledger():
    doc = yaml.safe_load(_wf_text())
    assert doc.get("permissions", {}).get("contents") == "write"
    steps = doc["jobs"]["statement"]["steps"]
    persist = [s for s in steps if "git add state/posts.db" in s.get("run", "")]
    assert persist, "no step commits state/posts.db"
    run = persist[0]["run"]
    assert persist[0].get("if") == "always()"
    assert "git pull --rebase --autostash" in run and "git push" in run


def test_workflow_has_its_own_concurrency_group():
    conc = yaml.safe_load(_wf_text()).get("concurrency")
    assert isinstance(conc, dict)
    assert conc.get("group") == "fomc-statement"
    assert conc.get("cancel-in-progress") is False


# ---------------------------------------------------------------- P1 -----
# Codex, 2026-09-21: a FAILED analysis was posted as a real decision and then
# recorded, permanently suppressing the correction. Only the missing-text case
# was guarded; an SDK/API-key/API/parse failure returns the verdict DEFAULTS --
# action "hold", stance "neutral", no target -- which is indistinguishable by
# inspection from a genuine hold at a neutral meeting. Hence `analysed`.

@pytest.mark.parametrize("reason", [
    "anthropic SDK not installed",
    "ANTHROPIC_API_KEY not set",
    "APIStatusError: 529 overloaded",
    "parse error: Expecting value: line 1 column 1 (char 0)",
])
def test_a_failed_analysis_neither_posts_nor_records(harness, reason):
    """All four real failure paths. Each returns a plausible-looking HOLD."""
    harness["analysis_fails"] = reason
    assert cli.cmd_fomc_statement(_args()) != 0, (
        f"{reason!r}: the lane reported success on an analysis that did not run"
    )
    assert harness["posts"] == [], (
        f"{reason!r}: a failed analysis was posted to #macro-and-markets as a "
        f"real Fed decision"
    )
    with PostsLedger(harness["db"]) as led:
        assert led.get(fs.LEDGER_FAMILY, DECISION) is None, (
            f"{reason!r}: the failed analysis was RECORDED, so the next run "
            f"would skip it and the wrong verdict would stand permanently"
        )


def test_the_retry_after_a_failed_analysis_posts_the_real_verdict(harness):
    """Not recording is only useful if the next run actually succeeds."""
    harness["analysis_fails"] = "APIStatusError: 529 overloaded"
    assert cli.cmd_fomc_statement(_args()) != 0
    assert harness["posts"] == []

    harness["analysis_fails"] = None          # the transient cause clears
    assert cli.cmd_fomc_statement(_args()) == 0
    assert len(harness["posts"]) == 1
    assert "HIKE" in harness["posts"][0]
    with PostsLedger(harness["db"]) as led:
        assert led.get(fs.LEDGER_FAMILY, DECISION) is not None


def test_a_real_hold_is_still_posted(harness):
    """⛑ Both sides of the classifier.

    `analysed` must key on whether the model ANSWERED, never on whether the
    answer looks like the defaults -- a genuine hold at a neutral meeting is
    field-for-field identical to a total failure. Storing the answer rather
    than inferring it is the only thing that separates them.
    """
    harness["analysis_json"] = json.dumps({
        "target_range": "3-1/2 to 3-3/4 percent",
        "action": "hold", "stance": "neutral",
        "summary": "The Committee left the target range unchanged.",
        "changes": [], "dissents": "",
    })
    assert cli.cmd_fomc_statement(_args()) == 0
    assert len(harness["posts"]) == 1
    assert "HOLD" in harness["posts"][0]


def test_analysed_is_false_by_default_so_a_new_failure_path_is_inert(harness):
    """A branch added later must fail closed without anyone remembering to."""
    v = fs.StatementVerdict(decision_date=DECISION)
    assert v.analysed is False
    assert v.has_text is True, (
        "has_text defaulting True is exactly why it could not serve as this "
        "guard -- the two fields answer different questions"
    )
