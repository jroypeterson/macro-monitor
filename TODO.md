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

- [ ] **`replay-day` command is a stub but advertised in the README.**
  `cmd_replay_day` (`cli.py`) only prints "not yet implemented (Phase 1a
  in progress)", yet `README.md` shows `replay-day 2026-05-15 --dry-run`
  as a usage example. Decide: implement it (re-run any releases that
  landed on a given date as if it were the original release morning — the
  polling + parse machinery already exists, so this is mostly wiring), or
  remove it from the docs until built.
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
- [ ] **Level z-score** (`release_runner.py`: "level z-score not yet
  implemented; flag in v1"). Minor — currently only the delta z-score is
  computed.

## Larger deferred phases

- [ ] **Phase 2 — international macro** (ECB / BoJ / eurozone / China / UK).
  Already named as "Phase 2" in `overview.py`'s pinned-overview text.
- [ ] **Phase 2 — deeper HC-subsector cuts** (beyond current healthcare
  employment + medical-care CPI sub-cuts).
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
