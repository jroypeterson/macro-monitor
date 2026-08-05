"""The two digest lanes that posted block lists without a ceiling guard (#268).

`fed_speeches` and `research_digest` both build their blocks in a loop over new items
and hand the whole list to `chat_postMessage`. Slack rejects >50 blocks with
`invalid_blocks`, an error that names nothing — and the count is largest on exactly
the days worth reading, so the failure correlates with the value of the message.
`publishers/slack.py` already solved this for the release digests; these two never
picked it up.

Splitting, never truncating: a shorter digest silently drops speeches, which is the
same class of loss the guard exists to prevent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from macro_monitor.publishers import guarded_post as gp  # noqa: E402


class FakeClient:
    """Records calls; mimics slack_sdk's response shape."""

    def __init__(self, fail_on: int | None = None):
        self.calls: list[dict] = []
        self.fail_on = fail_on

    def chat_postMessage(self, **kw):
        self.calls.append(kw)
        if self.fail_on is not None and len(self.calls) == self.fail_on:
            raise RuntimeError("slack boom")
        return {"ts": f"ts{len(self.calls)}", "channel": kw.get("channel")}


def blocks(n: int) -> list[dict]:
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f"b{i}"}}
            for i in range(n)]


def test_a_small_digest_posts_once_untouched():
    c = FakeClient()
    ok, msg = gp.post_guarded(c, "C1", "text", blocks(10))
    assert ok and len(c.calls) == 1
    assert len(c.calls[0]["blocks"]) == 10


def test_an_oversized_digest_is_SPLIT_not_truncated():
    """55 blocks is the real shape that killed a portfolio_daily digest (#264):
    no individual block broke a rule, the COUNT did."""
    c = FakeClient()
    ok, msg = gp.post_guarded(c, "C1", "text", blocks(120))
    assert ok
    posted = sum(len(call["blocks"]) for call in c.calls)
    assert posted == 120, "every block must survive; splitting never drops any"
    assert all(len(call["blocks"]) <= 50 for call in c.calls)


def test_continuations_go_into_the_THREAD_not_the_channel():
    """Matching what publishers/slack.py already does — extras belong in the thread,
    so the channel keeps one message per run."""
    c = FakeClient()
    gp.post_guarded(c, "C1", "text", blocks(120))
    assert "thread_ts" not in c.calls[0]
    assert all(call.get("thread_ts") == "ts1" for call in c.calls[1:])


def test_the_first_chunk_failing_is_a_failure():
    c = FakeClient(fail_on=1)
    ok, msg = gp.post_guarded(c, "C1", "text", blocks(120))
    assert not ok and "boom" in msg


def test_a_continuation_failing_is_reported_but_the_run_still_counts_as_posted():
    """The reader HAS the digest at that point. Losing a continuation is a partial,
    not a total failure — but it must be said out loud, not swallowed."""
    c = FakeClient(fail_on=2)
    ok, msg = gp.post_guarded(c, "C1", "text", blocks(120))
    assert ok
    assert "continuation" in msg.lower()


def test_violations_are_named_on_stderr(capsys):
    """`invalid_blocks` names nothing, so the guard has to say which ceiling broke."""
    over = [{"type": "section", "text": {"type": "mrkdwn", "text": "x" * 3500}}]
    gp.post_guarded(FakeClient(), "C1", "t", over)
    assert "3000" in capsys.readouterr().err or "section" in capsys.readouterr().err


def test_empty_blocks_posts_text_only_rather_than_raising():
    c = FakeClient()
    ok, _ = gp.post_guarded(c, "C1", "just text", [])
    assert ok and len(c.calls) == 1
