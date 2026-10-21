# Project Brief — read this first (for reviewers, human or AI)

> **Staleness -- check before trusting any figure below.** This file is not auto-updated:
> `python ../scripts/audit_project_briefs.py --repo "macro_monitor"` counts the behaviour-changing
> commits landed since it was last touched. Section 3 rationale and section 4 non-goals age
> well; section 2 status, and every count, version, path and line number here, is a
> **hypothesis** until checked against the code -- and a disagreement between this file and
> the repo is a defect worth reporting, not a documentation nit.
> Last reconciled against the code 2026-10-20 (board #319), through `a8e09e9`.

This file exists so a reviewer can (1) judge how close the project is to its
intended goal and (2) understand the key design decisions **before** giving
feedback. For mechanics — CLI verbs, workflows, secrets, the full output
table — see `README.md`; for the forward backlog see `TODO.md`. This brief
does **not** restate those.

> When reviewing, weigh findings against the **success criteria** (§2) and the
> **non-goals / accepted tradeoffs** (§4). Several "obvious improvements"
> (more FRED retries, a consensus gate, a market caching layer) were
> considered and deliberately deferred or declined with reasons. Say so if you
> think a declined option is worth it, but engage the stated rationale.

---

## 1. Intended goal (the "why")

Give the owner — a solo, part-time, healthcare-focused investor automating
"signal from noise" — a **disciplined, low-effort feed of macro and top-down
market data** so the macro layer of his process runs without him babysitting
it. Concretely, three things he should *not* have to do by hand:

1. **Catch every Tier-A US macro release** (CPI, payrolls, PCE, GDP, claims,
   JOLTS, PPI, ECI, FOMC) within ~1h of agency publication, with a chart,
   long-history context, and **healthcare-specific sub-cuts** (medical-care
   CPI, HC employment, HC producer prices) — the cuts a generic macro feed
   never gives him.
2. **Triage the macro reading firehose** — Fed research, mainstream macro
   press, and a few high-signal newsletters — into one scored daily digest
   instead of a dozen inboxes/feeds.
3. **Keep the top-down "where are we in the cycle / how expensive is the
   market" reference data** (valuation multiples, factor premia, CAPE, the
   Joseph Ellis leading-indicator chartpack) **mirrored, current, and
   chart-ready** in one place he controls, rather than re-pulling from NYU
   Stern / Ken French / multpl each time he wants to check.

Success is not "a dashboard exists" — it's that the owner can glance at
`#macro-and-markets` (and the published hub) and trust he hasn't missed a
release or a regime signal, with the HC angle already done.

## 2. Success criteria — and current status

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Tier-A US releases post to Slack within ~1h, with chart + long-history thread | 🟨 Posts reliably; **~1h is not achievable on GitHub cron** | `release_polling.yml` cron `*/15 11-18 * * 1-5` UTC; `release_runner.py` + `publishers/slack.py`; CPI/payrolls/PCE/GDP/claims/JOLTS/PPI/ECI live. GitHub creates this account's scheduled runs 3–4h late and drops most (1–3 of 32 weekday fires, 2026-08-27..09-17; `plans/missed_releases_diagnosis_2026-09-17.md`), and the old ET wall-clock gate made late runs exit green having posted nothing (Retail Sales, Industrial Production, Claims and the FOMC decision missed 2026-09-16/17). Fixed 2026-09-21 (merge `72d78a6`): every run polls with no ET gate, and `state/posts.db` ("owed and unposted") is the idempotency key, so a late run catches up instead of skipping. Lateness itself remains |
| 2 | HC-investor sub-cuts on the releases (not just headline) | ✅ Done | CPI medical breakdown (commodities/hospital/professional + medical-care-services) and 4 PPI HC producer cuts, each with its own thread chart; shipped 2026-05-30. JOLTS gained health care & social assistance openings/hires/quits rates 2026-10-18 (`a8e09e9`) |
| 3 | Week-ahead + annual calendar so nothing is a surprise | ✅ Done | `weekly_preview.yml` (Sun, this week + next 4); `release_reminder.yml` (daily "releasing tomorrow", all tiers); `annual_calendar.yml` quarterly HTML; Google Calendar push (`calendar_backfill.yml`, weekly Sunday evening, one cron line since `b9afa7f`). Since 2026-10-14 (`4b68ec9`) Tier A goes to `GOOGLE_CALENDAR_ID` and Tier B/C to `GOOGLE_CALENDAR_ID_OTHER` (falls back to one calendar when unset); event bodies carry release frequency and a healthcare read (`ef4bb28`, `b9afa7f`), and a partial backfill now fails loudly |
| 4 | Macro reading firehose → one scored daily digest | ✅ Done | `research_digest.yml` (daily); 11+ RSS feeds + 3 Gmail senders across 2 accounts; Haiku 4.5 `is_macro` filter + 1–10 read-worthiness score; `tests/test_research_digest.py`, `test_llm_scorer.py` |
| 5 | Joseph Ellis "Ahead of the Curve" chartpack recreated | ✅ Done | `ahead_of_curve/` — full canonical 23-figure set (README + PROJECTS.md); `cli ahead-of-curve`; `tests/test_ahead_of_curve.py` (21 tests) |
| 6 | Top-down valuation/factor reference mirrored + current | ✅ Done | `damodaran/` NYU Stern mirror (494 files on disk; "Phase 1 download+inventory") + `market/` Ken French + AQR + Shiller CAPE; `cli damodaran-fetch` / `market-charts`; CAPE **live from multpl.com** (not stale FMP) |
| 7 | One human-readable hub linking every view | ✅ Done | `readable/index.html` card hub + GitHub Pages (`pages_deploy.yml` → jroypeterson.github.io/macro-monitor); cross-links to the sibling hc-macro-policy site |
| 8 | International "Global macro" context | ✅ Done | EZ/UK/China/Japan CPI/core/GDP/unemployment/policy rates from native sources; weekly `cli global-macro`; shipped 2026-06-04 (caveats: Japan needs `ESTAT_APP_ID`, China via OECD) |
| 9 | Runs unattended; no silent failure | ✅ Mostly | All workflows idempotent; state DBs committed back so ledgers survive; daily `#status-reports` heartbeat (`schedulers/heartbeat.py`, `test_heartbeat.py`); per-series/per-family failure isolation. **Gap:** wake-time DNS race has no retry/backoff (§5) |
| 10 | FOMC decisions post automatically | 🟨 Built; ledger gate untested live | **The statement lane exists and predates this brief** — `fomc_statement.yml` + `fomc_statement.py` (2026-06-16): on a decision day it fetches the statement and the prior one, redlines the language, tags decision + lean (LLM) and posts to `#macro-and-markets`. Its old bash `ET_HOUR==14` gate skipped the 2026-09-16 decision on a green run; since 2026-09-21 it posts when a decision is "owed and unposted" (2-day lookback; ledger row `('fomc_statement', decision date)`), refuses to post a failed analysis as a decision (`32571a9`), and serialises in the `macro-posts` group as a third ledger writer (`f170ab3`). `state/posts.db` holds **no** `fomc_statement` row yet: the first live test is the 2026-10-28 decision. The separate release-family FOMC/minutes parser (`family_type: event`, TODO 1e) is still scaffolding |
| 12 | Fed speeches digest | ✅ Live (2026-06-15) | `fed_speeches.yml` daily ~17:00 ET: new Fed speeches summarised + tagged hawkish/dovish/neutral by Haiku, deduped via committed `state/fed_speeches_posted.db` |
| 13 | Prediction-market odds | ✅ Live (2026-06-12) | `prediction_markets.yml` Monday 08:00 ET: Polymarket macro / pandemics / FDA-catalyst odds to `#prediction-markets` + a `readable/` panel |
| 11 | Release "surprise" gating vs consensus | 🟡 Partial | Tier-B gate falls back to `trailing_5y_volatility`; `vs: consensus` returns "not implemented (v1.5)" — blocked on a **consensus data source**, not code (TODO §Feature gaps) |

**Overall: the v1 goal is met and then some** — the project outgrew the
original "US macro release feed" into a three-layer macro + top-down data
service. ~470 test functions across 45 test files (grep count, 2026-10-20). The
open items are: the FOMC ledger gate's first live meeting (10, 2026-10-28), a
consensus feed (11), and GitHub cron lateness, which no code here can fix (1).

## 3. Key design decisions (and why)

1. **Three explicit layers, one repo.** (1) release feed + cycle context,
   (2) `ahead_of_curve/` Ellis chartpack, (3) top-down market data
   (`damodaran/` + `market/`). They share Slack/Pages plumbing and a release
   cadence mindset but are otherwise independent — a dead market-data endpoint
   can't sink a CPI post. The README leads with this split deliberately.
2. **Declarative families / series, generic engine.** Releases, international
   series (`international/series.yaml`), and Ellis figures (`figures.yaml`) are
   config-driven; `release_runner.py` + a small `computed.py`/`transforms.py`
   layer (sum_of, yoy_pct_of_sum, annualized_mom, level/delta z-score) turn raw
   FRED series into post-ready context. Adding a release is config, not code.
3. **CAPE live from multpl.com, not FMP.** The owner's prior CAPE source (FMP)
   was stale; multpl.com is the canonical Shiller series and is scraped into
   `market/cape.py` / `data/latest/cape_multpl.csv`. Correctness of the regime
   signal over convenience of an already-wired API.
4. **Mirror the reference datasets locally; don't re-pull live.** Damodaran's
   NYU Stern files and Ken French/AQR factors are slow-moving and
   rate-/availability-sensitive, so they're mirrored to disk
   (`damodaran-fetch`, dated `data/raw/<date>/` + `data/latest/` + manifest)
   and charted from the mirror. Keeps charts reproducible and offline-safe.
5. **FRED `/release/dates` is deliberately fail-fast** (short timeout, 2
   retries). A FRED-wide 504 won't survive more retries anyway; the schedulers
   absorb family-level failures and recover next run. (TODO "Design notes" —
   explicitly *not* a bug.)
6. **LLM only where judgment is needed.** Haiku 4.5 scores read-worthiness and
   drops non-macro items in the research digest (~$0.005/run); releases and
   charts are deterministic. The model is a filter, not the pipeline.
7. **State DBs committed back to the repo.** `posts.db` and digest ledgers are
   pushed by the workflows so re-runs don't repost — the cheapest durable
   ledger for a GitHub-Actions-hosted job with no external DB.

## 4. Non-goals / accepted tradeoffs

- **Not** a real-time tick/market-data feed — it's release-cadence and
  daily/weekly batch. ~1h after agency publication is the target, not seconds.
- **Not** a forecasting or trade-signal engine. It surfaces data, context, and
  regime references; the owner draws the conclusions. (Phase 3
  earnings-transcript macro commentary is the only "analysis" stretch, deferred.)
- **Not** a consensus/expectations dataset. Surprise-vs-consensus gating is
  intentionally stubbed until a survey-expectations source is chosen — that's a
  sourcing decision, not a coding gap (don't re-propose hard-coding consensus).
- **Mirror, not API for others.** `damodaran/` and `market/` are a local
  reference archive + charts for the owner, not a re-distributable data service.
- **Median gas price** is out of scope: FRED has no median retail-gas series;
  the `gas_prices` family ships the EIA average by design (TODO).
- Uses **GitHub Actions cron + repo secrets** (headless, unattended), not the
  owner's laptop or interactive claude.ai connectors — the feed must run
  whether or not he's around.

## 5. Known gaps / candidate next steps (feedback most wanted here)

- **FOMC (10)** — the statement lane is built; confirm the "owed and unposted"
  gate posts exactly once on the 2026-10-28 decision. The release-family
  FOMC/minutes parser (TODO 1e) is still scaffolding.
- **GitHub cron lateness (1)** — runs arrive hours late and most are dropped; the
  catch-up fix makes them correct, not timely. Getting near ~1h needs a different
  trigger (an external scheduler dispatching `workflow_dispatch`), not more cron lines.
- **Consensus enrichment (11)** — pick a consensus/expectations source, then
  the Tier-B `vs: consensus` gate and "surprise" framing light up. Which
  source is the real question.
- **`market/` is mirror+charts only** — no regime *gating* or alerting yet
  (e.g. "CAPE at Nth percentile" call-out). Phase-2-ish.
- **Only one family uses the `level` z-score** — consumer-credit delinquency
  (`zscore_kind: level`, since `88de645`, 2026-06-16); umich/jolts/claims remain on
  delta, a per-family tuning decision (TODO).
- ~~`.tmp.<pid>.<hex>` leftovers~~ — checked 2026-10-20: `*.tmp.*` is gitignored
  and `git ls-files` tracks none.

## 6. How to evaluate

- **Mechanics, CLI verbs, workflows, secrets:** `README.md` (don't re-derive).
- **Run the suite:** `python -m pytest tests/ -q` (~470 test functions, 45 files;
  no network/keys needed — fetches are mocked, and since `8f9c11d` two tests that
  had been calling PredictIt and Kalshi live no longer do).
- **Posting/ledger concurrency:** `release_polling.yml`, `reconciliation.yml` and
  `fomc_statement.yml` all write `state/posts.db` and share the `macro-posts`
  concurrency group; read the comment block in `fomc_statement.yml` before moving
  any of them out.
- **Core release logic:** `release_runner.py` + `config.py` (family defs) +
  `computed.py` / `transforms.py` (derived series, z-scores) +
  `tier_b_gate.py` (post/skip decision) + `publishers/slack.py`.
- **Research digest:** `schedulers/research_digest.py` + `collectors/rss.py` +
  `scoring/` (Haiku scorer); `tests/test_research_digest.py`, `test_llm_scorer.py`.
- **Top-down data:** `market/` (`cape.py`, `download.py`, `charts.py`) and
  `damodaran/` + `ahead_of_curve/build.py`; `cli market-charts` /
  `ahead-of-curve` / `damodaran-fetch`.
- **Most useful feedback:**
  1. Is the **three-layer scope** coherent, or has the "macro release feed"
     accreted two side-projects (Ellis chartpack, Damodaran mirror) that belong
     elsewhere? Engage §1/§3 before recommending a split.
  2. Correctness of the **derived-series / z-score / Tier-B gate** logic — the
     numbers the owner will actually trust.
  3. Resilience of the **declarative family/series engine** to a bad or
     revised FRED/international series (failure isolation, revisions, vintages).
  4. Which §5 gap is worth doing first given the goal in §1.
