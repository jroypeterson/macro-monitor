# macro-monitor
> Macro **and** top-down market data. Core: a disciplined US macro release feed to Slack `#macro-and-markets` (Tier A indicators — CPI, payrolls, PCE, GDP, claims, JOLTS, PPI, ECI, FOMC — within ~1h of publication, with charts + long-history context + HC sub-cuts). Plus a growing top-down market-data layer (below).

**Scope (3 layers):**
1. **Macro releases & cycle** — the release feed + leading-indicator context (the original project).
2. **`ahead_of_curve/`** — Joseph Ellis "Ahead of the Curve" chart recreation (23 figures).
3. **Top-down market data** — `damodaran/` (risk-free, ERP, valuation multiples by market) + `market/` (Ken French factors, AQR factor premia, Shiller CAPE). Mirror/inventory now; charts later.

- **Status:** live
- **Runtime/trigger:** Python via GitHub Actions (release polling every 15 min 11:00–18:59 UTC weekdays; weekly preview Sun 07:00 ET; reconcile Thu 15:30 UTC; heartbeat daily 12:00 UTC)
- **Reads:** FRED API · Gmail research newsletters · RSS feeds · FOMC calendar · NYU Stern (Damodaran) · Ken French / AQR / Shiller data
- **Writes:** Slack `#macro-and-markets` (releases + charts) · `#status-reports` (heartbeat) · Google Calendar (release events) · GitHub Pages HTML · `state/posts.db`
- **Run:** `python -m macro_monitor.cli poll-all --post`  ·  **Entry points:** `macro_monitor/cli.py`, `macro_monitor/release_runner.py`, `macro_monitor/publishers/slack.py`

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

# Dry-run the Sunday week-ahead preview:
python -m macro_monitor.cli weekly-preview --dry-run

# Re-run the releases that landed on a given date (catch-up; dry-run default):
python -m macro_monitor.cli replay-day 2026-05-12 --dry-run
```

## What it produces

See Appendix B of the plan for the full table. Highlights:

| Surface | Output |
|---|---|
| Slack `#macro` | Sunday week-ahead preview (this week + next 4 weeks); per-release main post with chart; threaded long-history + components + HC employment subplots; REVISED posts on revision; annual benchmark summary; quarterly Annual Macro Calendar HTML |
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
  weekly_preview.yml       Sunday 07:00 ET (this week + next 4 weeks)
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
