"""Post a Block Kit payload without tripping Slack's 50-block ceiling.

Board #268. `publishers/slack.py` already validates + chunks its release digests; the
`fed_speeches` and `research_digest` schedulers never picked that up and handed their
whole block list straight to `chat_postMessage`. Both build blocks in a LOOP over new
items, so the count scales with how eventful the day was -- which means the failure
correlates with the value of the message. Slack answers >50 blocks with
`invalid_blocks`, an error that names nothing; portfolio_daily lost a whole digest to
that shape on 2026-07-30 (55 blocks, 50 allowed, after a 45-minute run).

SPLIT, NEVER TRUNCATE. A shorter digest silently drops speeches, which is the same
class of loss the guard exists to prevent. Continuations go into the THREAD, matching
where this project already puts its extras, so the channel keeps one message per run.

Imports the VENDORED `slack_blocks_client`, not `_shared/` -- this project's lanes run
in GitHub Actions where the Dropbox sibling is not checked out, and a shim would
import fine locally while going silently inert in CI.
"""
from __future__ import annotations

import sys

from . import slack_blocks_client


def post_guarded(client, channel: str, text: str,
                 blocks: list[dict]) -> tuple[bool, str]:
    """chat_postMessage with ceiling validation + threaded continuations.

    Returns (ok, message). `ok` gates the caller's LEDGER WRITE, not the reader's
    experience -- both callers do `if ok: record_posted(payload)`, which permanently
    dedupes every URL in the payload. So a lost continuation must return False: its
    items were never delivered, and recording them would bury them forever. The cost
    of False is that the next run re-posts some already-delivered items; duplicates
    are recoverable, permanent loss is not. Same rule the fr-feed lane states in its
    own words: "do NOT record so a retry re-alerts (no silent loss)".
    """
    for problem in slack_blocks_client.problems(blocks or []):
        # `invalid_blocks` names nothing, so name it ourselves before Slack is asked.
        print(f"[macro_monitor] Block Kit: {problem}", file=sys.stderr)

    chunks = slack_blocks_client.chunk(blocks) if blocks else [[]]

    try:
        resp = client.chat_postMessage(
            channel=channel, text=text, blocks=chunks[0] or None)
    except Exception as e:  # noqa: BLE001 — the caller reports, never crashes the lane
        return False, f"slack error: {e}"

    ts = resp.get("ts")
    lost = []
    for i, chunk in enumerate(chunks[1:], start=2):
        try:
            client.chat_postMessage(
                channel=channel, text=f"{text} (cont. {i}/{len(chunks)})",
                blocks=chunk, thread_ts=ts)
        except Exception as e:  # noqa: BLE001
            lost.append(f"{i}: {e}")

    if lost:
        # FAILS the run on purpose. The reader got the first chunk, but the caller
        # must not write its dedupe ledger: doing so would mark the undelivered
        # items as posted and no future run would ever re-send them.
        return False, (f"posted ts={ts} but {len(lost)} continuation(s) FAILED "
                       f"({'; '.join(lost)}) -- NOT recorded, so the next run will "
                       f"re-alert rather than lose them")
    if len(chunks) > 1:
        return True, f"posted ts={ts} in {len(chunks)} parts (threaded)"
    return True, f"posted ts={ts}"
