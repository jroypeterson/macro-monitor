# macro-monitor

Disciplined US macro data feed for `#macro` Slack channel. Posts Tier A
releases (CPI, payrolls, PCE, GDP, claims, JOLTS, PPI, ECI, FOMC) within
~1 hour of agency publication with a 5y chart, threaded long-history
context, and HC-investor-specific sub-cuts (healthcare employment, medical
care CPI).

**Spec:** see [`MACRO_MONITOR_PLAN.md`](../MACRO_MONITOR_PLAN.md) in the
parent directory.

## Setup

```bash
cp .env.example .env
# Fill in FRED_API_KEY, SLACK_BOT_TOKEN, SLACK_MACRO_CHANNEL_ID,
# SLACK_WEBHOOK_STATUS_REPORTS — see .env.example for sources.

python -m pip install -r requirements.txt

# Validate config:
python -m macro_monitor.cli validate-config

# Dry-run a release post against the most recent CPI period:
python -m macro_monitor.cli post-release --family cpi --dry-run

# Dry-run a Monday weekly preview:
python -m macro_monitor.cli weekly-preview --dry-run

# Replay a specific date end-to-end (no Slack post unless --post):
python -m macro_monitor.cli replay-day 2026-05-15 --dry-run
```

## What it produces

See Appendix B of the plan for the full table. Highlights:

| Surface | Output |
|---|---|
| Slack `#macro` | Monday preview (this week + next 4 weeks); per-release main post with chart; threaded long-history + components + HC employment subplots; REVISED posts on revision; annual benchmark summary; quarterly Annual Macro Calendar HTML |
| Slack `#status-reports` | Daily Tier B heartbeat; operator alerts on failure |
| Google Calendar (`floridabusinessman@gmail.com`) | Tier A release events on the dedicated "Macro Calendar" (shared earnings-agent service account; no user OAuth) |
| Local: `outputs/archive/<family>/<period>.{json,html}` | Per-period structured snapshot + browsable HTML report |
| Local: `outputs/dashboard/index.html` (Phase 1.5) | Static "current state" page, regenerated each release |
| Local: `outputs/calendar/<year>_macro_calendar.html` | Annual schedule grid |
| Local: `pdfs/` (gitignored) | Best-effort agency-source PDF mirror |

## Phasing

- **1a** ✅ CPI end-to-end
- **1b** ✅ Payrolls + `computed:` engine (sum_of, yoy_pct_of_sum, annualized_mom) + multi-pane HC employment subplots
- **1c** ✅ PCE, claims (weekly cadence), GDP (quarterly cadence)
- **1d** ✅ JOLTS, PPI, retail sales, ECI
- **1e** FOMC + minutes (`family_type: event` — separate parser, no FRED data series)
- **1f** ✅ Weekly preview + annual calendar HTML + Google Calendar backfill + `#status-reports` heartbeat + GitHub Actions cron
- **1.5** Static dashboard + consensus enrichment
- **2** Deeper HC + Fed research RSS
- **3** Earnings-transcript macro commentary

## GitHub Actions secrets

When pushing to `jroypeterson/macro-monitor`, add these repo secrets at
`Settings → Secrets and variables → Actions → New repository secret`:

| Secret | Used by |
|---|---|
| `FRED_API_KEY` | All FRED fetches |
| `SLACK_BOT_TOKEN` | `release_polling`, `weekly_preview`, `annual_calendar` (file uploads need bot) |
| `SLACK_MACRO_CHANNEL_ID` | All `#macro` posts |
| `SLACK_WEBHOOK_STATUS_REPORTS` | `heartbeat`, operator alerts |
| `GOOGLE_CALENDAR_ID` | `calendar_backfill` (the Macro Calendar in floridabusinessman@gmail.com) |
| `GOOGLE_CREDENTIALS_JSON` | `calendar_backfill` — paste the full `credentials.json` content; the workflow writes it to disk per run |

## Workflows

```
.github/workflows/
  release_polling.yml      */15 11-18 UTC Mon-Fri (covers ET morning + 14:00 FOMC)
  weekly_preview.yml       Monday 07:00 ET (this week + next 4 weeks)
  heartbeat.yml            Daily 08:00 ET to #status-reports
  annual_calendar.yml      Jan 1 + Apr/Jul/Oct 1 (quarterly refresh)
  calendar_backfill.yml    Sunday 21:00 ET — rolling 90-day Google Calendar push
  reconciliation.yml       Daily 17:00 ET — catch-up poll, surface stale series
```

All workflows are idempotent. `release_polling` and `reconciliation` commit
`state/posts.db` back to the repo so the ledger survives across runs —
without persistence every run would think it was the first time and
re-post everything.

## License

Private. No license file by design.
