"""Slack publisher — Block Kit messages + files_upload_v2 for charts.

Three operating modes:
  - dry_run=True              → print rendered payload to stderr; no Slack call
  - dry_run=False, no token   → raises (require explicit credentials)
  - dry_run=False, with token → actually post via Slack SDK

Graceful degradation:
  Text post is always sent FIRST and independently of the chart upload.
  If files_upload_v2 fails, we log to #status-reports but the release post
  is already in the channel — never let a chart bug suppress the data.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from ..posts_ledger import PostDecision
from ..release_runner import ReleaseResult


# ---------------------------------------------------------------------------
# Transient-network resilience for webhook POSTs
# ---------------------------------------------------------------------------
# A momentary DNS/network blip (or, on a laptop, WiFi-not-yet-up on wake) can
# kill the first POST to a Slack webhook. Retry-with-backoff rides through it.
# We retry ONLY on transport-level errors (requests.exceptions.RequestException)
# -- a successful-but-bad-status HTTP response is NOT retried; the caller keeps
# its existing handling of the returned response. (2026-06-01.)
_RETRY_BACKOFF = (5, 15, 30)  # seconds to wait BEFORE retry attempts 2..N


def requests_post_with_retry(url, *, attempts=4, label="slack post", **kwargs):
    """``requests.post`` with backoff retry on transient transport errors.

    Re-raises the last ``RequestException`` if every attempt fails, so existing
    callers keep their fallback / return-False behavior on a genuine outage --
    this only adds resilience to momentary blips. A successful response (even a
    non-2xx one) is returned as-is and never retried. The wall-clock sleep is
    skipped under pytest (PYTEST_CURRENT_TEST) so network-error tests stay fast.
    """
    import time

    import requests

    last = None
    for i in range(attempts):
        try:
            return requests.post(url, **kwargs)
        except requests.exceptions.RequestException as e:
            last = e
            if i < attempts - 1:
                delay = _RETRY_BACKOFF[min(i, len(_RETRY_BACKOFF) - 1)]
                print(
                    f"[{label}] attempt {i + 1}/{attempts} failed ({e}); "
                    f"retrying in {delay}s",
                    file=sys.stderr,
                )
                if not os.environ.get("PYTEST_CURRENT_TEST"):
                    time.sleep(delay)
    raise last


@dataclass(frozen=True)
class PublishedRelease:
    """What the publisher returns. Empty fields in dry-run mode."""

    main_ts: str | None
    main_channel: str | None
    thread_ts: list[str]
    text_payload: str
    block_payload: list[dict]
    chart_upload_errors: list[str]


# ---------------------------------------------------------------------------
# Text rendering — used both for Block Kit body and dry-run preview
# ---------------------------------------------------------------------------

def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%" if v < 0 else f"{v:.2f}%"


def _fmt_unsigned_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}%"


def _fmt_transformed(tv, display_unit: str | None = None) -> str:
    """Format a TransformedValue according to its transform + display_unit.

    Examples:
      yoy_pct, value=3.78 → "3.78%"
      mom_chg, value=175, unit="K" → "+175K"
      mom_chg, value=-22, unit="K" → "-22K"
      raw, value=4.2 (UNRATE) → "4.20%"  (we know UNRATE is a percent rate)
      raw, value=10.5 → "10.50"
    """
    if tv.value is None:
        return "—"
    if tv.transform in {"yoy_pct", "mom_pct", "annualized_mom", "qoq_pct_saar"}:
        # always signed for direction clarity
        sign = "+" if tv.value >= 0 else ""
        return f"{sign}{tv.value:.2f}%"
    if tv.transform == "mom_chg":
        sign = "+" if tv.value >= 0 else ""
        if display_unit == "K":
            return f"{sign}{tv.value:,.0f}K"
        if display_unit == "M":
            return f"{sign}{tv.value:,.2f}M"
        return f"{sign}{tv.value:,.1f}"
    # raw — strip unit-aware formatting
    if display_unit == "%":
        return f"{tv.value:.2f}%"
    # Large raw values (typically counts like claims) — strip decimals;
    # smaller raw values (rates, ratios) — keep 2 decimals.
    if abs(tv.value) >= 1000:
        return f"{tv.value:,.0f}"
    return f"{tv.value:,.2f}"


# Map of transform name → the basis label that disambiguates what the
# printed % (or level) actually means to a reader skimming the channel.
# A bare "4.30%" is ambiguous (a YoY rate? a level? a MoM change?); the
# basis label removes that ambiguity. Per-series config can override this
# default via SeriesSpec.basis (e.g. UNRATE is `raw` but should read
# "(level)" rather than the generic raw default).
_BASIS_BY_TRANSFORM = {
    "yoy_pct": "YoY",
    "mom_pct": "MoM",
    "annualized_mom": "ann. rate",
    "mom_chg": "MoM chg",
    "qoq_pct_saar": "QoQ SAAR",
    "raw": "(level)",
}


def basis_label(transform: str, basis: str | None = None) -> str:
    """Return an explicit basis label clarifying WHAT a headline number is.

    Derives a sensible default from the series' `primary_transform`
    (yoy_pct→"YoY", mom_pct→"MoM", raw→"(level)", …). A per-series
    `basis` override (config.SeriesSpec.basis) always wins so a series
    like UNRATE — which is `raw` but is really a proportion — can read
    "(level)" or "rate" instead of the bland default. Unknown transforms
    with no override fall back to the transform name itself rather than
    silently dropping the basis.
    """
    if basis:
        return basis
    return _BASIS_BY_TRANSFORM.get(transform, transform)


def _format_headline_line(h, display_unit: str | None = None) -> str:
    """One-line summary of a headline series.

    Appends an explicit basis label after the primary value so the reader
    knows what the number is (a YoY rate, a level, a MoM change, …) — e.g.
    `Nonfarm payrolls: +172K (+0.32% YoY)` reads the +172K as a MoM change
    and the YoY in the parens, `Unemployment rate: 4.30% (level)` reads the
    rate as a level, not a change.
    """
    primary_str = _fmt_transformed(h.primary, display_unit)
    basis = basis_label(h.primary.transform, getattr(h, "basis", None))
    primary_with_basis = f"{primary_str} {basis}"
    also_parts = []
    for ad in h.also_display:
        label = basis_label(ad.transform)
        also_parts.append(f"{_fmt_transformed(ad, None)} {label}")
    suffix = f" ({', '.join(also_parts)})" if also_parts else ""
    return f"{h.label}: {primary_with_basis}{suffix}"


def _format_prior_line(result: ReleaseResult, headline_units: dict[str, str | None]) -> str | None:
    prior_parts = []
    for h in result.headline:
        if h.prior_primary is not None:
            unit = headline_units.get(h.id)
            prior_parts.append(f"{h.label} {_fmt_transformed(h.prior_primary, unit)}")
    if not prior_parts:
        return None
    return f"Prior: {' · '.join(prior_parts)}"


def _format_trend_lines(result: ReleaseResult) -> list[str]:
    if result.context is None or not result.context.trends:
        return []
    lines = []
    for t in result.context.trends:
        lines.append(f"{t.label}: {_fmt_unsigned_pct(t.value)}")
    if result.context.zscore is not None:
        lines.append(
            f"{result.context.zscore_kind}-z vs {result.context.zscore_lookback_years}y: "
            f"{result.context.zscore:+.2f}σ"
        )
    return lines


def _format_healthcare_components(result: ReleaseResult) -> list[str]:
    """Components + computed series carrying tags=[healthcare] surface as
    differentiated context in the main post. Computed HC totals (the
    sum of NAICS 621+622+623) take precedence over individual sub-cuts."""
    lines = []
    # Computed HC series first — these are the "summary" HC numbers
    for c in result.computed:
        if "healthcare" in c.tags and c.transformed.value is not None:
            lines.append(f"{c.label}: {_fmt_transformed(c.transformed, c.display_unit)}")
    for c in result.components:
        if "healthcare" in c.tags and c.transformed.value is not None:
            lines.append(
                f"  ↳ {c.label}: {_fmt_transformed(c.transformed, c.display_unit)}"
            )
    return lines


def _decision_emoji(decision: PostDecision) -> str:
    return {
        PostDecision.NEW_PERIOD: "🔴",
        PostDecision.REVISED_HEADLINE: "🔁",
        PostDecision.REVISED_COMPONENT_ONLY: "🔁",
        PostDecision.UNCHANGED: "·",
    }[decision]


def _decision_word(decision: PostDecision) -> str:
    return {
        PostDecision.NEW_PERIOD: "RELEASED",
        PostDecision.REVISED_HEADLINE: "REVISED",
        PostDecision.REVISED_COMPONENT_ONLY: "REVISED (components)",
        PostDecision.UNCHANGED: "UNCHANGED",
    }[decision]


def render_release_text(
    result: ReleaseResult,
    decision: PostDecision = PostDecision.NEW_PERIOD,
    agency_pdf_url: str | None = None,
) -> str:
    """Plain-text rendering — used as the fallback `text` field in Block Kit
    AND as the dry-run preview."""
    headline_units = {h.id: h.display_unit for h in result.headline}

    lines: list[str] = []
    lines.append(
        f"{_decision_emoji(decision)} {_decision_word(decision)} — "
        f"{result.family_display_name} {result.period_label}"
    )
    for h in result.headline:
        lines.append(_format_headline_line(h, h.display_unit))

    prior = _format_prior_line(result, headline_units)
    if prior:
        lines.append(prior)

    trend_lines = _format_trend_lines(result)
    if trend_lines:
        lines.append("Trend:")
        for tl in trend_lines:
            lines.append(f"  {tl}")

    hc_lines = _format_healthcare_components(result)
    if hc_lines:
        lines.append("")
        for hl in hc_lines:
            lines.append(hl)

    if agency_pdf_url:
        lines.append(f"📄 {agency_pdf_url}")

    if result.is_stale:
        lines.append(
            f"⚠️ STALE: latest observation {result.latest_observation_period} "
            f"< expected {result.expected_observation_period}"
        )

    if result.from_fallback_cache:
        age = result.cache_age_hours
        age_str = f"{age:.1f}h ago" if age is not None else "unknown age"
        lines.append(
            f"⚠️ FRED unreachable — served from defensive cache "
            f"(last live fetch: {age_str})"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Block Kit
# ---------------------------------------------------------------------------

def build_release_blocks(
    result: ReleaseResult,
    decision: PostDecision = PostDecision.NEW_PERIOD,
    agency_pdf_url: str | None = None,
) -> list[dict]:
    """Compose a Block Kit list for the main release post.

    Headline values + prior in one section; trend lines + z-score in a
    second section; healthcare context (if any) in a third; agency-PDF
    button at the end.
    """
    blocks: list[dict] = []

    # Title
    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": (
                    f"{_decision_emoji(decision)} {_decision_word(decision)} — "
                    f"{result.family_display_name} {result.period_label}"
                ),
                "emoji": True,
            },
        }
    )

    # Headline lines
    headline_units = {h.id: h.display_unit for h in result.headline}
    headline_md = "\n".join(
        f"• {_format_headline_line(h, h.display_unit)}" for h in result.headline
    )
    prior = _format_prior_line(result, headline_units)
    if prior:
        headline_md += f"\n_{prior}_"

    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": headline_md},
        }
    )

    # Trend / context
    trend_lines = _format_trend_lines(result)
    if trend_lines:
        trend_md = "*Trend / context*\n" + "\n".join(f"• {t}" for t in trend_lines)
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": trend_md}}
        )

    # Healthcare context (differentiated angle for our HC-investor user)
    hc_lines = _format_healthcare_components(result)
    if hc_lines:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Healthcare context*\n"
                    + "\n".join(f"• {hl}" for hl in hc_lines),
                },
            }
        )

    # Stale warning
    if result.is_stale:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"⚠️ *STALE*: latest observation `{result.latest_observation_period}` "
                        f"< expected `{result.expected_observation_period}`"
                    ),
                },
            }
        )

    # Fallback-cache warning (FRED was unreachable)
    if result.from_fallback_cache:
        age = result.cache_age_hours
        age_str = f"{age:.1f} hours ago" if age is not None else "unknown age"
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"⚠️ *FRED unreachable* — served from defensive cache "
                        f"(last live fetch: _{age_str}_). Values may be from a prior period."
                    ),
                },
            }
        )

    # Agency PDF button
    if agency_pdf_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "📄 Official release"},
                        "url": agency_pdf_url,
                    }
                ],
            }
        )

    return blocks


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------

class SlackPublisher:
    """Posts a release to #macro and threads follow-ups.

    Mode is controlled by `dry_run`:
      dry_run=True  → no Slack calls; payload printed to stderr
      dry_run=False → requires SLACK_BOT_TOKEN; raises otherwise
    """

    def __init__(
        self,
        *,
        bot_token: str | None = None,
        channel_id: str | None = None,
        status_reports_webhook: str | None = None,
        dry_run: bool = True,
    ):
        self.bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
        self.channel_id = channel_id or os.environ.get("SLACK_MACRO_CHANNEL_ID")
        self.status_reports_webhook = status_reports_webhook or os.environ.get(
            "SLACK_WEBHOOK_STATUS_REPORTS"
        )
        self.dry_run = dry_run

        if not self.dry_run:
            if not self.bot_token:
                raise RuntimeError(
                    "SLACK_BOT_TOKEN required for live post; set it or use dry_run=True"
                )
            if not self.channel_id:
                raise RuntimeError(
                    "SLACK_MACRO_CHANNEL_ID required for live post; set it or use dry_run=True"
                )

    def publish_release(
        self,
        result: ReleaseResult,
        chart_paths: dict[str, Path],
        agency_pdf_url: str | None,
        decision: PostDecision = PostDecision.NEW_PERIOD,
    ) -> PublishedRelease:
        text = render_release_text(result, decision, agency_pdf_url)
        blocks = build_release_blocks(result, decision, agency_pdf_url)

        if self.dry_run:
            return self._dry_run_publish(result, text, blocks, chart_paths)

        return self._live_publish(result, text, blocks, chart_paths)

    # ------------------------------------------------------------------

    def _dry_run_publish(
        self,
        result: ReleaseResult,
        text: str,
        blocks: list[dict],
        chart_paths: dict[str, Path],
    ) -> PublishedRelease:
        print("\n=== SLACK DRY-RUN ===", file=sys.stderr)
        print(f"channel: {self.channel_id or '<unset>'}", file=sys.stderr)
        print("\n--- TEXT FALLBACK ---", file=sys.stderr)
        print(text, file=sys.stderr)
        print("\n--- BLOCK KIT PAYLOAD ---", file=sys.stderr)
        print(json.dumps(blocks, indent=2), file=sys.stderr)
        print("\n--- CHART UPLOADS (would attach) ---", file=sys.stderr)
        for name, p in chart_paths.items():
            tag = "MAIN" if name == "main" else "thread"
            print(f"  [{tag}] {name}: {p}", file=sys.stderr)
        print("=== END DRY-RUN ===\n", file=sys.stderr)

        return PublishedRelease(
            main_ts=None,
            main_channel=self.channel_id,
            thread_ts=[],
            text_payload=text,
            block_payload=blocks,
            chart_upload_errors=[],
        )

    # ------------------------------------------------------------------

    def _live_publish(
        self,
        result: ReleaseResult,
        text: str,
        blocks: list[dict],
        chart_paths: dict[str, Path],
    ) -> PublishedRelease:
        """Live Slack post path. Graceful degradation: text post first,
        then chart upload(s); chart failures don't kill the post."""
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError

        client = WebClient(token=self.bot_token)
        upload_errors: list[str] = []

        # 1. Main text post — this is the critical path. Land it first.
        try:
            main_resp = client.chat_postMessage(
                channel=self.channel_id,
                text=text,
                blocks=blocks,
            )
        except SlackApiError as e:
            self._alert_status_reports(
                f"❌ macro_monitor: chat_postMessage failed for "
                f"{result.family_display_name} {result.period_label}: {e.response.get('error')}"
            )
            raise

        main_ts = main_resp["ts"]
        main_channel = main_resp["channel"]

        # 2. Main chart attached as a reply to the same channel/thread.
        main_chart = chart_paths.get("main")
        if main_chart and main_chart.exists():
            try:
                client.files_upload_v2(
                    channel=main_channel,
                    file=str(main_chart),
                    title=f"{result.family_display_name} {result.period_label} — main chart",
                    thread_ts=main_ts,
                )
            except SlackApiError as e:
                msg = (
                    f"⚠️ files_upload_v2 failed for main chart "
                    f"({result.family_display_name} {result.period_label}): "
                    f"{e.response.get('error')}"
                )
                upload_errors.append(msg)
                self._alert_status_reports(msg)

        # 3. Thread charts (long history, component trends, etc.)
        thread_ts_list: list[str] = []
        for name, path in chart_paths.items():
            if name == "main" or not path.exists():
                continue
            try:
                resp = client.files_upload_v2(
                    channel=main_channel,
                    file=str(path),
                    title=f"{result.family_display_name} {result.period_label} — {name}",
                    thread_ts=main_ts,
                )
                if resp.get("file", {}).get("shares"):
                    thread_ts_list.append(str(resp.get("ts", "")))
            except SlackApiError as e:
                msg = (
                    f"⚠️ files_upload_v2 failed for thread chart {name!r} "
                    f"({result.family_display_name} {result.period_label}): "
                    f"{e.response.get('error')}"
                )
                upload_errors.append(msg)
                self._alert_status_reports(msg)

        return PublishedRelease(
            main_ts=main_ts,
            main_channel=main_channel,
            thread_ts=thread_ts_list,
            text_payload=text,
            block_payload=blocks,
            chart_upload_errors=upload_errors,
        )

    # ------------------------------------------------------------------

    def _alert_status_reports(self, message: str) -> None:
        """Best-effort warning to #status-reports. Never raises."""
        if not self.status_reports_webhook:
            print(f"[status-reports STUB] {message}", file=sys.stderr)
            return
        try:
            # Retry-with-backoff for transient-network resilience.
            requests_post_with_retry(
                self.status_reports_webhook,
                label="status-reports alert",
                json={
                    "blocks": [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": message},
                        }
                    ]
                },
                timeout=5,
            )
        except Exception as e:  # noqa: BLE001 — alert path; we swallow
            print(f"[status-reports alert failed: {e}] {message}", file=sys.stderr)
