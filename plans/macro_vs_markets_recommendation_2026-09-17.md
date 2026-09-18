# Macro vs markets: should #macro-and-markets be split? (board #310)

Written 2026-09-17. This is a recommendation only. No code, config or channel was changed, and nothing was posted.

JP, 2026-08-06: *"The channel is too cluttered with macro and markets mixed. Keep macro where it is, stand up a separate markets workflow for the other charts, possibly combined with the weekly chart pack since it is similar data. Tell me what you think."*

## Recommendation

**Don't create a new channel, and don't create a new lane.** Make `#chart-pack` the one home for markets content. Make `#macro-and-markets` macro-only by removing the "Markets" half from its pinned card. **Option (b), done lightly.**

Why: **no markets posts reach the channel today, so there is nothing to split off.** Two things make the channel look mixed and cluttered:

1. **The pinned card says the channel is mixed.** It opens with *"Two halves — macro and markets — across four layers"* and includes a full "Markets" section (CAPE, ERP, factor returns, earnings & growth). None of those charts ever post to Slack. The pages the card links to are also stale: `readable/market/index.html` was last built 2026-06-04 (105 days ago) and `growth.html` on 2026-06-19 (90 days ago). `market-charts` and `growth` run only on demand and have no cron.
2. **Most of the actual clutter is macro reminders.** It is not markets content (counts below).

The weekly chart pack already calls itself **"Weekly Market & Sector Chart Pack"**. It already posts a market overview every Friday (S&P 500, Nasdaq 100, Russell 2000 and sector returns) to `#chart-pack`, and already contains Global equity valuations and Market structure sections. That makes it the markets lane already. Opening a separate markets channel would give JP a channel with about 0 posts a week.

## Measured post counts: #macro-and-markets (C0B6CE79K35)

Top-level messages only. Thread replies such as Ahead-of-the-Curve charts and long-history threads were not counted.

**Last 2 weeks (2026-09-03 to 2026-09-17): 21 posts**

| Class | Type | Count |
|---|---|---|
| Macro | "Releasing tomorrow" reminders | **15** (71%) |
| of which | "(no scheduled macro releases tomorrow)" | **6** (29% of all posts) |
| Macro | RELEASED posts (Trade Balance, Claims ×2, Employment, PPI, CPI) | **6** |
| Markets | anything | **0** |

**The window JP was reacting to (2026-07-23 to 2026-08-06): 48 posts**

| Class | Type | Count |
|---|---|---|
| Pinned card | "Macro & Markets Monitor — channel overview" reposts | **19** (18 in a 28-minute burst on 2026-08-04, 16:01–16:49 ET, two days before his comment) |
| Macro | reminders, RELEASED/REVISED, Sunday week-ahead | **27** |
| Other | Claude app joined + greeting (2026-07-24) | **2** |
| Markets | anything | **0** |

**What "macro" and "markets" mean here:** **Macro** means the economy, measured by a statistical agency or central bank on a release calendar: CPI, payrolls, GDP, claims, FOMC, Fed speeches, global CPI/GDP. **Markets** means prices of traded assets and the valuations built from them: index returns, CAPE, implied ERP, factor returns, forward P/E, market structure. A useful test: if the number comes from a release calendar, it's macro. If it comes from a price, it's markets. Two items are borderline and I'd keep them in macro because they are driven by releases: *Ahead of the Curve* (posts on a data release) and S&P EPS vs corporate profits (a BEA release).

## Options and costs

| | (a) New markets channel + lane | (b) Merge markets into the weekly chart pack **(pick)** | (c) Keep one channel, add threading/section headers |
|---|---|---|---|
| New channel | Yes (plus card, bookmarks, a row in `refresh_channel_pins.py`) | No | No |
| New scheduled task | Yes, a GH Actions cron for `market-charts` + `growth` + a Slack post | No. An optional weekly step in the existing Fri `HC Sector Chart Pack` run | No |
| Scripts that change | `macro_monitor/cli.py`, a new workflow yml, a new publisher, `scripts/refresh_channel_pins.py`, `SCHEDULED_JOBS.md` | `macro_monitor/publishers/overview.py` (drop the Markets section and the "two halves" framing). `sector_chart_pack` render + `channel_pin.py` (add a "Top-down valuation" link block or section). Optionally one line in `SCHEDULED_JOBS.md` | `overview.py` headers only |
| Posts/week to the new home | ~0 today (the markets layer posts nothing) | +0 posts. The chart pack card gains a link or section | unchanged |
| What JP loses | Nothing, but he gets a near-empty channel to check | CAPE/ERP/factor links move from the macro pin to the `#chart-pack` pin | Nothing, and it doesn't fix the clutter |
| Fixes the stale markets pages? | Only if the new cron is built | Only if the pack builds them (see step 3) | No |

(c) is cheapest, but it treats the wrong cause. A section header can't reduce 15 reminders in 21 posts.

## If JP says yes: the build, smallest first

1. `macro_monitor/publishers/overview.py`: remove the "Markets" section and the "Two halves" line, and retitle the card "Macro Monitor". This makes the channel macro-only in how it describes itself. Consider renaming the channel to `#macro` (the Slack rename keeps the ID `C0B6CE79K35`, so `SLACK_MACRO_CHANNEL_ID` does not change).
2. `sector_chart_pack`: add a "Top-down valuation" block linking the CAPE/ERP/factor/growth pages, both to the pack and to its pinned card.
3. Optionally, so those links aren't 90+ days stale: run `macro_monitor.cli market-charts` + `growth` as one more non-gating step of the Friday pack task, or add a weekly GH cron to macro_monitor. Either choice costs one step. This does **not** need a new Windows task.

## Proposed separately (not part of #310, needs JP's decision)

- **Stop posting "no scheduled macro releases tomorrow."** That would remove 6 of 21 posts (29%) with no information lost. Folding the reminder into the Sunday week-ahead would remove most of the other 9. This is the biggest clutter reduction available, and it is a separate change from what JP asked for.

## Found while measuring: a silent outage in the macro lane (not part of #310)

- **The FOMC statement for 2026-09-16 was never posted, and the run was green.** Run `35151160595` started 21:13 UTC (17:13 ET). The workflow's guard requires `ET_HOUR == 14`, and GitHub delivered the 14:05 cron about 3 hours late, so the run set `skip=true` and exited successfully. The 21:56 UTC retry skipped the same way. This is the "gate on the trigger's clock" failure class: a late run silently turns into a no-op. **Verified from the run log.**
- **Release posts are late or missing (hypothesis, not diagnosed).** Release polling ran only about twice a day (e.g. 15:18 and 18:59 UTC) on 2026-09-15 to 17, not every 15 minutes. PPI and Claims on 2026-09-10 posted at 14:07 ET, 5.5 hours after the 08:30 print. Retail Sales (2026-09-16) and Claims (2026-09-17) do not appear in the channel at all. No Sunday week-ahead or Global macro post appears since 2026-08-02. I did not check the causes.
