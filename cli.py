"""macro_monitor CLI.

Manual entry points per feedback_manual_test_entrypoints. Every command
that touches Slack defaults to --dry-run and requires explicit --post
to actually send.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import __version__
from .config import default_config_path, load_config, validate_all_or_raise

# Load .env from the macro_monitor package directory at import time so
# every CLI invocation picks up FRED_API_KEY / SLACK_* without each
# command having to remember.
load_dotenv(Path(__file__).parent / ".env")


def cmd_validate_config(args: argparse.Namespace) -> int:
    path = Path(args.config) if args.config else default_config_path()
    try:
        families = load_config(path)
    except Exception as exc:
        print(f"ERROR loading {path}:\n  {exc}", file=sys.stderr)
        return 2

    print(f"Loaded {len(families)} family/families from {path}:")
    for fid, fam in families.items():
        print(f"  - {fid} ({fam.display_name}, tier {fam.tier}, {fam.family_type})")

    try:
        validate_all_or_raise(families)
    except ValueError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1

    print("\nAll families pass validation.")
    return 0


def cmd_post_release(args: argparse.Namespace) -> int:
    """Phase 1a: fetch data, render charts, write JSON+HTML.
    Slack publisher wiring lands when the bot token is set.
    """
    path = Path(args.config) if args.config else default_config_path()
    families = load_config(path)
    validate_all_or_raise(families)

    if args.family not in families:
        print(
            f"Unknown family {args.family!r}. Known: {list(families)}",
            file=sys.stderr,
        )
        return 2
    family = families[args.family]

    # Lazy imports — keep `validate-config` fast.
    from .charts.timeseries import render_family_charts
    from .collectors.fred import FREDClient
    from .outputs import outputs_root, write_release_artifacts
    from .release_runner import compute_release

    client = FREDClient()
    print(f"Fetching {family.display_name} from FRED…", file=sys.stderr)
    result = compute_release(family, client)

    print(f"  period: {result.period_label} ({result.period})")
    print(f"  stale: {result.is_stale} (latest={result.latest_observation_period}, expected={result.expected_observation_period})")

    if family.charts is None:
        print(f"  no charts configured", file=sys.stderr)
        chart_paths: dict[str, Path] = {}
    else:
        from .computed import compute_series
        from .release_runner import _fetch_series, parse_period_key

        target_period = parse_period_key(result.period, family.cadence)

        # Refetch real FRED series for chart rendering. The release_runner
        # did a one-shot pull but didn't return them; for v1 we refetch.
        real_ids = [s.id for s in family.headline] + [s.id for s in family.components]
        fetched = {sid: _fetch_series(client, sid, lookback_years=30) for sid in real_ids}

        # Re-derive computed series so charts can reference them by their
        # synthetic IDs (e.g. HC_TOTAL).
        for cs in family.computed:
            fetched[cs.id] = compute_series(
                cs.method, {iid: fetched[iid] for iid in cs.inputs}, cs.id
            )

        charts_dir = outputs_root() / "charts"
        chart_paths = render_family_charts(
            family_charts=family.charts,
            fetched_series=fetched,
            target_period=target_period,
            period_key=result.period,
            output_dir=charts_dir,
            family_display_name=family.display_name,
            period_label=result.period_label,
        )
        print(f"  rendered {len(chart_paths)} chart(s):")
        for name, p in chart_paths.items():
            print(f"    {name}: {p.relative_to(Path(__file__).parent)}")

    agency_pdf = family.agency.pdf_url_static
    json_path, html_path = write_release_artifacts(
        result=result, chart_paths=chart_paths, agency_pdf_url=agency_pdf
    )
    print(f"  json: {json_path.relative_to(Path(__file__).parent)}")
    print(f"  html: {html_path.relative_to(Path(__file__).parent)}")

    # === Posts-ledger READ-ONLY diff check (no write yet) ===
    from .posts_ledger import PostDecision, PostsLedger
    from .publishers.slack import SlackPublisher

    family_id = args.family  # caller uses config key
    headline_values = {h.id: h.primary.value for h in result.headline}
    component_values = {c.id: c.transformed.value for c in result.components}

    with PostsLedger() as ledger:
        diff = ledger.compute_diff(
            family_id=family_id,
            period=result.period,
            headline_values=headline_values,
            component_values=component_values,
        )

        print(f"  ledger decision: {diff.decision.value} "
              f"(revision_count={diff.revision_count})")

        if diff.decision == PostDecision.UNCHANGED:
            print(
                "  No new data since last post; skipping Slack publish.",
                file=sys.stderr,
            )
            return 0

        # === Slack publish (dry-run by default) ===
        publisher = SlackPublisher(dry_run=args.dry_run)
        published = publisher.publish_release(
            result=result,
            chart_paths=chart_paths,
            agency_pdf_url=agency_pdf,
            decision=diff.decision,
        )

        if args.dry_run:
            print(
                "\n  [DRY-RUN] artifacts written; Slack payload printed above.\n"
                "  Ledger NOT updated (dry-runs are read-only).\n"
                "  Use --post to actually publish.",
                file=sys.stderr,
            )
            return 0

        # === Live post succeeded — record to ledger (with slack_ts) ===
        ledger.record_post(
            family_id=family_id,
            period=result.period,
            headline_values=headline_values,
            component_values=component_values,
            slack_channel=published.main_channel,
            slack_ts=published.main_ts,
        )

        print(
            f"\n  Posted to Slack: channel={published.main_channel} ts={published.main_ts}",
            file=sys.stderr,
        )
        if published.chart_upload_errors:
            print(
                f"  {len(published.chart_upload_errors)} chart upload error(s) "
                f"— text post landed; charts may be missing.",
                file=sys.stderr,
            )

    return 0


def cmd_weekly_preview(args: argparse.Namespace) -> int:
    """Build + post the Monday weekly preview (this week + next 4 weeks)."""
    path = Path(args.config) if args.config else default_config_path()
    families = load_config(path)
    validate_all_or_raise(families)

    from .collectors.fred import FREDClient
    from .publishers.slack import SlackPublisher
    from .schedulers.weekly_preview import build_preview_payload_with_failures

    client = FREDClient()
    print("Fetching release calendars from FRED…", file=sys.stderr)
    text, blocks, failed = build_preview_payload_with_failures(
        families=families, client=client
    )

    if failed:
        print(f"\n⚠️ {len(failed)} family/families' FRED fetch failed:", file=sys.stderr)
        for f in failed:
            print(f"   {f.split(':')[0]}", file=sys.stderr)

    if args.dry_run:
        print("\n=== WEEKLY PREVIEW (DRY-RUN) ===", file=sys.stderr)
        print("\n--- TEXT FALLBACK ---", file=sys.stderr)
        print(text, file=sys.stderr)
        print("\n--- BLOCK COUNT ---", file=sys.stderr)
        print(f"{len(blocks)} blocks", file=sys.stderr)
        print("\n=== END DRY-RUN ===\n", file=sys.stderr)
        return 0

    # Live post
    publisher = SlackPublisher(dry_run=False)
    from slack_sdk import WebClient

    client_slack = WebClient(token=publisher.bot_token)
    resp = client_slack.chat_postMessage(
        channel=publisher.channel_id, text=text, blocks=blocks
    )
    print(
        f"Posted weekly preview to {resp['channel']} ts={resp['ts']}",
        file=sys.stderr,
    )

    # Surface FRED failures to #status-reports
    if failed and publisher.status_reports_webhook:
        publisher._alert_status_reports(
            f"weekly-preview: {len(failed)} family/families' FRED calendar failed:\n"
            + "\n".join(f"  • {f}" for f in failed)
        )

    return 0


def cmd_replay_day(args: argparse.Namespace) -> int:
    print(
        f"[replay-day {args.date}] not yet implemented (Phase 1a in progress). "
        f"Will re-run any releases that landed on {args.date} as if it were "
        f"the original release morning.",
        file=sys.stderr,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="macro_monitor", description="Macro Monitor CLI")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--config",
        help="Path to release_families.yaml (default: macro_monitor/config/release_families.yaml)",
    )

    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("validate-config", help="Load and validate release_families.yaml")
    sp.set_defaults(func=cmd_validate_config)

    sp = sub.add_parser("post-release", help="Post a release to #macro (defaults to dry-run)")
    sp.add_argument("--family", required=True, help="Family id (e.g. cpi)")
    sp.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Don't actually post to Slack (default)",
    )
    sp.add_argument(
        "--post", action="store_false", dest="dry_run", help="Actually post to Slack"
    )
    sp.set_defaults(func=cmd_post_release)

    sp = sub.add_parser("weekly-preview", help="Post the Monday weekly preview")
    sp.add_argument("--dry-run", action="store_true", default=True)
    sp.add_argument("--post", action="store_false", dest="dry_run")
    sp.set_defaults(func=cmd_weekly_preview)

    sp = sub.add_parser("replay-day", help="Replay all releases for a given date")
    sp.add_argument("date", help="YYYY-MM-DD")
    sp.add_argument("--dry-run", action="store_true", default=True)
    sp.add_argument("--post", action="store_false", dest="dry_run")
    sp.set_defaults(func=cmd_replay_day)

    sp = sub.add_parser(
        "backfill-calendar",
        help="Push the next 90 days of Tier A releases into Google Calendar",
    )
    sp.add_argument(
        "--days", type=int, default=90, help="Lookahead window in days"
    )
    sp.add_argument("--dry-run", action="store_true", default=True)
    sp.add_argument("--post", action="store_false", dest="dry_run")
    sp.set_defaults(func=cmd_backfill_calendar)

    sp = sub.add_parser(
        "annual-calendar",
        help="Render the annual macro calendar HTML and (optionally) post to #macro",
    )
    sp.add_argument(
        "--year", type=int, default=None, help="Year (defaults to current year)"
    )
    sp.add_argument("--dry-run", action="store_true", default=True)
    sp.add_argument("--post", action="store_false", dest="dry_run")
    sp.set_defaults(func=cmd_annual_calendar)

    sp = sub.add_parser(
        "poll-all",
        help=(
            "Iterate through every numeric Tier A family and post any new "
            "release data. Idempotent via the posts ledger. This is what "
            "the GitHub Actions */15 cron runs."
        ),
    )
    sp.add_argument(
        "--tier",
        default="A",
        choices=["A", "B"],
        help="Tier to poll (default A)",
    )
    sp.add_argument("--dry-run", action="store_true", default=True)
    sp.add_argument("--post", action="store_false", dest="dry_run")
    sp.add_argument(
        "--skip-window-check",
        action="store_true",
        help=(
            "By default poll-all skips outside the 8:25–11:00 ET window "
            "(plus 13:55–14:35 for FOMC). Override for manual testing."
        ),
    )
    sp.set_defaults(func=cmd_poll_all)

    sp = sub.add_parser(
        "heartbeat",
        help="Post a daily 'UP' heartbeat to #status-reports via webhook",
    )
    sp.add_argument("--dry-run", action="store_true", default=True)
    sp.add_argument("--post", action="store_false", dest="dry_run")
    sp.set_defaults(func=cmd_heartbeat)

    sp = sub.add_parser(
        "render-dashboard",
        help="Render outputs/dashboard/index.html from existing artifacts (Phase 1.5)",
    )
    sp.set_defaults(func=cmd_render_dashboard)

    sp = sub.add_parser(
        "overview",
        help="Post the channel overview (pinnable 'what this channel is' message) to #macro",
    )
    sp.add_argument("--dry-run", action="store_true", default=True)
    sp.add_argument("--post", action="store_false", dest="dry_run")
    sp.set_defaults(func=cmd_overview)

    return p


def cmd_overview(args: argparse.Namespace) -> int:
    """Post the channel-overview reference card to #macro. Designed to be
    pinned. Regenerate + re-pin when the family list changes."""
    path = Path(args.config) if args.config else default_config_path()
    families = load_config(path)

    from .publishers.overview import build_overview_blocks

    text, blocks = build_overview_blocks(families)

    if args.dry_run:
        import json as _json

        print("=== CHANNEL OVERVIEW (DRY-RUN) ===")
        print("\n--- TEXT FALLBACK ---")
        print(text)
        print(f"\n--- {len(blocks)} BLOCK KIT BLOCKS ---")
        for b in blocks:
            t = b.get("type")
            if t == "section":
                preview = b["text"]["text"].split("\n")[0][:80]
                print(f"  section: {preview}…")
            elif t == "header":
                print(f"  header:  {b['text']['text']}")
            elif t == "divider":
                print("  divider")
            elif t == "context":
                print(f"  context: {b['elements'][0]['text'][:60]}…")
        print("\n  Use --post to publish to #macro.", file=sys.stderr)
        return 0

    import os

    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    channel_id = os.environ.get("SLACK_MACRO_CHANNEL_ID")
    if not bot_token or not channel_id:
        print("  SLACK_BOT_TOKEN + SLACK_MACRO_CHANNEL_ID required for --post", file=sys.stderr)
        return 2

    client = WebClient(token=bot_token)
    try:
        resp = client.chat_postMessage(channel=channel_id, text=text, blocks=blocks)
        print(f"  Posted overview to {resp['channel']} ts={resp['ts']}", file=sys.stderr)
        print(
            f"  Now: open #macro in Slack, click ⋯ on this message, "
            f"choose 'Pin to channel'.",
            file=sys.stderr,
        )
    except SlackApiError as e:
        print(f"  ⚠️ Post failed: {e.response.get('error')}", file=sys.stderr)
        return 1
    return 0


def cmd_render_dashboard(args: argparse.Namespace) -> int:
    """Render the static current-state dashboard from existing artifacts.

    Reads outputs/latest/*.json + outputs/charts/*.png — no FRED fetches.
    This is the "dashboard escape hatch" the architecture has promised
    since v3, finally realized as a real static artifact.
    """
    path = Path(args.config) if args.config else default_config_path()
    families = load_config(path)

    from .charts.dashboard import render_dashboard

    rendered = render_dashboard(families)
    rel = rendered.relative_to(Path(__file__).parent)
    print(f"Rendered dashboard to {rel}")
    print(f"  Open in browser: file://{rendered.absolute()}")
    return 0


def cmd_poll_all(args: argparse.Namespace) -> int:
    """Master polling entry point — run every 15 min by GitHub Actions cron.
    Iterates every numeric Tier A family, runs the same `post-release`
    path the manual command uses. Idempotent via the posts ledger.
    """
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    ET = ZoneInfo("America/New_York")

    # Window check (skippable via --skip-window-check)
    if not args.skip_window_check:
        now_et = datetime.now(ET)
        weekday = now_et.weekday()  # Mon=0..Sun=6
        t = now_et.time()
        # Tier A 8:30 ET releases — fetch from 8:25 to 11:00 ET
        morning_window = time(8, 25) <= t <= time(11, 0)
        # FOMC 14:00 ET — 13:55 to 14:35
        fomc_window = time(13, 55) <= t <= time(14, 35)
        if weekday >= 5 or not (morning_window or fomc_window):
            print(
                f"  Outside polling window (now={now_et.strftime('%a %H:%M ET')}); "
                f"exit clean.",
                file=sys.stderr,
            )
            return 0

    path = Path(args.config) if args.config else default_config_path()
    families = load_config(path)
    validate_all_or_raise(families)

    targets = {
        fid: f for fid, f in families.items()
        if f.tier == args.tier and f.family_type == "numeric"
    }
    print(f"Polling {len(targets)} {args.tier}-tier numeric families…", file=sys.stderr)

    posted_count = 0
    skipped_unchanged = 0
    errors: list[str] = []

    for family_id in targets:
        try:
            sub_args = argparse.Namespace(
                family=family_id,
                dry_run=args.dry_run,
                config=args.config,
            )
            print(f"  → {family_id}", file=sys.stderr)
            rc = cmd_post_release(sub_args)
            if rc != 0:
                errors.append(f"{family_id}: rc={rc}")
            # Detection of "actually posted" vs "unchanged" is implicit —
            # cmd_post_release prints the ledger decision; we count by
            # re-reading it below.
        except Exception as e:  # noqa: BLE001
            errors.append(f"{family_id}: {type(e).__name__}: {e}")

    print(
        f"\npoll-all complete. errors={len(errors)}",
        file=sys.stderr,
    )
    for err in errors[:10]:
        print(f"  ⚠️ {err}", file=sys.stderr)
    return 0 if not errors else 1


def cmd_heartbeat(args: argparse.Namespace) -> int:
    """Post the daily Tier B heartbeat to #status-reports."""
    path = Path(args.config) if args.config else default_config_path()
    families = load_config(path)

    from .schedulers.heartbeat import (
        build_heartbeat_blocks,
        collect_state,
        send_heartbeat,
    )

    state = collect_state(families)
    text, blocks = build_heartbeat_blocks(state)

    print("=== HEARTBEAT ===")
    print(text)
    print()

    if args.dry_run:
        print(
            "  [DRY-RUN] webhook post skipped. Use --post to send to #status-reports.",
            file=sys.stderr,
        )
        return 0

    ok, msg = send_heartbeat(blocks, text)
    if ok:
        print(f"  Posted to #status-reports: {msg}", file=sys.stderr)
        return 0
    print(f"  ⚠️ Failed: {msg}", file=sys.stderr)
    return 1


def cmd_backfill_calendar(args: argparse.Namespace) -> int:
    """Push Tier A release events into the Google Calendar."""
    from datetime import date, timedelta

    path = Path(args.config) if args.config else default_config_path()
    families = load_config(path)
    validate_all_or_raise(families)

    from .collectors.fred import FREDClient
    from .publishers.google_calendar import (
        GoogleCalendarPublisher,
        build_events_from_schedule,
    )
    from .schedulers.weekly_preview import fetch_scheduled_releases

    client = FREDClient()
    today = date.today()
    end = today + timedelta(days=args.days)

    print(f"Fetching {args.days}-day release calendar from FRED…", file=sys.stderr)
    scheduled, failed = fetch_scheduled_releases(
        families=families, client=client, start=today, end=end
    )
    print(f"  {len(scheduled)} release events found")
    if failed:
        print(f"  ⚠️ {len(failed)} family/families' FRED fetch failed:", file=sys.stderr)
        for f in failed:
            print(f"      {f.split(':')[0]}", file=sys.stderr)

    events = build_events_from_schedule(families, scheduled)
    publisher = GoogleCalendarPublisher(dry_run=args.dry_run)

    if args.dry_run:
        print("\n=== CALENDAR BACKFILL (DRY-RUN) ===", file=sys.stderr)
        for ev in events:
            print(
                f"  {ev.release_date} {ev.release_time_et} ET — {ev.display_name} "
                f"(id={ev.google_event_id[:14]}…)",
                file=sys.stderr,
            )
        print(f"\n  {len(events)} events would be upserted to {publisher.calendar_id}")
        print("  Use --post to actually publish.", file=sys.stderr)
        return 0

    print(f"Upserting {len(events)} events into Google Calendar…", file=sys.stderr)
    counts = publisher.upsert_events(events)
    print(
        f"  created={counts['created']} updated={counts['updated']} "
        f"errors={len(counts['errors'])}",
        file=sys.stderr,
    )
    for err in counts["errors"][:10]:
        print(f"    ⚠️ {err}", file=sys.stderr)
    return 0


def cmd_annual_calendar(args: argparse.Namespace) -> int:
    """Render the annual macro calendar HTML and (optionally) upload to #macro."""
    from datetime import date

    path = Path(args.config) if args.config else default_config_path()
    families = load_config(path)
    validate_all_or_raise(families)

    from .charts.annual_calendar import render_annual_calendar
    from .collectors.fred import FREDClient

    year = args.year if args.year else date.today().year
    client = FREDClient()
    output_dir = Path(__file__).parent / "outputs" / "calendar"
    output_path = output_dir / f"{year}_macro_calendar.html"

    print(f"Rendering {year} annual macro calendar…", file=sys.stderr)
    rendered = render_annual_calendar(
        families=families, client=client, year=year, output_path=output_path
    )
    print(f"  wrote {rendered.relative_to(Path(__file__).parent)}")

    if args.dry_run:
        print(
            "\n  [DRY-RUN] HTML written; Slack upload skipped. Open the file "
            "in a browser to view.\n  Use --post to also upload to #macro.",
            file=sys.stderr,
        )
        return 0

    # Upload to #macro
    import os

    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    channel_id = os.environ.get("SLACK_MACRO_CHANNEL_ID")
    if not bot_token or not channel_id:
        print("  SLACK_BOT_TOKEN + SLACK_MACRO_CHANNEL_ID required for --post", file=sys.stderr)
        return 2

    client_slack = WebClient(token=bot_token)
    try:
        client_slack.files_upload_v2(
            channel=channel_id,
            file=str(rendered),
            title=f"{year} Macro Calendar",
            initial_comment=f"📅 {year} Macro Calendar — double-click to open in browser.",
        )
        print("  Uploaded to #macro as file attachment.", file=sys.stderr)
    except SlackApiError as e:
        print(f"  ⚠️ Upload failed: {e.response.get('error')}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
