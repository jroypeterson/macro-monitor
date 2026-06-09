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

from datetime import date
from pathlib import Path

from .build import _FIGURES_YAML, _load_yaml, build
from .charts import FigureSpec, parse_figures
from .schedule import RELEASE_NAME, SERIES_RELEASE_ID

# The (expensive — deep FRED + yfinance) build is memoized per process+data-day
# so a single poll run posting several AoC-relevant releases rebuilds only once.
_BUILD_CACHE: dict[str, dict[str, Path]] = {}


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
        return []

    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    client = WebClient(token=pub.bot_token)
    comment = (
        f"📈 *Ahead of the Curve* — {len(uploads)} chart(s) updated with the new "
        f"{rname} data:\n" + "\n".join(f"• {f.title}" for f in figs if f.id in posted)
    )
    try:
        client.files_upload_v2(
            channel=channel or pub.channel_id,
            file_uploads=uploads,
            initial_comment=comment,
            thread_ts=thread_ts,
        )
    except SlackApiError as e:
        pub._alert_status_reports(
            f"⚠️ macro_monitor: Ahead-of-the-Curve chart upload failed for "
            f"{rname} ({fig_ids}): {e.response.get('error')}"
        )
        return []
    return posted
