"""Build readable/why_each_measure_matters.html -- the #macro channel bookmark.

Published as the artifact https://claude.ai/artifact/PszYN4CLpyYsPoNnAAjrzN
(bookmark "Why each measure matters" in #macro, added 2026-11-12). To update:
edit the rows below, run `python readable/build_why_page.py readable/why_each_measure_matters.html`,
then republish that file to the SAME artifact URL so the bookmark keeps working.
When a release family is added to config/release_families.yaml, add its row here.
"""
import html
import pathlib
import sys

OUT = pathlib.Path(sys.argv[1])

# (name, source, cadence/time, what, why, healthcare read or "")
TIER_A = [
    ("CPI", "Bureau of Labor Statistics", "Monthly · 8:30 ET",
     "Price change of the basket urban consumers buy. Headline covers everything; core leaves out food and energy.",
     "The inflation number markets trade on. It moves the expected path of Fed rates, and rates set the discount rate on long-dated cash flows, which hits biotech and other long-duration equities hardest.",
     "The post breaks out medical care services, medical care goods (drugs and equipment), hospital services and physician and dental services. Those lines show pricing power at providers and how fast drug prices are rising for consumers."),
    ("Employment Situation (jobs report)", "Bureau of Labor Statistics", "Monthly · 8:30 ET",
     "Jobs added (nonfarm payrolls), the unemployment rate (U-3), the broader underemployment rate (U-6) and average hourly earnings.",
     "Employment is the other half of the Fed's mandate. Strong hiring with firm wages keeps rates higher for longer; a weak report pulls rate cuts forward. It is usually the most market-moving release of the month.",
     "Hiring is shown for ambulatory care, hospitals and nursing and residential care. Healthcare has been one of the steadiest sources of job growth, so the pace tells you about staffing supply and wage pressure at providers. Employer insurance coverage also follows employment."),
    ("Consumer spending and PCE inflation", "Bureau of Economic Analysis", "Monthly · 8:30 ET",
     "Personal income, consumer spending (in real and nominal terms), the saving rate and the PCE price index, headline and core.",
     "Core PCE is the measure the Fed's 2% target is written against, so it outranks CPI for policy. Consumer spending is about two thirds of GDP, which makes this the best monthly read on demand.",
     "PCE gives healthcare a much larger weight than CPI does, because it counts care paid for by employers, Medicare and Medicaid, where CPI counts only what households pay out of pocket."),
    ("Initial jobless claims", "Department of Labor", "Weekly, Thursday · 8:30 ET",
     "People filing for unemployment insurance for the first time that week, plus continued claims (people still collecting).",
     "The fastest labor-market signal there is. Turning points in the economy tend to show up here weeks before the monthly jobs report. Continued claims show how hard it is to find a new job once laid off.",
     ""),
    ("GDP", "Bureau of Economic Analysis", "Quarterly · 8:30 ET",
     "Growth in total US output, quarter over quarter at an annual rate, in real (inflation-adjusted) and nominal terms, with the main components.",
     "The broadest scorecard of the economy and the base for earnings growth across sectors. The mix matters as much as the total: growth led by consumers and investment is sturdier than growth led by inventories or trade swings.",
     "The post includes consumer spending on health services, one of the largest and steadiest pieces of consumption."),
    ("JOLTS (job openings and labor turnover)", "Bureau of Labor Statistics", "Monthly · 10:00 ET",
     "Unfilled job openings, hires, layoffs and the quits rate.",
     "The demand side of the labor market. The Fed watches openings per unemployed worker as its tightness gauge, and a falling quits rate means workers are less sure they can find something better, which cools wage growth.",
     "Openings, hires and quits are shown for health care and social assistance. High openings with high quits mean staffing shortages, which show up as wage and contract-labor costs at hospitals and services companies."),
    ("PPI (producer prices)", "Bureau of Labor Statistics", "Monthly · 8:30 ET",
     "Prices that domestic producers receive, headline and core (final demand).",
     "Inflation in the pipeline. Cost changes here tend to reach consumer prices later, and several PPI lines feed directly into the calculation of core PCE, so forecasters use this release to sharpen their PCE estimate.",
     "Shown for hospitals, physician offices, dentist offices, pharmaceutical manufacturing and surgical and medical instruments. These are the prices providers and manufacturers actually receive, and the health-services lines are source data for PCE healthcare inflation."),
    ("Retail sales", "Census Bureau", "Monthly · 8:30 ET",
     "Receipts at stores, online sellers and restaurants, in nominal dollars, with an inflation-adjusted version.",
     "The first hard number on consumer spending each month, well ahead of the fuller PCE report. It feeds straight into running estimates of GDP.",
     ""),
    ("Employment Cost Index", "Bureau of Labor Statistics", "Quarterly · 8:30 ET",
     "Change in total compensation (wages plus benefits), holding the mix of jobs constant.",
     "The cleanest wage-inflation measure, and the one the Fed trusts most, because shifts in who is employed do not distort it the way they distort average hourly earnings.",
     "Labor is the largest cost line for hospitals and healthcare services. The benefits component also captures what employers pay for health insurance."),
]

TIER_B = [
    ("Industrial production and capacity utilization", "Federal Reserve", "Monthly · 9:15 ET",
     "Physical output of factories, mines and utilities, and the share of industrial capacity in use.",
     "The goods-producing side of the economy, which swings harder than services through a cycle. Sustained high utilization signals pressure to invest and to raise prices.", ""),
    ("Housing starts and building permits", "Census Bureau", "Monthly · 8:30 ET",
     "New homes begun in the month and permits issued for future building, at annual rates.",
     "Housing is the most rate-sensitive part of the economy, so it is where Fed policy bites first. Permits lead starts, and both lead the broader cycle.", ""),
    ("Durable goods orders", "Census Bureau", "Monthly · 8:30 ET",
     "New orders for long-lasting goods. The line to watch is core capital goods (non-defense, excluding aircraft).",
     "Core capital goods orders are the leading indicator of business investment. The headline is noisy because single aircraft orders move it.", ""),
    ("Trade balance", "Bureau of Economic Analysis and Census Bureau", "Monthly · 8:30 ET",
     "Exports minus imports of goods and services.",
     "Swings in the gap feed directly into the GDP arithmetic, and it is where tariff effects appear first, as importers pull orders forward or cut them back.",
     "Pharmaceuticals are among the larger US import categories, so drug tariff changes show up in these figures."),
    ("Consumer credit", "Federal Reserve", "Monthly · 3:00 PM ET",
     "Household borrowing outside mortgages: credit cards (revolving), auto loans and student loans.",
     "Shows whether spending is being paid for out of income or with debt. Fast growth in card balances while incomes are flat is a warning about how long spending can last.", ""),
    ("Loan delinquency rates", "Federal Reserve", "Quarterly · 4:30 PM ET",
     "Share of bank loans 30 or more days past due, led by credit cards, with consumer loans and mortgages.",
     "A direct gauge of household financial stress. Rising delinquencies come before cuts in spending and tighter bank lending.", ""),
    ("Productivity and unit labor costs", "Bureau of Labor Statistics", "Quarterly · 8:30 ET",
     "Output per hour worked, and labor cost per unit of output.",
     "Productivity is what lets wages rise without inflation. When unit labor costs climb, companies either take lower margins or raise prices.", ""),
    ("University of Michigan consumer sentiment", "University of Michigan", "Monthly · 10:00 ET",
     "A survey of how households view their finances and the economy, plus the inflation they expect over the next year.",
     "Survey data rather than hard data, but the inflation-expectations figure matters to the Fed: once households expect higher inflation it becomes harder to bring down.", ""),
    ("ADP employment report", "ADP", "Monthly · 8:15 ET",
     "Private-sector jobs added, counted from ADP's payroll records.",
     "A preview of the official jobs report two days later. The two often disagree in a given month, so it sets expectations more than it settles them.",
     "The post includes the education and health services line."),
    ("Gas prices", "Energy Information Administration", "Weekly, Monday · 5:00 PM ET",
     "Average US pump price for regular gasoline.",
     "The most visible price households pay. It drives the swings in headline CPI and moves consumer sentiment. Posted only when the move is unusual.", ""),
    ("Mortgage rates", "Freddie Mac", "Weekly, Thursday · 12:00 PM ET",
     "Average rates on 30-year and 15-year fixed mortgages.",
     "The channel through which Fed policy and the 10-year Treasury yield reach households. It sets housing affordability. Posted only when the move is unusual.", ""),
    ("Existing home sales", "National Association of Realtors", "Monthly · 10:00 ET",
     "Closed sales of previously owned homes, at an annual rate.",
     "Most housing turnover is existing homes. Each sale also triggers spending on moving, furnishing and renovation.", ""),
    ("New home sales", "Census Bureau", "Monthly · 10:00 ET",
     "Signed contracts on newly built single-family homes, at an annual rate.",
     "Counted at contract signing rather than closing, so it reacts to rate changes a month or two before existing home sales do. It is the demand read for homebuilders.", ""),
    ("Construction spending", "Census Bureau", "Monthly · 10:00 ET",
     "Dollar value of construction put in place: residential, non-residential and public.",
     "The non-residential line tracks the build-out of data centers and factories, a large part of current business investment.", ""),
]

FED = [
    ("FOMC decision and statement", "Federal Reserve", "Eight meetings a year · 2:00 PM ET",
     "The policy rate decision, with a line-by-line comparison of the statement against the previous one.",
     "The policy rate anchors every other interest rate. Changes in the statement's wording are how the committee signals its next move before making it.", ""),
    ("Fed speeches", "Federal Reserve and regional banks", "Daily, when given",
     "Speeches by Fed governors and bank presidents, each summarized and tagged by stance.",
     "Between meetings, speeches are how officials move market expectations. A shift in tone across several speakers usually comes before a shift in policy.", ""),
    ("Fed research digest", "Federal Reserve and regional banks", "Daily, when published",
     "New research notes and papers from the Fed system, filtered to macro topics.",
     "Staff research shows what questions the Fed is working on and often previews the arguments that later appear in speeches.", ""),
]

GLOBAL = [
    ("CPI and core CPI (year over year)", "Eurostat · ONS · OECD · e-Stat", "Monthly",
     "Consumer price inflation over the past 12 months in each region. Core leaves out energy and food.",
     "Each central bank sets rates against its own inflation. When inflation paths split from the US, interest-rate gaps move, and those gaps drive the dollar and global bond yields.", ""),
    ("GDP (year over year)", "Eurostat · ONS · OECD", "Quarterly",
     "Real output compared with the same quarter a year earlier.",
     "Demand outside the US. It matters for the overseas revenue of US multinationals, including large pharma and medical-device companies with big European and Asian sales.", ""),
    ("Unemployment rate", "Eurostat · ONS", "Monthly",
     "Share of the labor force without work.",
     "Tight labor markets keep wage growth and services inflation high, which is what holds the ECB and the Bank of England back from cutting.", ""),
    ("Business confidence", "OECD", "Monthly",
     "An index where 100 is the long-run average for that country. Above 100 means firms are more upbeat than usual.",
     "A forward-looking read on hiring and investment plans, comparable across regions because every country is scaled the same way.", ""),
    ("Policy rate", "ECB · Bank of England · Bank of Japan", "Shown with the date it last changed",
     "The central bank's main interest rate.",
     "The gap between these rates and the Fed's rate is the main driver of exchange rates. The Bank of Japan matters more than its size suggests: as it raises rates, Japanese investors bring money home.", ""),
    ("Government bond yields (2-year and 10-year)", "ECB · Bank of England · CFETS · FRED", "Daily or monthly",
     "What governments pay to borrow. The 2-year follows expected central-bank policy; the 10-year adds growth, inflation and debt concerns. Change is shown since the end of last year.",
     "Bond markets are linked. A rise in Japanese or UK long yields tends to pull US long yields up too, and US long yields set the discount rate for equities.", ""),
]

REGIONS = [
    ("Eurozone", "The largest developed economy outside the US and a major market for US drug and device makers."),
    ("United Kingdom", "The stickiest inflation among the large economies, and a gilt market that reacts sharply to budget news."),
    ("China", "Weak prices at home are exported to the rest of the world through cheaper goods. Also a large market and supplier for pharma and medical technology."),
    ("Japan", "Leaving decades of near-zero rates. Rising Japanese yields pull capital out of US and European bonds."),
]


def esc(s):
    return html.escape(s, quote=True)


def card(row, tier):
    name, source, when, what, why, hc = row
    tag = {"A": '<span class="tag a">Tier A</span>', "B": '<span class="tag b">Tier B</span>'}.get(tier, "")
    hc_html = f'<dt class="hc">Healthcare read</dt><dd class="hc">{esc(hc)}</dd>' if hc else ""
    return f'''<article class="m" data-text="{esc((name + " " + source + " " + what + " " + why + " " + hc).lower())}">
  <header><h3>{esc(name)}</h3><p class="meta">{tag}<span>{esc(when)}</span><span>{esc(source)}</span></p></header>
  <dl><dt>What it is</dt><dd>{esc(what)}</dd><dt>Why it matters</dt><dd class="why">{esc(why)}</dd>{hc_html}</dl>
</article>'''


def section(anchor, title, blurb, rows, tier=""):
    cards = "\n".join(card(r, tier) for r in rows)
    return f'''<section id="{anchor}" class="grp">
  <div class="grp-head"><h2>{esc(title)}</h2><p>{esc(blurb)}</p></div>
  {cards}
</section>'''


regions = "".join(f"<li><b>{esc(n)}</b> {esc(t)}</li>" for n, t in REGIONS)
n_total = len(TIER_A) + len(TIER_B) + len(FED) + len(GLOBAL)

PAGE = f'''<title>Why Each Macro Measure Matters</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: one reading column; each measure is a two-column row (name and
   schedule on the left, what / why / healthcare read on the right). */
:root {{
  --bg: #f6f8f9; --surface: #ffffff; --fg: #17232b; --muted: #5a6b76; --line: #d9e0e4;
  --accent: #0b6e69; --accent-soft: #e2f1ef; --hc: #8a4a12; --hc-soft: #fbf0e3;
  --sans: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #10181c; --surface: #172229; --fg: #e4ecef; --muted: #96a7b1; --line: #2a3941;
  --accent: #5cc7bf; --accent-soft: #15332f; --hc: #e7a96a; --hc-soft: #33261a; color-scheme: dark }} }}
:root[data-theme="dark"] {{
  --bg: #10181c; --surface: #172229; --fg: #e4ecef; --muted: #96a7b1; --line: #2a3941;
  --accent: #5cc7bf; --accent-soft: #15332f; --hc: #e7a96a; --hc-soft: #33261a; color-scheme: dark }}
body {{ background: var(--bg); color: var(--fg); font: 16px/1.55 var(--sans); }}
.wrap {{ max-width: 60rem; margin: 0 auto; padding-block: 2rem 4rem;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
h1 {{ font-size: 1.9rem; line-height: 1.2; font-weight: 600; margin: 0 0 .5rem; text-wrap: balance; }}
.lede {{ color: var(--muted); max-width: 42rem; margin: 0 0 1.25rem; }}
.tools {{ display: flex; flex-wrap: wrap; gap: .75rem 1rem; align-items: center; margin-bottom: 1rem; }}
#q {{ flex: 1 1 14rem; min-width: 0; font: inherit; padding: .5rem .7rem; border: 1px solid var(--line);
  border-radius: 6px; background: var(--surface); color: var(--fg); }}
#q:focus-visible, a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
nav {{ display: flex; flex-wrap: wrap; gap: .4rem 1rem; font: 500 .8rem var(--mono); }}
nav a {{ color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; }}
nav a:hover {{ border-bottom-color: var(--accent); }}
#count {{ font: .8rem var(--mono); color: var(--muted); }}
.grp {{ margin-top: 2.5rem; }}
.grp-head {{ border-bottom: 2px solid var(--fg); padding-bottom: .5rem; }}
.grp-head h2 {{ font-size: 1.2rem; font-weight: 600; margin: 0; }}
.grp-head p {{ margin: .2rem 0 0; color: var(--muted); font-size: .9rem; max-width: 44rem; }}
.m {{ display: grid; grid-template-columns: minmax(0, 15rem) minmax(0, 1fr); gap: .5rem 2rem;
  padding: 1.1rem 0; border-bottom: 1px solid var(--line); }}
.m h3 {{ font-size: 1rem; font-weight: 600; margin: 0 0 .4rem; text-wrap: balance; }}
.meta {{ margin: 0; display: flex; flex-direction: column; gap: .2rem; align-items: flex-start;
  font: .75rem/1.4 var(--mono); color: var(--muted); }}
.tag {{ font-weight: 500; padding: .05rem .4rem; border-radius: 3px; letter-spacing: .03em; }}
.tag.a {{ background: var(--accent); color: var(--bg); }}
.tag.b {{ border: 1px solid var(--muted); color: var(--muted); }}
dl {{ margin: 0; display: grid; gap: .15rem; min-width: 0; }}
dt {{ font: 500 .7rem var(--mono); text-transform: uppercase; letter-spacing: .07em; color: var(--muted); margin-top: .5rem; }}
dt:first-child {{ margin-top: 0; }}
dd {{ margin: 0; max-width: 40rem; }}
dd.why {{ font-weight: 500; }}
dt.hc {{ color: var(--hc); }}
dd.hc {{ background: var(--hc-soft); padding: .45rem .65rem; border-radius: 4px; font-size: .93rem; }}
.note {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 1rem 1.2rem; margin-top: 1rem; }}
.note ul {{ margin: .3rem 0 0; padding-left: 1.1rem; }}
.note li {{ margin: .25rem 0; max-width: 42rem; }}
#none {{ color: var(--muted); padding: 2rem 0; }}
@media (max-width: 40rem) {{
  .m {{ grid-template-columns: minmax(0, 1fr); }}
  .meta {{ flex-direction: row; flex-wrap: wrap; gap: .2rem .7rem; }}
  h1 {{ font-size: 1.5rem; }}
}}
</style>
<div class="wrap">
  <h1>Why each macro measure matters</h1>
  <p class="lede">Every release and reading posted to #macro, with what it measures, why a markets reader should care, and what it says about healthcare where it says something specific.</p>
  <div class="tools">
    <input id="q" type="search" placeholder="Filter, e.g. inflation, wages, hospitals" aria-label="Filter measures">
    <span id="count">{n_total} measures</span>
  </div>
  <nav aria-label="Sections">
    <a href="#tier-a">US Tier A ({len(TIER_A)})</a><a href="#tier-b">US Tier B ({len(TIER_B)})</a>
    <a href="#fed">Federal Reserve ({len(FED)})</a><a href="#global">Global macro ({len(GLOBAL)})</a><a href="#reading">Reading a post</a>
  </nav>

  {section("tier-a", "US releases, Tier A", "Always posted in full the moment they are released. These move markets or bear directly on the Fed.", TIER_A, "A")}
  {section("tier-b", "US releases, Tier B", "Posted as one line, or in full when the move is unusual against five years of history.", TIER_B, "B")}
  {section("fed", "Federal Reserve", "What the Fed decides and says between data releases.", FED)}
  {section("global", "Global macro", "The Sunday digest. The same six readings for the Eurozone, United Kingdom, China and Japan.", GLOBAL)}
  <div class="note" id="regions"><b>Why these four regions</b><ul>{regions}</ul></div>
  <p id="none" hidden>No measure matches that filter.</p>

  <section id="reading" class="grp">
    <div class="grp-head"><h2>Reading a post</h2></div>
    <div class="note"><ul>
      <li><b>Tier A or Tier B</b> is shown in the title of every release post.</li>
      <li><b>A sigma figure</b> such as "0.3σ move" compares this month's change with the typical change over the past five years. One sigma or more is unusual, and a Tier B release then posts in full.</li>
      <li><b>MoM annualized</b> is the one-month change scaled to a yearly rate. It shows the current pace; year over year shows the past 12 months.</li>
      <li><b>In the global digest</b> each line gives the value, the period it covers, and the change from the previous reading. "pt" means percentage points.</li>
      <li><b>A star</b> in the daily reminder marks the three priority topics: consumer spending, employment and real hourly earnings.</li>
    </ul></div>
  </section>
</div>
<script>
(function () {{
  var q = document.getElementById("q"), items = [].slice.call(document.querySelectorAll(".m")),
      groups = [].slice.call(document.querySelectorAll("section.grp")), count = document.getElementById("count"),
      none = document.getElementById("none"), regions = document.getElementById("regions");
  q.addEventListener("input", function () {{
    var t = q.value.trim().toLowerCase(), shown = 0;
    items.forEach(function (el) {{ var ok = !t || el.dataset.text.indexOf(t) !== -1; el.hidden = !ok; if (ok) shown++; }});
    groups.forEach(function (g) {{ var ms = g.querySelectorAll(".m"); if (ms.length) g.hidden = !g.querySelector(".m:not([hidden])"); else g.hidden = !!t; }});
    regions.hidden = !!t;
    none.hidden = shown !== 0;
    count.textContent = t ? shown + " of " + items.length + " measures" : items.length + " measures";
  }});
}})();
</script>
'''
OUT.write_text(PAGE, encoding="utf-8", newline="\n")
print(OUT, len(PAGE), n_total)
