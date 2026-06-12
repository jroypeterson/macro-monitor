# HC / Biotech prediction-market watchlist — pick what goes in the weekly rundown

> Live scan 2026-06-12 of **Polymarket** (Gamma, keyless) + **Kalshi** (`api.elections.kalshi.com`, keyless reads).
> JP: tick the ones you want in the weekly **#prediction-markets** HC-macro rundown. Organized by the
> 3 lanes we agreed (Macro / Healthcare / Aggregated). Raw scans saved in `data/predmarket_hc_scan_*.json`.

## ⚠️ The key finding: liquidity is one-sided
- **Polymarket = the live signal.** Real volume, real odds (pandemics carry $millions; FDA-approval markets are thinner, $66–$570k — indicative but whale-sensitive).
- **Kalshi = mostly scaffolding right now.** It has *cataloged* far MORE biotech/FDA contracts (Beam, Intellia, Verve, Compass, a generic "Will the FDA approve drug?", ACA repeal/extension, FDA-commissioner) — but **every HC/biotech market is currently 0-volume with no last price.** Listed, not trading. So they give no live signal *today*; worth watching in case volume arrives. Kalshi's "Health" category is entirely dead COVID-era series; its live biotech contracts sit under **"Science and Technology."**
- **Net:** build the live rundown off **Polymarket**; carry the **Kalshi** contracts as a "watch — listed, awaiting volume" appendix and auto-promote any that start trading.

Liquidity legend: 🟢 >$250k · 🟡 $25–250k · 🔴 <$25k (odds noisy) · ⚪ Kalshi listed, 0 vol (no price yet)

---

## Lane 1 — Pandemics / public-health (Macro lane; some overlap to HC)
**Polymarket (live):**
- [ ] 🟢 **Hantavirus pandemic in 2026?** — Yes **4%** ($15.2M)
- [ ] 🟢 **Measles cases in U.S. in 2026** (9 buckets) ($7.7M)
- [ ] 🟢 **New pandemic in 2026?** — Yes **10%** ($0.72M)
- [ ] 🟢 **Ebola pandemic in 2026?** — Yes **8%** ($0.46M)
- [ ] 🟡 **New COVID variant of concern before 2027?** — Yes **14%** ($241k)
- [ ] 🟡 **Hantavirus vaccine in 2026?** — Yes **6%** ($120k)
- [ ] 🟡 **CDC issues Level 4 warning by Dec 31?** — Yes **24%** ($72k)
- [ ] 🟡 **Measles cases in U.S. by June 30** (4 buckets) ($38k)
- [ ] 🔴 **New Coronavirus Pandemic in 2026?** — Yes **6%** ($15k)

**Kalshi (⚪ listed, 0 vol):** `KXMEASLES` (Measles cases >3k/4k/6k/8k/10k) · `KXAVGMEASLESDJT` (Measles during Trump admin)

## Lane 2 — FDA drug-approval catalysts (Healthcare lane → also route to the biotech catalyst lane)
**Polymarket (live) — crowd PDUFA/approval odds per drug:**
- [ ] 🟢 **FDA approves Retatrutide this year?** — Yes **12%** ($570k) — *Lilly triple-G obesity*
- [ ] 🔴 **FDA approves Ionis' Olezarsen?** — Yes **92%** ($2.2k)
- [ ] 🔴 **FDA approves Arcutis' Zoryve cream?** — Yes **89%** ($4.1k)
- [ ] 🔴 **FDA approves Merck's Welireg + Keytruda/Qlex?** — Yes **84%** ($0.3k)
- [ ] 🔴 **FDA approves Unicycive's Oxylanthanum carbonate?** — Yes **76%** ($3.5k)
- [ ] 🔴 **FDA approves Arcalyst technology transfer?** — Yes **72%** ($2.3k)
- [ ] 🔴 **FDA approves Daraxonrasib this year?** — Yes **70%** ($66) — *Revolution Medicines RAS(ON)*
- [ ] 🔴 **FDA approves Viridian's Veligrotug?** — Yes **69%** ($2.7k) — *TED*
- [ ] 🔴 **FDA approves GSK & Spero's Tebipenem HBr?** — Yes **60%** ($4.1k)
- [ ] 🔴 **Eli Lilly licenses Peptron's SmartDepot by Oct 7?** — Yes **20%** ($10k)

**Kalshi (⚪ listed, 0 vol) — broader catalog, watch for volume:** `KXFDAAPPROVE` ("Will the FDA approve drug?", 24 dated buckets) · `KXFDARETATRUTIDE` (Retatrutide by date) · `KXNEWDRUGAPPBEAM` (Beam Therapeutics) · `KXNEWDRUGAPPNTLA`/`KXFDAAPPROVALDATENTLA` (Intellia) · `KXFDAVERVE102` (Verve-102) · `KXFDAAPPROVALDATECMPS`/`KXNEWDRUGAPPLICATIONCMPS` (Compass Pathways) · `KXFDAAPPROVALPSYCHEDELIC` · `KXFDAANNOUNCE` · `KXNEWDRUGS` ("New FDA drugs")

## Lane 3 — HC policy / regulatory / political-health (Healthcare lane)
**Polymarket (live):**
- [ ] 🔴 **RFK Jr. out by December 31?** — Yes **53%** ($19k)
- [ ] 🔴 **Who will Trump announce as next FDA commissioner?** (33 names) ($12k)

**Kalshi (⚪ listed, 0 vol):** `KXACAREPEAL` (ACA repeal before 2029) · `KXACAEXT` (ACA premium-credit extension before 2027) · `KXACAHSAFSA` (bill to route ACA subsidies into HSA/FSA) · `KXFDANOM` (FDA commissioner nominee — Hahn/Brenner/Saphier/Oz/Diamantas/Giroir…) · `KXVACCINEREC` (ACIP vaccine rec ended — Rotavirus/Polio/HepB/Flu/Dengue/COVID)

---

## Other drug-focused platform checked: Endpoint Arena
**Not usable yet.** Clinical-trial-focused prediction market (drug approvals + data readouts), but **still in pilot / paper-trading only**, and its API is private (`/api/v1/markets` → 401). No public data. Revisit once it exits pilot and lists real-money markets — it's the most on-thesis platform if it matures (`endpointarena.com/method`).

## My read / recommendation for the rundown
- **Include now (real signal):** the high-volume pandemic/measles set (Lane 1) + **Retatrutide** (Lane 2, the only liquid FDA one) + **RFK-out / FDA-commissioner** (Lane 3).
- **Include as a "biotech catalyst board" but flag thin-liquidity:** the rest of the Polymarket FDA-approval set — they're genuinely useful as *directional* per-drug odds (and unique to Polymarket), just label them low-volume so a 92% isn't over-trusted.
- **Carry Kalshi as "watch — awaiting volume":** auto-promote any contract once it starts trading (the build can check volume>0 each run).
- **Aggregated lane:** a compact top-of-rundown line — e.g. "recession 18% · 0 Fed cuts 77% · new pandemic 10% · RFK out 53%" — pulling the single headline number from each lane.
