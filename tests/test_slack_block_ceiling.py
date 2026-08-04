"""
Block Kit ceiling guard for the release publisher (fleet board #268).

`_live_publish` posted `blocks` straight to `chat_postMessage` with no ceiling check.
Slack rejects >50 blocks with `invalid_blocks`, which names nothing — so a rejection
here would have been silent and undiagnosable. The digests build blocks in a loop over
components and trends, so the count scales with how eventful the release was: the
payload is biggest on exactly the days worth reading.

The guard is VENDORED rather than imported from `_shared/` because these lanes run in
GitHub Actions, where `_shared/` is not checked out. `test_the_guard_has_no_workspace_
dependency` is the pin on that — it is the whole reason the duplication is accepted.
"""

from __future__ import annotations

from macro_monitor.publishers import slack_blocks_client as g


def sec(i=0):
    return {"type": "section", "text": {"type": "mrkdwn", "text": f"item {i}"}}


def div():
    return {"type": "divider"}


def test_an_oversized_payload_is_named():
    p = g.problems([sec(i) for i in range(137)])
    assert p and "137 blocks" in p[0]


def test_a_normal_payload_is_clean():
    assert g.problems([sec(i) for i in range(12)]) == []


def test_a_context_block_without_elements_is_caught():
    """Slack rejects the WHOLE message for this, so it must be named before sending."""
    assert any("elements" in x for x in g.problems([sec(), {"type": "context"}]))


def test_chunking_loses_nothing():
    blocks = [sec(i) for i in range(137)]
    chunks = g.chunk(blocks)
    assert [b for ch in chunks for b in ch] == blocks
    assert all(len(ch) <= 50 for ch in chunks)


def test_a_normal_release_is_a_single_message():
    """The common path must behave exactly as before the guard existed."""
    blocks = [sec(i) for i in range(12)]
    assert g.chunk(blocks) == [blocks]


def test_chunk_prefers_a_divider_seam():
    blocks = [sec(i) for i in range(60)]
    blocks[47] = div()
    assert len(g.chunk(blocks)[0]) == 48


def test_chunking_terminates_on_all_dividers():
    chunks = g.chunk([div()] * 300)
    assert sum(len(c) for c in chunks) == 300
    assert all(1 <= len(c) <= 50 for c in chunks)


def test_the_guard_has_no_workspace_dependency():
    """THE POINT OF VENDORING IT.

    These lanes run in GitHub Actions, where `<workspace>/_shared/` does not exist. If
    this module ever grows a sys.path shim to it, the guard imports fine on the laptop
    and silently degrades to 'post unchunked' on every CI run — inert precisely where
    it is needed, while the fleet docs claim the project is covered.
    """
    import inspect
    # Check the CODE, not the docstring — the docstring names `_shared/` on purpose to
    # explain why it is not depended on. Strip it before asserting, or the test
    # contradicts the very comment that justifies it.
    src = inspect.getsource(g)
    code = src.split('"""', 2)[-1]
    for forbidden in ("sys.path", "import slack_blocks", "importlib", "_shared"):
        assert forbidden not in code, (
            f"{forbidden!r} in the vendored guard's code: it must not reach outside "
            f"this repo, or it goes inert in CI")
