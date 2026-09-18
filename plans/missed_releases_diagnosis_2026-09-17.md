# Missed releases diagnosis — 2026-09-17 (written 2026-09-18)

Status: DIAGNOSIS + PLAN ONLY. No code changed, no workflow dispatched, nothing posted.

## Outcome

- **Root cause 1 (platform): GitHub's scheduler is creating this account's scheduled runs 3–4 hours late, and drops most of them.** The lag is in run *creation*, not the runner queue (created→started = 0 s on all 40 most recent runs of 3 workflows). It is account/platform-wide, not a repo setting: `daily-reads` (cron 12:00 UTC) ran at 15:48–15:56 UTC on 2026-09-15..17. All 14 macro_monitor workflows show `active` — nothing disabled.
- **Root cause 2 (ours): both posting paths gate on the wall clock at run time, not on "is a release due and unposted".** A late run lands outside the window and exits 0. The ledger that would make catch-up safe already exists — `poll-all` simply never consults it after 11:00 ET.
- **Why it was green:** "outside the window" is coded as a clean exit (`return 0` / `skip=true`), the same outcome as "nothing to do". No check compares *expected* releases with *posted* ones.

## Measured cadence (gh run list, schedule events only)

`release_polling.yml` cron `*/15 11-18 * * 1-5` = **32 fires per weekday**.

| Period | Scheduled runs per weekday (of 32) | First run of day (ET) | Effect |
|---|---|---|---|
| 2026-05-29 → 07-31 | 2–6 | 08:07–12:36 | Morning window hit on some days |
| 2026-08-07 → 08-14 | 8 | ~07:41 | Window hit daily |
| 2026-08-17 → 08-26 | 8–14 | ~07:21 (about 20 min late) | Healthiest period |
| **2026-08-27 → 09-17** | **1–3** | **10:46–13:51** | Window mostly missed |
| 2026-09-14 → 09-17 | **2** | 11:18–12:45 | **0 runs inside any window** |

Lateness on other workflows over 2026-09-03..17 (the crons are UTC):

| Workflow | Cron (ET) | Actual (ET) | Late by |
|---|---|---|---|
| fomc_statement | 14:05 | 16:15–18:20 | ~2h10m–4h15m |
| heartbeat | 08:00 | 10:26–14:30 | ~2h30m–6h30m |
| fed_speeches | 17:00 | 18:40–20:15 | ~1h40m–3h15m |

Even in the healthiest period, more than half of the */15 fires were dropped. **Cron punctuality on GitHub Actions is not something this lane can rely on.**

## Timeline (ET)

| Date | Event | What ran | Result |
|---|---|---|---|
| 2026-08-26 | Last day with a normal morning cadence | 8 poll runs from 07:26 | PCE and GDP posted 08:53 |
| 2026-08-27 | Lag jumps to ~4h | 1 poll run at 16:53 | Outside window, exit 0 |
| 2026-09-02 | Claims (08-22), JOLTS, durables, UMich | Run at 10:57 lands in window | Posted up to 11 days late, in one batch at 10:58 |
| 2026-09-10 | Claims (w/e 09-05), PPI | Run at 14:04 lands in the **FOMC** window (13:55–14:35) on a non-FOMC day | Posted 14:06 by luck |
| 2026-09-11 | CPI | Run at 10:49 | Posted 10:50 by luck |
| **2026-09-16** | Retail Sales (Aug) 08:30; Industrial Production (Aug) 09:15; **FOMC decision 14:00** | Poll 11:18 and 14:59: both `Outside polling window (now=Wed 11:19 ET); exit clean.` (run 35114489146). FOMC runs 17:13 and 17:56: `ET_HOUR=17` so skip=true (run 35151160595) | **Nothing posted. All runs green.** |
| **2026-09-17** | Initial Claims (w/e 09-12) 08:30 | Poll 11:25 and 15:10: outside window (run 35240116996) | **Not posted. Green.** |

Ledger check (`state/posts.db`): newest `retail_sales` row is period 2026-07 (posted 2026-08-14). Newest `claims` row is 2026-09-05. Newest `industrial_production` row is 2026-07. There is no FOMC posted-state anywhere.

## Code locations

- **Poll gate:** `cli.py:1536-1552` (`cmd_poll_all`). `morning_window = 08:25–11:00`, `fomc_window = 13:55–14:35`. Outside both it returns `0` without reading the ledger or the release calendar.
- **FOMC gate:** `.github/workflows/fomc_statement.yml:33-47`. `[ "$ET_HOUR" = "14" ] && DECISION=yes`. The gate lives in bash, so no Python test can reach it.
- **Idempotent state:**
  - Releases: **yes.** `posts_ledger.py`, table `posts` with `PRIMARY KEY (family_id, period)`. `cmd_post_release` (`cli.py:157-170`) returns early on `UNCHANGED`, and the workflow commits `posts.db` back under `if: always()`. A late run can therefore post safely; the window gate is the only thing stopping it.
  - FOMC: **no.** `cmd_fomc_statement` (`cli.py:1119+`) calls `post_to_macro` unconditionally. Only the hour check prevents a double post, and a `workflow_dispatch` bypasses it (yml:38).
- **Heartbeat** (`schedulers/heartbeat.py`) reports `is_stale` series from outputs. It never compares a scheduled release date against the ledger, so it could not see this.

## Why the runs were green (silent-failure shape)

1. **Too early / too late and "nothing to do" share one exit path.** `return 0` with a log line nobody reads. This is the fleet's "a health proxy decays when nothing changes" pattern: the run *happened*, so everything looks healthy.
2. **The gate asks "what time is it", not "what is owed".** The system knows the owed set (`release_calendar_id` per family → FRED release dates, plus `fomc.all_meetings()`), but nothing consults it.
3. **No invariant compares expected with delivered.** "A release due at T should have a ledger row by T + N" is never checked. The heartbeat is itself on the lagged scheduler (08:00 cron, ran 10:26–14:30).
4. **Luck hid the regression for 3 weeks.** Lagged runs still landed inside a window on 09-02, 09-03, 09-04, 09-10 and 09-11, so releases kept appearing, just late and batched.

## The invariant

> For every Tier A family (and every FOMC decision) with a scheduled release at time **T** on or before now, either a ledger row for that period exists, or an alarm has been raised by **T + 45 min**. A run that sees an owed, unposted item must never exit 0 silently.

## Fix design

### F1. Gate on "due and unposted", not on the clock (`cmd_poll_all`)
- Replace the window check with `owed = [f for f in tier_A if release_time(f, today) <= now < release_time(f, today) + MAX_LATENESS and not ledger.has(f, expected_period)]`.
- Get today's scheduled families from FRED release dates (`release_calendar_id`, via the existing `get_release_dates` client call, cached per day) plus `release_time_et`.
- **MAX_LATENESS = 30h.** That covers a same-day miss and the next morning. Past it, do not post as fresh: alarm and log instead.
- A post made more than 30 min after T carries a context line: "Posted late: released 08:30 ET, delivered 11:19 ET". Never pass a late post off as real-time.
- Keep the cheap fast path: with nothing owed, exit 0 as today, which leaves the fetch cost unchanged.

### F2. Move the FOMC gate into Python and give it posted-state
- `fomc_due(now, ledger)` = today is a decision day AND now ≥ 14:00 ET AND now < 14:00 + MAX_LATENESS AND no `posts` row for `('fomc_statement', meeting.end.isoformat())`.
- Reuse `posts_ledger` with `family_id='fomc_statement'`, so there is no new store. Record a row after a successful post.
- Delete the bash `ET_HOUR` gate. Make `workflow_dispatch` go through the same ledger check, with an explicit `--force` for manual reposts.
- Add `state/posts.db` persistence to `fomc_statement.yml` (it has no commit step today).

### F3. Stop depending on GitHub cron punctuality
- Created→started is 0 s, so a **`workflow_dispatch` triggered by an external clock does not suffer the lag**. Add an external pinger (Cloudflare Worker cron or cron-job.org, free tier) that dispatches `release_polling.yml` at 08:31, 08:45, 09:16, 10:01, 10:15 and 14:01 ET on weekdays, and `fomc_statement.yml` at 14:01 and 14:10 ET on decision days.
- Keep the GitHub crons as a backstop. F1 and F2 make redundant runs harmless.
- Cost: one PAT-scoped secret on the pinger. Decision for JP: which external scheduler (priced below).

### F4. Owed-but-unposted alarm
- Add `poll-all --check-owed`, which runs at the end of every poll. For each owed item older than T + 45 min with no ledger row, post one `#status-reports` alarm per (family, period), deduped via the same ledger or a small `alarms` table, and exit **1** so the run goes red.
- The alarm must be triggered by the external pinger too (F3), not only by GitHub cron. Otherwise it inherits the same 3–4h blind spot.
- Add an "owed vs posted today" line to the heartbeat.

### F5. Make the gate outcome visible
- A skip prints `::notice::` with the reason and the owed count, so a green run that skipped owed work reads differently from an idle one.

## Tests that would fail on today's code

All use a frozen `now` and a temp ledger, with no network (`test_no_live_network.py` already enforces that).

1. `test_poll_all_catches_up_after_morning_window`: Wed 2026-09-16 11:19 ET, retail_sales scheduled 08:30 today, ledger has no 2026-08 row. Expect `cmd_post_release('retail_sales')` to be called. **Today: returns 0 without calling it.**
2. `test_poll_all_catches_up_afternoon`: same setup at 14:59 ET. **Fails today** (outside both windows).
3. `test_poll_all_idempotent_after_catchup`: ledger already has the row. Expect no post. Passes today; it pins the negative.
4. `test_poll_all_respects_max_lateness`: release 3 days old and unposted. Expect no fresh post, one alarm, rc=1. **Fails today** (rc=0, no alarm).
5. `test_fomc_due_late_run_posts`: 2026-09-16 17:13 ET, decision day, no ledger row. Expect `fomc_due` to be True. **Fails today**: the gate is bash, so the function does not exist.
6. `test_fomc_no_double_post`: ledger row present, dispatch without `--force`. Expect no post. **Fails today** (posts unconditionally).
7. `test_fomc_workflow_has_no_wallclock_gate`: static. Parse `fomc_statement.yml` and assert no `ET_HOUR` equality. **Fails today.**
8. `test_owed_alarm_fires`: 08:30 release, now 09:20, no row. Expect alarm and rc=1. **Fails today.**
9. **Mutation check:** revert F1 to the clock gate and confirm tests 1, 2 and 8 go red. A green suite on its own is not evidence.

## Immediate recovery (not done, JP's call)

Once F1 lands, one dispatched `poll-all` run would post retail_sales (Aug), industrial_production (Aug) and claims (w/e 09-12) through the ledger, marked late. Before F1, a `--skip-window-check` dispatch does the same thing today. The FOMC 09-16 statement needs `workflow_dispatch` on `fomc_statement.yml` (with no posted-state, check Slack first to avoid a double post). None of this was run.

## Decision for JP (priced)

- **External trigger for F3:** Cloudflare Worker cron ($0 on the free tier; per-worker cron-trigger limit recalled, not verified) vs cron-job.org ($0, hosted UI). Either needs one fine-grained PAT with `actions:write` on macro_monitor. Recommendation: Cloudflare, because the config lives in code. Without F3, F1 and F2 still recover everything, but 3–4h late.
