# macro-monitor — backlog / TODO

Verified inventory of outstanding work, captured 2026-05-30. Grouped by
size. The shipped phases are tracked in `README.md` → "Phasing"; this file
is the **forward** backlog (what's left), with the actual code state
verified rather than copied from the roadmap.

> The two 2026-05-28/29 `#status-reports` alerts (Slack `files:write`
> `missing_scope`, FRED `/release/dates` outage) are **both resolved** —
> the bot token now has `files:write`, and the FRED outage was transient
> (re-tested, recovers in 0.2s). Neither needed a code change.

## Quick / bounded (doc + small wiring)

- [x] **`replay-day` command** — SHIPPED 2026-05-30. Looks up which numeric
  families had a FRED release on the given date (tight realtime `[date,date]`
  window) and re-runs the post-release pipeline for each, dry-run by default.
  Targeted per-date catch-up (vs `poll-all`'s full sweep). Vintage caveat
  documented: processes current-latest data, not an ALFRED point-in-time
  vintage — exact for recent dates; ledger prevents duplicate posts. Pure
  selection helper `families_releasing_on()` unit-tested (4 tests).
- [x] **README roadmap accuracy** — Phase 1.5 "static dashboard" is in
  fact shipped (`render_dashboard()` runs on every post, `cli.py`; plus a
  `render-dashboard` CLI verb), so the roadmap's unchecked 1.5 was
  misleading. Corrected in README 2026-05-30. (Consensus enrichment, the
  other half of 1.5, remains pending — see below.)

## Feature gaps (real; need a small build + a product decision)

- [ ] **Consensus enrichment / consensus-based Tier B gating (Phase 1.5).**
  `tier_b_gate.py` returns `reason="consensus gate not implemented
  (v1.5); defaulting to post"` whenever a family's gate is `vs:
  "consensus"`. Finishing this needs a **consensus / survey-expectations
  data source** (what the release is being judged surprising *against*) —
  that's a sourcing decision, not just code. Until then, gating falls back
  to `trailing_5y_volatility`, which works.
- [ ] **FOMC + minutes (Phase 1e).** Event-family scaffolding exists
  (`family_type: "event"`, a 13:55–14:35 ET polling window in `cli.py`,
  weekly-preview event handling), but `overview.py` states FOMC is "manual
  until a meeting tests the parser." Next FOMC meeting is the natural
  forcing function to finish + test the event parser so decisions post
  automatically.
- [x] **Level z-score** — SHIPPED 2026-05-30. `transforms.level_zscore()`
  standardizes the latest transform *value* `(latest - mean)/std` vs the
  trailing window; `release_runner` selects it when `zscore_kind: level`
  (config already permitted the value; it previously produced `None`). The
  Tier B gate reads `context.zscore` so it gates on whichever kind a family
  configures. Unit-tested (3 tests) + integration-verified on UMich
  sentiment (level −1.64σ vs delta −0.79σ — different questions, as
  intended). **No family flipped to `level` yet** — that's a per-family
  tuning decision with Tier B posting-behavior implications. Best
  candidates: `umich` (sentiment), `jolts` (openings rate), `claims`.

## Larger deferred phases

- [x] **Phase 2 — international macro ("Global macro")** — SHIPPED 2026-06-04.
  Eurozone / UK / China / Japan CPI, core CPI, GDP, unemployment & policy
  rates from native sources (Eurostat JSON-stat · ECB & OECD SDMX-JSON · ONS
  `/data` · BoE IADB CSV · FRED for Japan's rate), normalized to one model and
  surfaced as a weekly `#macro` "Global macro" digest + `outputs/international/`
  dashboard panel — `cli global-macro`, `global_macro.yml` (Sun 08:00 ET).
  Declarative series in `international/series.yaml`; per-series failure
  isolation. **Remaining:** (a) Japan CPI/GDP need a free `ESTAT_APP_ID` (e-Stat
  client built + gated; time-code decode to confirm on first key use); (b) China
  NBS native API is geo-blocked (403) so China uses OECD — fine, but note it;
  (c) BoJ has no clean keyless by-code endpoint, so Japan's policy rate uses
  FRED's call-money series (`sources/boj.py` left as a stub for a future native
  client); (d) possible later adds: PMIs, China IP, eurozone-member detail.
- [x] **Phase 2 — deeper HC-subsector cuts** — SHIPPED 2026-05-30. CPI now
  breaks medical care into commodities (`SAM1`) / hospital & related
  (`SEMD`) / professional services (`SEMC`, NSA) alongside the existing
  medical-care-services line, with a `hc_cpi_detail` thread chart. PPI went
  from headline-only to four HC producer-price cuts (hospitals `PCU622622`,
  physician offices `PCU621111621111`, pharma mfg `PCU325412325412`,
  surgical & medical instruments `PCU339112339112`) + a `hc_ppi_detail`
  chart. All IDs verified live on FRED; CPI+PPI dry-runs render clean.
  (Further depth possible later: dental/eyeglasses detail, GDP/PCE-side
  HC services beyond the current PCE-health-services cut.)
- [ ] **Phase 3 — earnings-transcript macro commentary** (cross-reference
  macro themes against the `transcripts/` corpus).

## Design notes (intentional, not bugs)

- FRED `/release/dates` is **deliberately fail-fast** (`fred.py`:
  `RELEASE_DATES_TIMEOUT=15`, `RELEASE_DATES_MAX_RETRIES=2`) — the
  schedulers absorb family-level failures and recover next run. Do not
  "fix" this with more retries; a FRED-wide 504 won't survive them anyway.
- The FRED **observations mirror** was intentionally skipped in Phase 1
  (`fred_cache.py`) to avoid a premature cache; the defensive cache covers
  outages.
