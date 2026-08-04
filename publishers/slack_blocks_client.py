"""Block Kit ceiling guard — VENDORED, deliberately, not a shim to `_shared/`.

**Why vendored.** This project's release lanes run in GitHub Actions
(`release_polling.yml` et al), and `<workspace>/_shared/` is a Dropbox sibling that is
NOT checked out there. A `sys.path` shim would import fine on JP's laptop and fail on
every CI run — degrading to "post unchunked" exactly where the guard is needed, while
the fleet docs claimed this project was covered. A guard that is silently inert in
production is worse than no guard, because it stops anyone looking again.

The project already made this call once and wrote it down: `email_alert_client.py` is
vendored for the same reason (see `CLAUDE.md`). Same tradeoff accepted here — a copy of
~50 lines beats a dependency that evaporates in CI.

Canonical implementation + tests: `<workspace>/_shared/slack_blocks/`. If the ceilings
change, that is the copy to fix first; this one is a follower.

Ceilings are Slack's documented Block Kit limits as of 2026-08.
"""
from __future__ import annotations

MAX_BLOCKS = 50
MAX_SECTION_CHARS = 3000
MAX_HEADER_CHARS = 150
MAX_CONTEXT_ELEMENTS = 10


def problems(blocks: list[dict]) -> list[str]:
    """Every Block Kit ceiling this payload breaks. Empty list == fine.

    Returns rather than raises: the caller's job is to deliver the release, and a
    named failure is worth more than an exception that stops the post.
    """
    out: list[str] = []
    if not isinstance(blocks, list) or not blocks:
        return ["payload is empty or not a list"]
    if len(blocks) > MAX_BLOCKS:
        out.append(f"{len(blocks)} blocks exceeds Slack's limit of {MAX_BLOCKS} per message")
    for i, b in enumerate(blocks):
        if not isinstance(b, dict):
            out.append(f"block {i}: not a dict")
            continue
        t = b.get("type")
        if t == "section":
            txt = (b.get("text") or {}).get("text", "")
            if len(txt) > MAX_SECTION_CHARS:
                out.append(f"block {i} (section): {len(txt)} chars exceeds {MAX_SECTION_CHARS}")
            if not txt.strip() and not (b.get("fields") or []):
                out.append(f"block {i} (section): empty text and no fields")
        elif t == "context":
            els = b.get("elements")
            if not els:
                # Slack rejects the WHOLE message for this one.
                out.append(f"block {i} (context): missing or empty elements[]")
            elif len(els) > MAX_CONTEXT_ELEMENTS:
                out.append(f"block {i} (context): {len(els)} elements exceeds "
                           f"{MAX_CONTEXT_ELEMENTS}")
        elif t == "header":
            txt = (b.get("text") or {}).get("text", "")
            if len(txt) > MAX_HEADER_CHARS:
                out.append(f"block {i} (header): {len(txt)} chars exceeds {MAX_HEADER_CHARS}")
    return out


def chunk(blocks: list[dict], *, max_blocks: int = MAX_BLOCKS) -> list[list[dict]]:
    """Split into postable messages, preferring a divider as the seam.

    SPLITS, never truncates: the limit is per message, so a continuation loses
    nothing, whereas a shortened payload silently drops release components. The seam
    search floor is the halfway point so a divider-sparse payload still advances
    instead of emitting many tiny chunks.
    """
    if not isinstance(blocks, list):
        return [blocks]
    if len(blocks) <= max_blocks:
        return [list(blocks)]
    out: list[list[dict]] = []
    i, n = 0, len(blocks)
    while i < n:
        end = min(i + max_blocks, n)
        if end < n:
            floor = i + max_blocks // 2
            seam = next((j for j in range(end - 1, floor, -1)
                         if isinstance(blocks[j], dict)
                         and blocks[j].get("type") == "divider"), None)
            if seam is not None:
                end = seam + 1
        out.append(blocks[i:end])
        i = end
    return out
