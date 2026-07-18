"""Post the Ahead-of-the-Curve chart(s) tied to a FRED release into #macro.

The Ellis chartpack refreshes its published HTML gallery on every build, but
JP wants the relevant chart to *land in chat* when the data that drives it is
released — not just silently update the page. `cmd_post_release` calls
`post_for_release` right after a family's release post lands; the matching AoC
figures ride in as a single threaded reply under that release (rebuilt with
the new data point on them).

Dedup is free: the caller only reaches this path when the family genuinely
posted new data (the posts ledger gates that), so an AoC chart posts exactly
once per new release, and again on a revision.
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

from .build import _FIGURES_YAML, _load_yaml, build
from .charts import FigureSpec, parse_figures
from .schedule import RELEASE_NAME, SERIES_RELEASE_ID

# The (expensive — deep FRED + yfinance) build is memoized per process+data-day
# so a single poll run posting several AoC-relevant releases rebuilds only once.
_BUILD_CACHE: dict[str, dict[str, Path]] = {}

# Backoff schedule (seconds) for retrying a transient Slack upload failure.
# Mirrors scheduled_jobs_monitor's `_urlopen_retry` pattern.
_RETRY_BACKOFF = (2, 5, 10)

# Slack `files_upload_v2` error codes that are server-side / transient and worth
# retrying. `file_update_failed` is the race that dropped the 3 GDP charts on
# 2026-06-17; the rest are Slack's generic transient/availability codes. Anything
# NOT in this set (e.g. `invalid_auth`, `channel_not_found`) is a permanent error —
# retrying just wastes the backoff window, so we re-raise immediately.
_RETRYABLE_SLACK_ERRORS = frozenset({
    "file_update_failed",
    "fatal_error",
    "internal_error",
    "service_unavailable",
    "ratelimited",
    "rate_limited",
})


def _upload_with_retry(client, *, attempts: int = 4, label: str = "AoC upload", **kwargs):
    """`client.files_upload_v2(**kwargs)` with backoff so a momentary Slack-side
    race (e.g. `file_update_failed`) doesn't drop a chart. Retries only transient
    server errors; permanent client errors re-raise on the first hit. Re-raises the
    last exception if every attempt fails (the caller alerts — never silent)."""
    from slack_sdk.errors import SlackApiError

    last: Exception | None = None
    for i in range(attempts):
        try:
            return client.files_upload_v2(**kwargs)
        except SlackApiError as e:
            err = (e.response.get("error") if e.response else "") or ""
            if err.lower() not in _RETRYABLE_SLACK_ERRORS:
                raise  # permanent — don't burn the backoff window
            last = e
            if i < attempts - 1:
                delay = _RETRY_BACKOFF[min(i, len(_RETRY_BACKOFF) - 1)]
                print(f"  {label} attempt {i+1}/{attempts} failed ({err}); "
                      f"retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
    raise last  # type: ignore[misc]


def figures_for_release(release_id: int) -> list[FigureSpec]:
    """The AoC figures this release *primarily* drives.

    A figure matches on the release that publishes its FIRST (headline) series
    — the main economic line of the chart. Matching on the headline only (not
    every series) keeps each release to the handful of charts it actually
    moves, and stops a two-series figure (e.g. PCE-vs-employment) from posting
    twice — once under each series' release.
    """
    figs, _ = parse_figures(_load_yaml(_FIGURES_YAML))
    return [
        f for f in figs
        if f.series and SERIES_RELEASE_ID.get(f.series[0].fred) == release_id
    ]


def _build_once(key: str) -> dict[str, Path]:
    cached = _BUILD_CACHE.get(key)
    if cached is None:
        _BUILD_CACHE.clear()  # only ever keep the current day's build
        cached = build()
        _BUILD_CACHE[key] = cached
    return cached


def post_for_release(
    release_id: int,
    *,
    thread_ts: str | None = None,
    channel: str | None = None,
    dry_run: bool = False,
    publisher=None,
) -> list[str]:
    """Post the AoC chart(s) tied to `release_id` into #macro, as one threaded
    reply (when `thread_ts` given) carrying every matching figure.

    Returns the list of figure ids posted. Never raises — chart delivery is a
    nicety; an upload failure warns to #status-reports and returns [].
    """
    figs = figures_for_release(release_id)
    if not figs:
        return []
    rname = RELEASE_NAME.get(release_id, "new data")
    fig_ids = [f.id for f in figs]

    if dry_run:
        print(
            f"  [DRY-RUN] would post {len(figs)} Ahead-of-the-Curve chart(s) "
            f"for {rname}: {fig_ids}"
        )
        return fig_ids

    from ..publishers.slack import SlackPublisher

    pub = publisher or SlackPublisher(dry_run=False)
    rendered = _build_once(date.today().isoformat())

    uploads, posted = [], []
    for f in figs:
        png = rendered.get(f.id)
        if png is not None and Path(png).exists():
            uploads.append({"file": str(png), "title": f"Ahead of the Curve — {f.title}"})
            posted.append(f.id)
    if not uploads:
        # H6: figures WERE mapped to this release (figs is non-empty) but none
        # rendered / exist on disk — a silent degradation that used to return
        # [] with no trace. Alarm so the missing charts are visible.
        pub._alert_status_reports(
            f"⚠️ macro_monitor: Ahead-of-the-Curve had {len(figs)} figure(s) "
            f"mapped to {rname} ({fig_ids}) but none rendered — no charts posted."
        )
        return []

    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    client = WebClient(token=pub.bot_token)
    comment = (
        f"📈 *Ahead of the Curve* — {len(uploads)} chart(s) updated with the new "
        f"{rname} data:\n" + "\n".join(f"• {f.title}" for f in figs if f.id in posted)
    )
    # Upload each chart as its own single-file files_upload_v2 call. The multi-file
    # `file_uploads=[...]` form combined with thread_ts + initial_comment returns
    # `file_update_failed` from Slack — only the GDP release produces >1 chart, which
    # is why ONLY GDP failed 2026-06-17 (3 figs). The single-file form is the proven
    # path used everywhere else in the publisher. Summary comment on the first only.
    try:
        for i, up in enumerate(uploads):
            _upload_with_retry(
                client,
                label=f"AoC upload {up['title']!r}",
                channel=channel or pub.channel_id,
                file=up["file"],
                title=up["title"],
                thread_ts=thread_ts,
                initial_comment=comment if i == 0 else None,
            )
    except SlackApiError as e:
        pub._alert_status_reports(
            f"⚠️ macro_monitor: Ahead-of-the-Curve chart upload failed for "
            f"{rname} ({fig_ids}): {e.response.get('error')}"
        )
        return []
    return posted
