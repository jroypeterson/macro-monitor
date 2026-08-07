# USAFacts as a macro source — evaluated, answer is NO

**Board #212 item (2), 2026-08-06.** *"Evaluate Steve Ballmer's USAFacts as a usable macro
source."* Evaluated against their own data-sources page, not from reputation.

## Two findings, either of which is disqualifying on its own

**1. It is an aggregator, not a producer.** USAFacts states it relies *exclusively* on
government agencies — "over 70 at last count" — and re-presents them, conducting analysis on
top. It collects no original data. The agencies named are Census, BEA, BLS, the Federal
Reserve, CDC, CMS, FDA, FBI, DOT, SSA, EPA and ~50 more.

**Every one of those this fleet cares about, it already reaches directly**, from the primary
source, on a schedule:

| USAFacts source | already pulled by |
|---|---|
| BLS, BEA, Federal Reserve | `macro_monitor` via FRED |
| CMS, CDC, FDA | `hc_macro_policy` (Pillars A–C), `catalyst_watch` (openFDA) |
| Census | `demographics` (ACS 65+ by CBSA/state) |
| GAO / CBO | `gov_reports` |

So the best case is a second copy of data already held, one revision cycle behind the
primary — and USAFacts' own page warns that government sources "may sometimes contradict
themselves or get revised", which is precisely the lag a re-presenter inherits.

**2. There is no programmatic access.** Their data-sources page documents **no API, no bulk
download, and no developer endpoint** — it hyperlinks out to the source agencies instead. A
scheduled lane cannot consume it without scraping a site whose entire value proposition is
human-readable presentation.

## Verdict

**Do not add it.** It offers no series `macro_monitor` cannot already get, and no supported
way to get it. Its real product is editorial explanation for a general audience, which is a
different job from feeding a chart lane.

**Revisit only if** USAFacts ships a documented API *and* a series the fleet does not already
hold from a primary source — both conditions, not either.

## What this does not say

It is not a judgement on USAFacts' quality. For reading, it is a good site. This evaluates
one narrow question — is it a usable *input* to an automated macro lane — and the answer to
that turns entirely on access and originality, not on how good the site is.
