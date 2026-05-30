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
# NOTE: replay-day is not yet implemented (stub) — see TODO.md.
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
- **1e** FOMC + minutes (`family_type: event` — event scaffolding shipped; parser **manual until a meeting tests it**)
- **1f** ✅ Weekly preview + annual calendar HTML + Google Calendar backfill + `#status-reports` heartbeat + GitHub Actions cron
- **1.5** Static dashboard ✅ (renders on every post) · consensus enrichment **pending** (needs a consensus data source)
- **2a** ✅ Fed research RSS digest (NBER, Liberty Street, SF/St Louis Fed, FEDS, Conversable Economist)
- **2b** ✅ Macro-focus keyword filters + mainstream feeds (NYT/FT/Bloomberg/WSJ/Economist) + Gmail senders (Torsten Slok / Yardeni / Economist Today) + multi-account Gmail (jroypeterson + floridabusinessman)
- **2c** ✅ Haiku 4.5 read-worthiness scorer + macro classifier + curated top picks + table of contents + per-source staleness probe
- **2 deeper HC subsector** ✅ CPI medical breakdown (commodities / hospital & related / professional services alongside medical-care-services) + PPI HC cuts (hospitals, physician offices, pharma mfg, surgical & medical instruments), each with a dedicated thread chart + Healthcare-context lines
- **3** Earnings-transcript macro commentary

### Daily research digest

```bash
# Dry-run the daily Fed/macro research digest (scores items, shows what'd post):
python -m macro_monitor.cli research-digest --dry-run

# Live-fire to #macro (ledger updates so re-runs don't repost):
python -m macro_monitor.cli research-digest --post

# Scan a Gmail inbox for new high-signal sender candidates:
python -m macro_monitor.cli suggest-research-senders --days 90 --account floridabusinessman

# Authorize a new Gmail account (token lands in Dropbox/API Keys/):
python -m macro_monitor.cli authorize-gmail --account <short-name>
```

Each item is batch-scored by Haiku 4.5 with `is_macro` (drops the
keyword filter's misses — TV reviews, philosophy essays, geopolitics
without econ angle) and a 1–10 read-worthiness score. The post opens
with a curated top-picks section (score ≥7, capped at 7), then a
table-of-contents listing every source with item counts, then the
full grouped-by-source digest sorted high→low by score. Cost ~$0.005/run.

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
| `ANTHROPIC_API_KEY` | `research_digest` — Haiku 4.5 read-worthiness scorer |
| `GMAIL_TOKEN_JSON` | `research_digest` — default-account (jroypeterson) Gmail OAuth token |
| `GMAIL_TOKEN_FLORIDABUSINESSMAN` | `research_digest` — floridabusinessman@gmail.com Gmail OAuth token |

## Workflows

```
.github/workflows/
  release_polling.yml      */15 11-18 UTC Mon-Fri (covers ET morning + 14:00 FOMC)
  weekly_preview.yml       Monday 07:00 ET (this week + next 4 weeks)
  heartbeat.yml            Daily 08:00 ET to #status-reports
  annual_calendar.yml      Jan 1 + Apr/Jul/Oct 1 (quarterly refresh)
  calendar_backfill.yml    Sunday 21:00 ET — rolling 90-day Google Calendar push
  reconciliation.yml       Daily 17:00 ET — catch-up poll, surface stale series
  research_digest.yml      Daily 08:30 ET — Fed/macro research RSS + Gmail digest
```

All workflows are idempotent. `release_polling`, `reconciliation`, and
`research_digest` commit their state DBs back to the repo so ledgers
survive across runs — without persistence every run would think it was
the first time and re-post everything.

## License

Private. No license file by design.
