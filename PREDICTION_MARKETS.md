# Prediction-Market Sources — accessibility & integration inventory

> Persistent reference for the macro_monitor "prediction-market odds" feature (PROJECT_TRIAGE #6).
> What each source covers, whether its **data** is API-accessible **for free without auth**, and how it
> fits JP's healthcare/macro focus. Probed live 2026-06-12. Re-verify endpoints before relying on them.

## TL;DR ranking for *our* use (free, API-accessible market **data**, macro + healthcare-policy signal)

| Rank | Source | Free data API? | Auth? | Best for | Verdict |
|---|---|---|---|---|---|
| 1 | **Polymarket** (Gamma API) | ✅ yes | none | Narrative/tail-risk + **ticker-level FDA approval catalysts** + geopolitics | **Build v1** |
| 2 | **Kalshi** (read endpoints) | ✅ yes | none for reads | Data-release-pegged econ (CPI/GDP/jobs/fed-funds) + 98-series Health + 2,022 Politics | **Build v2** |
| 3 | **Metaculus** | ✅ yes | none | *Judgmental* long-horizon forecasts (not money-weighted) — complement, different signal | Optional later |
| — | **Endpoint Arena** | ❌ private (401) | yes | Clinical-trial / drug-approval / data-readout markets — most on-thesis | Skip — pilot/paper-only, revisit |
| — | **PredictIt** | ⚠️ partial | none | Politics only; most *accurate* (Vanderbilt 93%) but tiny + capped; limited feed | Skip unless pure-politics accuracy wanted |
| — | **Robinhood Prediction Markets** | ❌ no public data API | — | = **Kalshi contracts** today (distribution deal) | Skip for data (adds nothing over Kalshi) |
| — | **IBKR ForecastTrader** (Kalshi+CME+ForecastEx) | ❌ Pro-only API | RSA/Pro | Trading venue; aggregates 3 exchanges | Skip — **JP on IBKR Lite (no API)** |
| — | **CME event contracts** | ❌ paid market data | — | Futures price-target contracts + GDP/CPI | Skip — only via IBKR/data vendor |
| — | **Manifold** | ✅ yes | none | Play-money — low signal (no real capital at risk) | Skip |

---

## Detailed notes

### 1. Polymarket — PRIMARY (build first)
- **API:** Gamma API, `https://gamma-api.polymarket.com`, **no auth, no key.**
  - `/public-search?q=<term>&events_status=active&limit_per_type=N` — keyword search (works well).
  - `/events?slug=<slug>` — full event incl. `markets[]` with `outcomes` + `outcomePrices` (JSON-string lists).
  - `/events?closed=false&active=true&order=volume&ascending=false&limit=500&offset=N` — browse by volume.
  - **Note:** the `/markets?q=` filter param is *ignored* — use `/public-search` or client-side filtering.
  - Trading (CLOB) needs a Polygon wallet; **we only need read data, which is keyless.**
- **Volume:** ~$9.7B/30d (Apr 2026) — largest by volume. Liquidity real: $100M+ on the Fed meeting market.
- **Coverage (live-verified 2026-06-12):**
  - Macro: "US recession by end of 2026?" (Yes 18%), "How many Fed rate cuts in 2026?" (0→77%/1→14%/2→4%), "Fed Decision in June/July/Sept", "What will the Fed rate be at end of 2026?", "S&P 500 June target", gov shutdown, BoE, # Fed dissents, Japan/UK recession.
  - **Healthcare (the differentiator):** ticker-level **FDA drug-approval** markets — "FDA approves Ionis' Olezarsen?", "FDA approves Viridian's Veligrotug?", "FDA approves GSK & Spero's Tebipenem?", "FDA approves Unicycive's Oxylanthanum…", "Who will Trump announce as next FDA commissioner", "RFK Jr. out by Dec 31?", pandemic markets (Hantavirus/Ebola/new-Coronavirus 2026). → effectively a crowd PDUFA/approval-odds feed; ties to biotech-catalyst ideas (#13/#14).
- **Caveat:** offshore-domiciled, claims to block US users (doesn't affect *reading* public data). Whale-distortion risk on thin markets (use volume as a confidence weight). Vanderbilt accuracy 67% (lower than Kalshi/PredictIt) — liquidity ≠ calibration.

### 2. Kalshi — SECONDARY (build second; layer onto release reminders)
- **API:** `https://api.elections.kalshi.com/trade-api/v2`, **read endpoints work with NO signing** (verified). RSA-PSS signing only needed for **trading/portfolio** endpoints. (The old `trading-api.kalshi.com` base returns 401 — use the `api.elections.kalshi.com` base.)
  - `/series/?category=<Economics|Politics|Health|...>` — list series (Economics=578, Politics=2,022, Health=98 as of probe).
  - `/markets?status=open&series_ticker=…`, `/events`, plus market history/orderbook.
- **Volume:** ~$6B/30d, 52.6% US share — **but ~87% is sports.** US CFTC-regulated DCM.
- **Coverage:** deepest *data-release-pegged* econ contracts — CPI (MoM/YoY/core), PCE, unemployment, payrolls, GDP, fed-funds path meeting-by-meeting, T-bills, new-home sales (`KXNHSALES`), building permits (`KXBUILDPERMS`), gas (`KXCPIGAS`), central-bank decisions by country (`KXCBDECISION*`). Health category (COVID variants/waves, FDA pill approvals, "drug ads on TV"). 
- **Why second:** its econ contracts map 1:1 onto macro_monitor's existing release families → layer the implied distribution onto the day-before CPI/jobs reminder. Vanderbilt accuracy 78%.
- **HC/biotech caveat (scan 2026-06-12):** Kalshi has *cataloged* lots of biotech/FDA contracts (under **"Science and Technology"**, not Health — Health is dead COVID-era series) — Beam/Intellia/Verve/Compass drug apps, a generic `KXFDAAPPROVE`, ACA repeal/extension, FDA-commissioner — but **every one is currently 0-volume with no last price** (listed, not trading). So for HC/biotech there's no live Kalshi *signal* yet; treat as a watch-list and auto-promote on volume>0. The live HC/biotech signal today is **Polymarket-only**.

### Endpoint Arena — drug-focused, not usable yet
Clinical-trial prediction market (drug approvals + data readouts) — the most on-thesis platform for biopharma. But **pilot / paper-trading only**, and its API is **private** (`endpointarena.com/api/v1/markets` → 401; no public docs). Nothing to integrate now; **revisit once it exits pilot** and lists real-money markets. `endpointarena.com/method`.

### 3. Metaculus — optional complement
- Public API (no auth) for community/expert **judgmental** forecasts — NOT money-weighted prices. Different signal: "what calibrated forecasters think" vs "what money thinks." Good for long-horizon macro/geopolitical/health questions where money markets are thin. Lower priority.

### PredictIt — differentiated for politics, but limited (answers JP's Q)
- **Most accurate** of the money markets per a 2025 Vanderbilt study: **PredictIt 93%** vs Kalshi 78% vs Polymarket 67%, across 2,500 contracts. Why: a **$3,500 per-trader position cap** → a "crowd of peers," not a "market of whales" (the distortion that hurts Polymarket calibration).
- **Politics-only** (elections, nominations, control of Congress, some policy-outcome contracts). **No healthcare drug-catalyst markets** like Polymarket's FDA set, and small dollar size.
- **Data access:** a basic public REST feed (`https://www.predictit.org/api/marketdata/all/`) exists but is limited (top-level prices); full depth needs scraping. 
- **Verdict:** worth it ONLY if we specifically want *highest-calibration political/election* odds (e.g. clean "control of Congress / who wins" signal). For HC-*policy* and drug catalysts, Polymarket is richer. Keep documented; not in the v1/v2 build.

### Robinhood Prediction Markets — skip for data (answers JP's Q)
- Today it's a **distribution partnership with Kalshi** — the contracts ARE Kalshi contracts, so the data == Kalshi. No public Robinhood prediction-market data API (the `robinhood-trading` MCP we have is equities/options/index only).
- 2026 change in motion: RH + Susquehanna acquired **MIAXdx** (closed Jan 2026) and are launching their own exchange ("Rothera"), starting to route some volume (World Cup) off Kalshi. **Re-check in 6–12 months** — if Rothera lists unique macro/policy contracts with a data API, revisit. Today: nothing to integrate.

### IBKR ForecastTrader / ForecastEx / CME — skip at JP's tier (answers JP's Q)
- IBKR launched (2026-05-14) a **unified portal aggregating Kalshi + CME + ForecastEx** with best-net-price routing. API exists (TWS/Web API) **but is Pro-only — JP is on IBKR Lite (no API access)**; even on Pro it's a *trading* venue, not a clean free data feed.
- **What CME contributes (beyond Kalshi):** event contracts on **11 underlying futures** — E-mini S&P 500 / Nasdaq 100 / Russell 2000 / DJIA, energy (crude, nat gas), crypto (BTC, ETH), FX (EUR/GBP/JPY), metals (gold) — priced $1–$99 ($100 payout), **plus recently GDP & CPI** indicator contracts. So CME ≈ "will index/commodity/FX close above X" price-target contracts + a little econ.
- **What ForecastEx contributes (IBKR's own affiliate, beyond Kalshi):** categories = **economic indicators, capital markets, central banks, sovereign debt, climate/environment, elections, government actions** ($0.02–$0.99, $1 payout). Adds central-bank-decision, sovereign-debt, and **climate** contracts not central to Kalshi.
- **Net:** the unique data (CME futures price-targets, ForecastEx climate/sovereign) is real but locked behind Pro+paid data. Not accessible for our free signal use. Revisit only if JP upgrades to IBKR Pro.

---

## Regulatory durability caveat
Congress is actively weighing (mid-2026) **restricting election/policy betting** on Kalshi/Polymarket over insider-trading concerns (CNBC/Axios, May–Jun 2026). The **political/policy** markets are the ones most at risk of being curtailed; macro (Fed/CPI/recession) and the FDA-approval catalysts are lower-risk. Build the integration so a category can be dropped without breaking the rest.

## Design decisions (JP, 2026-06-12)
- **Surface: BOTH** — a readable HTML panel in the macro hub **and** a Slack post to the **new `#prediction-markets` channel** (JP created it to collect everything).
- **3 lanes:** (1) **Macro** {recession, # rate cuts, Fed meeting, shutdown, S&P} · (2) **Healthcare** {FDA drug-approval catalysts, FDA commissioner, RFK, pandemics/measles, HC policy} · (3) **Aggregated** — a compact top-line pulling the single headline number from each lane.
- **Healthcare lane stays in macro_monitor for now**; if it gets differentiated/robust, split it out later. The **biotech FDA-catalyst markets ALSO route to the biotech catalyst lane** (PROJECT_TRIAGE #13/#14) — dual-purpose.
- Curated, reviewable market list: **`PREDMARKET_HC_WATCHLIST.md`** (JP picks what enters the weekly rundown).

## Build plan (sequenced)
- **v1 — Polymarket client + 3-lane rundown — ✅ SHIPPED 2026-06-12.** `predmarkets/` package (keyless Gamma `client.py` resolving each curated market by search+title-match → highest-volume active event; `rundown.py` → text/Block Kit/HTML; `post.py` → readable panel + bot-token Slack post). CLI `pred-markets` (dry-run default, `--post` to send). Readable panel `readable/prediction_markets/` linked from the hub; weekly `prediction_markets.yml` (Mon 08:00 ET). 11 tests. Markets annotated by volume (🟢/🟡/🔴). **Activation steps:** invite the Slack bot (ClaudeBot) to **#prediction-markets** and ensure `SLACK_BOT_TOKEN` (+ optional `SLACK_PREDMARKET_CHANNEL_ID`) secrets are set — until the bot is in-channel, `--post` degrades to dry-run + writes the panel.
- **v1.2 — PredictIt source + legislative lane + multi-source discovery — ✅ SHIPPED 2026-06-12.** Added a keyless **PredictIt** client (`predictit.py`, `/api/marketdata/all/`) — markets carry a `source` and render with a 🎯 (calibrated) flag, no $ (PredictIt's $3,500 cap = no whales; no per-market volume in the feed). Curated PredictIt adds: **control of government** (Senate control R 60% / House D 73% / Balance of power) in the macro lane + aggregated top-line, and a new **legislative lane** (CLARITY Act, SAVE Act). **Discovery now scans Polymarket + PredictIt + Kalshi** with PER-SOURCE silent seeding (adding a source seeds it silently instead of flooding; ids source-prefixed pm:/pi:/kalshi:) and a legislative relevance set (JP: HC first, then any *meaningful* legislative change). `resolve.py` dispatches each spec to its source's client. +7 tests (25 in predmarkets; suite 256 green). Verified live: PredictIt control + legislative resolve; discovery seeded kalshi 665 / pi 20 / pm 66.
- **v1.1 — movers + discovery — ✅ SHIPPED 2026-06-12.** `history.py` appends a dated snapshot per market each run (keyed by stable config key, so a rolled-over market keeps one continuous series; `data/predmarket_history.json`, committed weekly) and `movers()` flags ≥8pp **WoW / YoY** shifts (per-outcome match; YoY accrues over time) → a "📈 Notable moves" section. `discovery.py` sweeps Polymarket by macro+HC keywords, diffs against a persisted seen-set (`data/predmarket_seen.json`; seeds silently on first run), and surfaces **newly-opened relevant markets** (the fact one opened is the signal) → a "🆕 Newly-opened" section. Both wired into the CLI + readable panel + Slack; +7 tests (18 total).
- **v2 — Kalshi:** (a) econ overlay onto the existing CPI/jobs/GDP release reminders; (b) watch the cataloged-but-untraded HC/biotech contracts and **auto-promote any with volume>0** into the rundown.
- **biotech routing:** the FDA-approval lane feeds both macro_monitor's HC rundown and the future biotech catalyst channel.
- **later — Metaculus** (judgmental complement) / **PredictIt** (pure-politics calibration) / **Endpoint Arena** (when it exits pilot) / **Robinhood-Rothera** (re-check) only if a gap appears.

Pointer added to root `CAPABILITIES.md`.
