"""Build readable/why_each_measure_matters.html -- the #macro channel bookmark.

Published as the artifact https://claude.ai/artifact/PszYN4CLpyYsPoNnAAjrzN
(bookmark "Why each measure matters" in #macro, added 2026-11-12). To update:
edit the rows below, run `python readable/build_why_page.py readable/why_each_measure_matters.html`,
then republish that file to the SAME artifact URL so the bookmark keeps working.

Three things have to stay in step with the code, and nothing enforces it:
  * a release family added to config/release_families.yaml needs a row here,
    with one TX series row per headline, component and computed series and
    its transform keys copied from that family's primary_transform /
    also_display / context.anchor_transform / context.trends;
  * a figure added to ahead_of_curve/figures.yaml needs a row in ELLIS (the
    script asserts the two id sets match, so that one does fail loudly);
  * every link points at the public site, https://jroypeterson.github.io/macro-monitor/.
"""
import html
import pathlib
import sys
import urllib.parse

OUT = pathlib.Path(sys.argv[1])
HERE = pathlib.Path(__file__).resolve().parent

SITE = "https://jroypeterson.github.io/macro-monitor/"
DASH = ("US dashboard (latest value and mini-chart)", SITE + "dashboard/")
GROWTH = SITE + "market/growth.html"
INTL = ("Global macro dashboard", SITE + "international/")


def rep(slug):
    return ("Latest release report, with charts", SITE + "latest/" + urllib.parse.quote(slug) + ".html")


def ell(fig_id, title):
    return ("Ellis chart: " + title, SITE + "ahead_of_curve/#" + fig_id)


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

# Transformation glossary: key -> (short tag, full name, definition). A series
# row names the keys applied to it, so the per-entry "Transformations (N)" list
# and its count are derived, never typed.
T = {
    "level": ("as published", "As published", "The figure the agency publishes, with no further arithmetic here."),
    "mom_ann": ("MoM annualized", "Month over month, annualized", "The one-month percent change compounded to a yearly rate. It shows the current pace."),
    "mom": ("MoM %", "Month over month, percent", "Percent change from the prior month."),
    "yoy": ("YoY %", "Year over year, percent", "Percent change against the same month or quarter a year earlier."),
    "qoq": ("QoQ annualized", "Quarter over quarter, annualized", "The one-quarter percent change compounded to a yearly rate."),
    "trend": ("3m and 6m annualized", "3-month and 6-month annualized", "The percent change over the last three and six months, each scaled to a yearly rate. Separates one noisy month from a change of pace."),
    "trend3": ("3m annualized", "3-month annualized", "The percent change over the last three months, scaled to a yearly rate."),
    "avg36": ("3m and 6m average", "3-month and 6-month average change", "The average monthly change over the last three and six months."),
    "mom_chg": ("change vs last month", "Change from the prior month, in units", "This month minus last month, in the series' own unit: thousands of jobs, dollars, index points, or percentage points for a rate."),
    "yoy_chg": ("change vs a year ago", "Change from a year ago, in units", "This period minus the same period a year earlier, in the series' own unit. Percentage points for a rate."),
    "wk": ("vs 4 and 52 weeks ago", "Change against 4 and 52 weeks ago", "Percent change against about four weeks ago and 52 weeks ago. Used for weekly series in place of month over month and year over year."),
    "prev": ("change vs previous reading", "Change from the previous reading", "The latest value minus the one before it, with both periods named. In percentage points for a rate."),
    "sum": ("sum", "Sum of several series", "Added together here. The agency does not publish this total as one series."),
    "real": ("deflated", "Divided by a price index", "A dollar series divided by a price index, which removes inflation and leaves the volume."),
    "accel": ("change in growth", "Change in growth over 12 months", "The year-over-year growth rate minus the same rate 12 months earlier, in percentage points. Above zero means growth is speeding up."),
    "accel13": ("speeding up or slowing", "Growth against one and three months ago", "Whether the year-over-year rate is higher or lower than it was one month ago and three months ago."),
    "sigma": ("sigma score", "Sigma score on the move", "The latest change divided by the typical change over the past five years. One or more is unusual; a Tier B release then posts in full."),
    "sigma_level": ("sigma score on level", "Sigma score on the level", "How far the level itself sits from its five-year average, in units of its usual spread."),
    "mavg": ("monthly average", "Monthly average", "Daily values averaged over the month."),
    "log": ("log scale", "Log scale", "Plotted so that equal distances are equal percent moves."),
    "ytd_bp": ("change since year-end", "Change since year-end, in basis points", "The yield minus its value on the last trading day of the prior year. One basis point is a hundredth of a percentage point."),
    "since": ("date of last change", "Date of last change", "Stored as the dates the rate changed, so the line reads 'last changed' with the size of that move. An old date means no change, not stale data."),
    "diff": ("sentence comparison", "Sentence-by-sentence comparison", "Each sentence is matched against the previous statement, and what was added, removed or reworded is listed."),
}

# Series, subsets and transformations, keyed by measure name.
#   "s": [(series or subset, note, "transform keys")]  -- ONE ROW PER SERIES.
#   "n": [(label, note)]                                -- caveats about the release as a whole.
# US rows mirror config/release_families.yaml (primary_transform, also_display,
# context.anchor_transform, context.trends, computed); global rows mirror
# international/series.yaml.
TX = {
    "CPI": {"s": [
        ("Headline CPI", "The full basket, seasonally adjusted. The lead figure is the annualized one-month change, and the sigma score is measured on it.", "mom_ann yoy mom trend sigma"),
        ("Core CPI", "Subset: all items less food and energy, about 80% of the basket.", "mom_ann yoy mom"),
        ("Shelter", "Subset: rent and the rent-equivalent cost of owning a home. About a third of the basket.", "yoy"),
        ("Food", "Subset: groceries and restaurants.", "yoy"),
        ("Energy", "Subset: gasoline, electricity and gas.", "yoy"),
        ("Medical care services", "Subset: hospitals, physicians, dentists and health insurance.", "yoy"),
        ("Hospital services", "A subset of medical care services.", "yoy"),
        ("Physician and dental services", "A subset of medical care services. Not seasonally adjusted, which year over year neutralizes.", "yoy"),
        ("Medical care goods", "Subset: mostly prescription drugs, plus equipment.", "yoy"),
    ], "n": [
        ("Charts", "Year over year, five years and 25 years, against the Fed's 2% line."),
    ]},
    "Employment Situation (jobs report)": {"s": [
        ("Nonfarm payrolls", "All jobs except farms, from the survey of employers. The lead figure is the change in jobs from last month, in thousands, and the sigma score is measured on it.", "mom_chg yoy avg36 sigma"),
        ("Unemployment rate (U-3)", "The official rate: people with no job who looked for one in the past four weeks, as a percent of the labor force. From the household survey.", "level mom_chg yoy_chg"),
        ("Underemployment rate (U-6)", "U-3 plus people who want a job but have stopped looking, plus people working part time who want full time. The widest measure.", "level mom_chg yoy_chg"),
        ("Average hourly earnings", "All private-sector employees, in nominal dollars (not adjusted for inflation). The Ellis charts use a different wage series: production and nonsupervisory workers only, divided by CPI.", "yoy mom"),
        ("Ambulatory care jobs", "Subset: physician offices, outpatient centers, home health (industry code 621).", "yoy"),
        ("Hospital jobs", "Subset: industry code 622.", "yoy"),
        ("Nursing and residential care jobs", "Subset: industry code 623.", "yoy"),
        ("Healthcare employment, total", "The three lines above added together. It leaves out social assistance.", "sum yoy mom_chg"),
        ("Professional and business services jobs", "Subset.", "yoy"),
        ("Information jobs", "Subset.", "yoy"),
        ("Financial activities jobs", "Subset.", "yoy"),
        ("White-collar employment, total", "The three lines above added together, a proxy for office jobs.", "sum yoy mom_chg accel13"),
    ], "n": [
        ("Two surveys", "Payrolls and earnings come from a survey of employers; U-3 and U-6 come from a separate survey of households. They can disagree in a given month."),
    ]},
    "Consumer spending and PCE inflation": {"s": [
        ("Real consumer spending", "The government's inflation-adjusted (chained-dollar) series.", "yoy mom"),
        ("Nominal consumer spending", "In current dollars. The gap between nominal and real is inflation.", "yoy mom"),
        ("PCE price index, headline", "The lead figure is the annualized one-month change, and the sigma score is measured on it.", "mom_ann yoy mom trend sigma"),
        ("PCE price index, core", "Subset: less food and energy. The inflation measure the Fed watches most closely.", "mom_ann yoy mom"),
        ("Personal income", "Nominal, before taxes.", "yoy mom"),
        ("Real disposable income", "After taxes and after inflation, so it is the figure that bounds spending.", "yoy mom"),
        ("Saving rate", "Saving as a percent of after-tax income.", "level"),
    ], "n": [
        ("Versus the Ellis charts", "Ellis's real spending is built as nominal spending divided by the PCE price index, so the history reaches back to 1959. The government's chained-dollar series used in the post starts in 2007. The two track closely."),
    ]},
    "Initial jobless claims": {"s": [
        ("Initial claims", "The weekly count of new filings, seasonally adjusted. The sigma score is on the week's change.", "level wk sigma"),
        ("Continued claims", "People still collecting benefits. Runs one week behind initial claims.", "level"),
    ], "n": [
        ("Charts", "Two years for the recent turn, five years for the level in context."),
    ]},
    "GDP": {"s": [
        ("Real GDP growth", "Published as quarter over quarter, seasonally adjusted, at an annual rate. The sigma score is on the change in that rate from the prior quarter.", "level sigma"),
        ("Nominal GDP growth", "The same, in current dollars: real growth plus inflation.", "level"),
        ("Real GDP, level", "The dollar level behind the headline, shown on a different basis from it.", "yoy"),
        ("Consumer spending (real)", "Subset of GDP.", "yoy"),
        ("Private investment (real)", "Subset of GDP.", "yoy"),
        ("Government (real)", "Subset of GDP.", "yoy"),
        ("Health services spending", "Subset of consumer spending, in nominal dollars.", "yoy qoq"),
    ], "n": [
        ("Two bases", "The headline is annualized quarterly growth; the components are year over year. Do not compare them directly: 2% year over year and 2% annualized quarterly growth are different statements."),
        ("Three estimates", "Each quarter is published three times (advance, second, third) a month apart. The later posts are revisions of the same quarter."),
        ("Versus the Ellis charts", "Ellis plots real GDP year over year, built as nominal GDP divided by the GDP price deflator."),
    ]},
    "JOLTS (job openings and labor turnover)": {"s": [
        ("Job openings", "The count of unfilled jobs, in thousands.", "level yoy mom_chg"),
        ("Quits rate", "Quits in the month as a percent of total employment.", "level mom_chg yoy_chg"),
        ("Job openings rate", "Openings as a percent of filled jobs plus openings. The sigma score is on this line, because it adjusts for the size of the workforce.", "level sigma"),
        ("Hires", "Count, in thousands.", "level"),
        ("Layoffs and discharges", "Count, in thousands.", "level"),
        ("Healthcare openings rate", "Subset: health care and social assistance (industry code 62).", "level mom_chg yoy_chg"),
        ("Healthcare hires rate", "Subset: the same group.", "level mom_chg yoy_chg"),
        ("Healthcare quits rate", "Subset: the same group.", "level mom_chg yoy_chg"),
    ], "n": [
        ("Healthcare coverage", "Industry code 62 includes social assistance, so it is a wider group than the healthcare job count in the jobs report."),
        ("Timing", "Covers the month before the one in the latest jobs report."),
    ]},
    "PPI (producer prices)": {"s": [
        ("Headline PPI", "Final demand. The lead figure is the annualized one-month change, and the sigma score is measured on it.", "mom_ann yoy mom trend sigma"),
        ("Core PPI", "Subset: final demand less food and energy.", "mom_ann yoy mom"),
        ("Hospitals", "Industry price index: what hospitals receive.", "yoy"),
        ("Physician offices", "Industry price index.", "yoy"),
        ("Dentist offices", "Industry price index.", "yoy"),
        ("Drug makers", "Industry price index for pharmaceutical manufacturing. A list-price measure: it does not capture rebates.", "yoy"),
        ("Medical device makers", "Industry price index for surgical and medical instruments.", "yoy"),
    ], "n": [
        ("Seasonal adjustment", "The five healthcare lines are not seasonally adjusted, which year over year neutralizes."),
    ]},
    "Retail sales": {"s": [
        ("Retail sales", "Stores, online sellers and restaurants, seasonally adjusted, in nominal dollars, so part of any rise is price. The sigma score is on the monthly change.", "mom yoy trend3 sigma"),
        ("Real retail sales", "The same series divided by CPI. This is the volume read.", "real yoy mom"),
    ], "n": [
        ("Coverage", "Mostly goods plus restaurants. It leaves out most services, which are about two thirds of consumer spending."),
    ]},
    "Employment Cost Index": {"s": [
        ("Total compensation", "Wages plus benefits for all civilian workers, including state and local government. Year over year is the lead figure and the basis of the sigma score.", "yoy qoq sigma"),
        ("Wages and salaries", "Subset: private industry only.", "yoy"),
        ("Benefits", "Subset: private industry only.", "yoy"),
    ], "n": [
        ("Different groups", "The two components cover private industry, a narrower group than the headline, so they do not average to it."),
    ]},
    "Industrial production and capacity utilization": {"s": [
        ("Industrial production", "An index (2017 = 100) of output at factories, mines and utilities. The sigma score is on the year-over-year rate.", "yoy mom sigma"),
        ("Capacity utilization", "The percent of industrial capacity in use.", "level mom_chg yoy_chg"),
    ], "n": [
        ("Versus the Ellis charts", "The post uses total industry. The Ellis charts use manufacturing only."),
    ]},
    "Housing starts and building permits": {"s": [
        ("Housing starts", "Homes begun, as a seasonally adjusted annual rate, in thousands. Single-family and apartment buildings combined.", "yoy mom sigma"),
        ("Building permits", "Permits issued, on the same basis. Leads starts.", "yoy mom"),
    ], "n": [
        ("Noise", "Single months swing widely with weather and apartment projects, which is why the lead figure is year over year."),
    ]},
    "Durable goods orders": {"s": [
        ("Durable goods orders", "New orders, nominal dollars, seasonally adjusted. The sigma score is on the monthly change.", "mom yoy sigma"),
        ("Core capital goods orders", "Subset: non-defense capital goods excluding aircraft.", "yoy mom"),
    ]},
    "Trade balance": {"s": [
        ("Trade balance", "Exports minus imports, goods and services together, in millions of nominal dollars. Negative is a deficit.", "level mom_chg yoy_chg sigma"),
    ], "n": [
        ("Why dollars, not percent", "A percent change of a negative number misleads, so changes are given in dollars."),
    ]},
    "Consumer credit": {"s": [
        ("Total consumer credit", "The outstanding balance: the stock of debt, not the month's new borrowing.", "yoy mom sigma"),
        ("Revolving credit", "Subset: mostly credit cards.", "yoy"),
    ], "n": [
        ("Coverage", "Excludes mortgages and other loans secured by real estate."),
    ]},
    "Loan delinquency rates": {"s": [
        ("Credit card delinquency rate", "The lead line: the percent of card balances 30 or more days past due.", "level yoy_chg sigma_level"),
        ("Consumer loan delinquency rate", "All consumer loans, of which cards are a subset.", "level"),
        ("Single-family mortgage delinquency rate", "Subset: home loans.", "level"),
        ("All-loan delinquency rate", "Every loan type, including business loans.", "level"),
    ], "n": [
        ("Coverage", "Commercial banks only, seasonally adjusted."),
        ("Full post rule", "This is the one release judged on its level against five years of history, not on the size of the latest move, because stress shows in how high the rate is."),
    ]},
    "Productivity and unit labor costs": {"s": [
        ("Productivity", "Output per hour worked. Year over year is the lead figure and the basis of the sigma score; the quarterly rate is far noisier.", "yoy qoq sigma"),
        ("Unit labor costs", "Hourly compensation growth minus productivity growth.", "yoy qoq"),
    ], "n": [
        ("Coverage", "The nonfarm business sector, which leaves out government, nonprofits and farms."),
    ]},
    "University of Michigan consumer sentiment": {"s": [
        ("Sentiment index", "A level (first quarter of 1966 = 100). The change from last month is in index points.", "level yoy mom_chg sigma"),
        ("Expected inflation", "The median expected price change over the next 12 months, in percent.", "level"),
    ], "n": [
        ("Two readings a month", "A preliminary figure mid-month and a final one at month end."),
    ]},
    "ADP employment report": {"s": [
        ("Private payrolls", "Private employers only, so no government jobs. The sigma score is on the monthly change.", "mom_chg yoy avg36 sigma"),
        ("Education and health services", "Subset, and wider than healthcare: it includes private schools and colleges.", "mom_chg yoy"),
    ]},
    "Gas prices": {"s": [
        ("Regular gasoline", "The US average, in dollars per gallon.", "level wk sigma"),
    ], "n": [
        ("Posting rule", "Judged on the 52-week change against five years of history. Nothing is posted in an ordinary week."),
    ]},
    "Mortgage rates": {"s": [
        ("30-year fixed rate", "The weekly average from Freddie Mac's lender survey, in percent.", "level wk sigma"),
        ("15-year fixed rate", "The shorter standard loan, from the same survey.", "level wk"),
    ], "n": [
        ("Posting rule", "Judged on the 52-week change of the 30-year rate. Nothing is posted in an ordinary week."),
    ]},
    "Existing home sales": {"s": [
        ("Existing home sales", "Closed sales of previously owned homes, as a seasonally adjusted annual rate.", "yoy mom"),
    ], "n": [
        ("No sigma score", "The public data source carries only the last 13 months of this series, so the move cannot be compared with five years of history. It always posts as one line."),
    ]},
    "New home sales": {"s": [
        ("New home sales", "Signed contracts on new single-family homes, as a seasonally adjusted annual rate.", "yoy mom sigma"),
    ], "n": [
        ("Revisions", "A small sample, so the first figure is often revised by a large amount."),
    ]},
    "Construction spending": {"s": [
        ("Total construction spending", "A seasonally adjusted annual rate in nominal dollars. Rising building costs lift it without any more building.", "yoy mom sigma"),
        ("Private construction", "Subset: excludes public works.", "yoy"),
        ("Non-residential construction", "Subset: offices, factories, data centers, hospitals, roads.", "yoy"),
    ]},
    "FOMC decision and statement": {"s": [
        ("Federal funds target range", "As announced.", "level"),
        ("Statement text", "Compared with the previous meeting's statement.", "diff"),
    ]},
    "CPI and core CPI (year over year)": {"s": [
        ("Eurozone headline", "The harmonized index (HICP), which leaves out the cost of owning a home. Published as a 12-month rate.", "level prev"),
        ("Eurozone core", "Subset: excludes energy, food, alcohol and tobacco.", "level prev"),
        ("United Kingdom headline", "CPI, published as a 12-month rate.", "level prev"),
        ("United Kingdom core", "Subset: the same core definition as the Eurozone.", "level prev"),
        ("China headline", "Published as a 12-month rate. No core series is collected.", "level prev"),
        ("Japan headline", "The 12-month rate is computed here from Japan's price index. No core series is collected.", "yoy prev"),
    ], "n": [
        ("Not comparable with US CPI", "US CPI includes owners' housing costs; the European measures do not."),
    ]},
    "GDP (year over year)": {"s": [
        ("Eurozone", "Real output against the same quarter a year earlier, seasonally adjusted, as published.", "level prev"),
        ("United Kingdom", "The same basis.", "level prev"),
        ("China", "The same basis.", "level prev"),
    ], "n": [
        ("Not the US basis", "The US headline is quarter over quarter annualized, so do not compare the two directly."),
        ("Coverage", "Japan's GDP is not collected."),
    ]},
    "Unemployment rate": {"s": [
        ("Eurozone", "Monthly, seasonally adjusted, in percent.", "level prev"),
        ("United Kingdom", "A three-month average for people 16 and over, published about two months behind.", "level prev"),
    ], "n": [
        ("Coverage", "China and Japan are not collected."),
    ]},
    "Business confidence": {"s": [
        ("Eurozone", "The OECD's index, already scaled so that 100 is the long-run average. No unit; the change is in index points.", "level prev"),
        ("United Kingdom", "The same index and scaling.", "level prev"),
        ("China", "The same index and scaling.", "level prev"),
        ("Japan", "The same index and scaling.", "level prev"),
    ]},
    "Policy rate": {"s": [
        ("Eurozone", "The European Central Bank's main refinancing rate.", "since"),
        ("United Kingdom", "The Bank of England's Bank Rate.", "since"),
        ("Japan", "The overnight call rate, which follows the Bank of Japan's target closely.", "mavg prev"),
    ], "n": [
        ("Coverage", "China is not collected."),
    ]},
    "Government bond yields (2-year and 10-year)": {"s": [
        ("Eurozone 2-year", "The ECB's curve for AAA-rated euro governments, close to German yields and lower than French or Italian yields.", "ytd_bp"),
        ("Eurozone 10-year", "The same curve.", "ytd_bp"),
        ("United Kingdom 10-year", "The 10-year gilt.", "ytd_bp"),
        ("Japan 10-year", "The 10-year government bond.", "mavg ytd_bp"),
        ("China 2-year", "From the official interbank curve. The source gives only the latest day, so no change since year-end is shown.", "level"),
        ("China 10-year", "The same curve and the same limit.", "level"),
    ], "n": [
        ("Missing", "The UK and Japan have no 2-year source yet."),
    ]},
}
for _name, _d in TX.items():
    for _row in _d["s"]:
        assert all(k in T for k in _row[2].split()), (_name, _row[0])

P_PCE = "Consumer spending and PCE inflation"
P_JOBS = "Employment Situation (jobs report)"
E = {  # Ellis figure id -> short title used in link labels
    "real_pce_yoy": "real consumer spending", "pce_accel": "spending, speeding up or slowing",
    "pce_leads_capex": "spending leads capital spending", "capex_accel": "capital spending, speeding up or slowing",
    "pce_vs_employment": "spending and employment", "employment_wages_spending": "employment, wages and spending",
    "real_earnings_vs_spending": "real hourly earnings and spending", "earnings_accel": "real earnings, speeding up or slowing",
    "rates_vs_bears": "interest rates and bear markets", "real_gdp_yoy": "economic growth and the cycle",
    "pce_vs_industrial_production": "spending and industrial production",
    "industrial_production_vs_capex": "industrial production and capital spending",
    "real_earnings_vs_inflation": "inflation and real hourly earnings",
    "employment_borrowing_earnings": "employment, borrowing and earnings",
    "consumer_sentiment": "consumer sentiment", "saving_rate": "the saving rate",
    "unemployment_vs_bears": "unemployment and bear markets", "unemployment_vs_spending": "unemployment and spending",
    "inflation_vs_rates": "inflation and interest rates", "growth_and_stock_market": "growth and the stock market",
    "real_earnings_and_stock_market": "real earnings and the stock market",
    "long_rates_and_stock_market": "long rates and the stock market",
    "bear_recession_timeline": "bear market and recession timeline",
}


def ells(*ids):
    return [ell(i, E[i]) for i in ids]


# Where else each measure is charted, keyed by measure name.
LINKS = {
    "CPI": [rep("cpi"), DASH] + ells("real_earnings_vs_inflation", "inflation_vs_rates") + [
        ("Drug-price inflation, consumer vs producer", SITE + "drug_prices/")],
    P_JOBS: [rep("employment_situation"), DASH] + ells(
        "pce_vs_employment", "employment_wages_spending", "real_earnings_vs_spending", "earnings_accel",
        "unemployment_vs_bears", "unemployment_vs_spending") + [("Growth page: unemployment rate", GROWTH)],
    P_PCE: [rep("consumer_spending_—_personal_consumption_expenditures_(pce)___personal_income_and_outlays"), DASH]
    + ells("real_pce_yoy", "pce_accel", "pce_leads_capex", "saving_rate")
    + [("Growth page: real consumer spending", GROWTH)],
    "Initial jobless claims": [rep("initial_jobless_claims"), DASH],
    "GDP": [rep("gdp"), DASH] + ells("real_gdp_yoy", "growth_and_stock_market", "capex_accel") + [
        ("Growth page: real GDP and capital spending", GROWTH),
        ("Federal spending and health spending, as a share of GDP", SITE + "fiscal/")],
    "JOLTS (job openings and labor turnover)": [rep("jolts"), DASH],
    "PPI (producer prices)": [rep("ppi"), DASH, ("Drug-price inflation, consumer vs producer", SITE + "drug_prices/")],
    "Retail sales": [rep("retail_sales"), DASH] + ells("real_pce_yoy"),
    "Employment Cost Index": [rep("employment_cost_index"), DASH] + ells("real_earnings_vs_spending"),
    "Industrial production and capacity utilization": [rep("industrial_production"), DASH] + ells(
        "pce_vs_industrial_production", "industrial_production_vs_capex") + [
        ("Growth page: industrial production", GROWTH)],
    "Housing starts and building permits": [rep("housing_starts_and_permits"), DASH],
    "Durable goods orders": [rep("durable_goods_orders"), DASH] + ells("pce_leads_capex", "capex_accel"),
    "Trade balance": [rep("trade_balance"), DASH],
    "Consumer credit": [rep("consumer_credit"), DASH] + ells("employment_borrowing_earnings"),
    "Loan delinquency rates": [rep("loan_delinquency_rates"), DASH],
    "Productivity and unit labor costs": [rep("productivity_and_unit_labor_costs"), DASH],
    "University of Michigan consumer sentiment": [rep("umich_consumer_sentiment"), DASH] + ells("consumer_sentiment"),
    "ADP employment report": [rep("adp_national_employment_report"), DASH] + ells("pce_vs_employment"),
    "Gas prices": [rep("gas_prices_(us_regular,_avg)"), DASH],
    "Mortgage rates": [rep("mortgage_rates_(30yr_and_15yr_fixed)"), DASH] + ells("long_rates_and_stock_market"),
    "Existing home sales": [rep("existing_home_sales"), DASH],
    "New home sales": [rep("new_home_sales"), DASH],
    "Construction spending": [rep("construction_spending"), DASH],
    "FOMC decision and statement": ells("rates_vs_bears") + [
        ("US dashboard: Treasury curve", SITE + "dashboard/"),
        ("Prediction markets: Fed and rate odds", SITE + "prediction_markets/")],
    "Fed speeches": [("Prediction markets: Fed and rate odds", SITE + "prediction_markets/")],
    "CPI and core CPI (year over year)": [INTL],
    "GDP (year over year)": [INTL],
    "Unemployment rate": [INTL],
    "Business confidence": [INTL],
    "Policy rate": [INTL],
    "Government bond yields (2-year and 10-year)": [INTL, ("US dashboard: Treasury curve", SITE + "dashboard/")],
}

RELEASE_NAMES = {r[0] for r in TIER_A + TIER_B + FED + GLOBAL}
assert set(TX) <= RELEASE_NAMES, set(TX) - RELEASE_NAMES
assert set(LINKS) <= RELEASE_NAMES, set(LINKS) - RELEASE_NAMES
assert {r[0] for r in TIER_A + TIER_B + GLOBAL} <= set(TX) & set(LINKS), "every release needs TX and LINKS"

YOY = "percent change against the same month a year earlier"
YOYQ = "percent change against the same quarter a year earlier"
ACCEL = "The year-over-year growth rate minus the same rate 12 months earlier, in percentage points. Above zero means growth is speeding up."
REAL_PCE = ("Real consumer spending", "Nominal consumer spending divided by the PCE price index, then the " + YOY + ". Monthly.")
REAL_CAPEX = ("Real capital spending", "Business investment in buildings, equipment and software (private non-residential fixed investment) divided by the GDP price deflator, then the " + YOYQ + ". Quarterly.")
REAL_AHE = ("Real hourly earnings", "Average hourly earnings of production and nonsupervisory workers (about four fifths of private employees) divided by CPI, then the " + YOY + ".")
EMPLOY = ("Employment", "Civilian employment from the household survey, the " + YOY + ". This is not the payrolls figure in the jobs post.")
SPX = ("S&P 500", "Month-end level on a log scale (right axis), so equal distances are equal percent moves.")
MFG = ("Industrial production", "Manufacturing output only (the post uses total industry), the " + YOY + ".")

# (figure id, title, book figure or "", what it shows, why it matters, [(series, how built)], [release names it draws on])
ELLIS = [
    ("real_pce_yoy", "Real consumer spending, year over year", "",
     "Growth in inflation-adjusted consumer spending against a year earlier.",
     "The centerpiece of the framework. Consumer spending is about two thirds of the economy and sits at the head of the chain: production, capital spending and hiring follow it. Peaks in this line, while growth is still positive, have come before bear markets.",
     [REAL_PCE], [P_PCE]),
    ("pce_accel", "Real consumer spending: speeding up or slowing", "",
     "Whether spending growth is higher or lower than it was a year ago.",
     "The early warning is slower growth, not a decline. This line crosses below zero when spending growth starts to fade, well before spending itself falls.",
     [("Change in growth", ACCEL)], [P_PCE]),
    ("pce_leads_capex", "Consumer spending leads capital spending", "",
     "Real consumer spending growth against real business investment growth.",
     "The book's core lead and lag. Companies add capacity after they see demand, so capital spending turns after consumer spending does. A capital-spending boom is late-cycle news, not a fresh signal.",
     [REAL_PCE, REAL_CAPEX], [P_PCE, "GDP", "Durable goods orders"]),
    ("capex_accel", "Real capital spending: speeding up or slowing", "",
     "Whether business investment growth is higher or lower than a year ago.",
     "Shows where capital spending is in its own cycle. Read it after the spending chart: it should follow with a lag.",
     [("Change in growth", ACCEL + " Quarterly.")], ["GDP", "Durable goods orders"]),
    ("pce_vs_employment", "Consumer spending and employment", "",
     "Real consumer spending growth against employment growth.",
     "Employment follows spending. Companies hire after demand has risen and cut after it has fallen, so a strong jobs report confirms what spending already showed. It does not forecast.",
     [REAL_PCE, EMPLOY], [P_PCE, P_JOBS]),
    ("employment_wages_spending", "Employment, wage growth and consumer spending", "Fig 11-11",
     "Employment growth and real hourly earnings growth against real consumer spending growth.",
     "Household income is the number of people working times what each is paid. This chart puts both inputs next to the spending they pay for.",
     [EMPLOY, REAL_AHE, REAL_PCE], [P_JOBS, "CPI", P_PCE]),
    ("real_earnings_vs_spending", "Real hourly earnings and consumer spending", "",
     "Growth in inflation-adjusted hourly pay against real consumer spending growth.",
     "Ellis treats real hourly earnings as the main driver of spending, and so the indicator furthest ahead. It is one of the three priority topics starred in the daily reminder.",
     [REAL_AHE, REAL_PCE], [P_JOBS, "CPI", P_PCE]),
    ("earnings_accel", "Real hourly earnings: speeding up or slowing", "",
     "Whether real hourly earnings growth is higher or lower than a year ago.",
     "The earliest turn in the chain. When this falls below zero, purchasing power is fading and spending growth is likely to follow.",
     [("Change in growth", ACCEL)], [P_JOBS, "CPI"]),
    ("rates_vs_bears", "Interest rates and bear markets", "",
     "The Fed's policy rate and the 10-year Treasury yield against the record of bear markets.",
     "Rising rates have come before most bear markets. In the framework they work through the consumer: higher borrowing costs and the inflation that prompts them both cut into spending.",
     [("Fed funds rate", "The Fed's policy rate, a level in percent."), ("10-year Treasury yield", "A level in percent.")],
     ["FOMC decision and statement"]),
    ("real_gdp_yoy", "Economic growth and the cycle", "Fig 4-1",
     "Real GDP growth against a year earlier.",
     "Bear markets begin while growth is still positive but slowing. Waiting for a recession, which is declared after the fact, means acting late.",
     [("Real GDP", "Nominal GDP divided by the GDP price deflator, then the " + YOYQ + ". The GDP post leads with quarter over quarter annualized, a different basis.")],
     ["GDP"]),
    ("pce_vs_industrial_production", "Consumer spending and industrial production", "Fig 7-3",
     "Real consumer spending growth against manufacturing output growth.",
     "The second link in the chain. Factories produce what consumers order, so output follows spending and swings harder because inventories amplify the move.",
     [REAL_PCE, MFG], [P_PCE, "Industrial production and capacity utilization"]),
    ("industrial_production_vs_capex", "Industrial production and capital spending", "Fig 7-5",
     "Manufacturing output growth against real business investment growth.",
     "The third link. When plants run hard, companies invest in more capacity; when output slows, investment is cut.",
     [MFG, REAL_CAPEX], ["Industrial production and capacity utilization", "GDP"]),
    ("real_earnings_vs_inflation", "Inflation and real hourly earnings", "Fig 10-4",
     "Real hourly earnings growth against CPI inflation.",
     "Inflation is subtracted from pay. When inflation rises faster than wages, real earnings fall, and that is the route by which inflation hurts spending and then stocks.",
     [REAL_AHE, ("CPI inflation", "Headline CPI, the " + YOY + ". The same index deflates the earnings line, so the two mirror each other in part by construction.")],
     [P_JOBS, "CPI"]),
    ("employment_borrowing_earnings", "Employment, borrowing and hourly earnings", "Fig 10-9",
     "Employment growth, growth in total debt and real hourly earnings growth.",
     "The three sources of spending power: more people working, more borrowing, and higher real pay. Spending that leans on borrowing while real pay is flat is the least durable kind.",
     [EMPLOY, ("Total debt", "All debt owed in the US by households, businesses, governments and financial firms, the " + YOYQ + ". Quarterly, and published about three months behind. It is far wider than the consumer credit release."), REAL_AHE],
     [P_JOBS, "Consumer credit", "CPI"]),
    ("consumer_sentiment", "Consumer sentiment", "Fig 9-3",
     "The University of Michigan sentiment index.",
     "A check on whether how people say they feel adds anything to what their pay and jobs already show. Read it against the spending chart.",
     [("Sentiment index", "A level (first quarter of 1966 = 100). Not transformed.")],
     ["University of Michigan consumer sentiment"]),
    ("saving_rate", "The saving rate", "Supplemental",
     "Personal saving as a share of after-tax income.",
     "A low or falling saving rate means spending is running ahead of income, which leaves less room to keep spending when income slows.",
     [("Saving rate", "A level in percent. Not transformed.")], [P_PCE]),
    ("unemployment_vs_bears", "Unemployment and bear markets", "Fig 11-8",
     "The unemployment rate against the record of bear markets and recessions.",
     "Unemployment is a lagging indicator. It is usually near its low when a bear market starts and still rising after the market has turned up, so it is the wrong thing to wait for.",
     [("Unemployment rate", "The official (U-3) rate, a level in percent. Not transformed.")], [P_JOBS]),
    ("unemployment_vs_spending", "Unemployment and consumer spending", "Fig 11-6",
     "Real consumer spending growth (left axis) against the unemployment rate (right axis).",
     "Shows the order of events: spending growth turns first, and the unemployment rate follows.",
     [REAL_PCE, ("Unemployment rate", "A level in percent on the right axis. One line is a growth rate and the other a level, so compare turning points, not heights.")],
     [P_PCE, P_JOBS]),
    ("inflation_vs_rates", "Inflation and interest rates", "Fig 12-4",
     "CPI inflation against the 10-year Treasury yield.",
     "Long-term rates follow inflation. Inflation therefore hits stocks twice: through lower real earnings and through a higher discount rate.",
     [("CPI inflation", "Headline CPI, the " + YOY + "."), ("10-year Treasury yield", "A level in percent, monthly average.")],
     ["CPI"]),
    ("growth_and_stock_market", "Economic growth, recessions and the stock market", "Fig 4-1",
     "Real GDP growth (left axis) against the S&P 500 (right axis).",
     "Puts the market next to the growth rate so the timing is visible: the market falls as growth slows, ahead of the recession.",
     [("Real GDP", "Nominal GDP divided by the GDP price deflator, then the " + YOYQ + "."), SPX], ["GDP"]),
    ("real_earnings_and_stock_market", "Real hourly earnings and the stock market", "Fig 10-10",
     "Real hourly earnings growth (left axis) against the S&P 500 (right axis).",
     "Links the earliest indicator in the chain directly to the market it is meant to anticipate.",
     [REAL_AHE, SPX], [P_JOBS, "CPI"]),
    ("long_rates_and_stock_market", "Long-term interest rates and the stock market", "Fig 13-3",
     "The 10-year Treasury yield (left axis) against the S&P 500 (right axis).",
     "Long rates set the discount rate on future earnings and the return on the alternative to stocks. Sustained rises have gone with weaker markets.",
     [("10-year Treasury yield", "A level in percent, monthly average."), SPX], []),
    ("bear_recession_timeline", "Bear markets and recessions: timeline", "Reference",
     "Every S&P 500 bear market and every official recession, with no economic series.",
     "The backdrop for the other charts. Bear markets and recessions overlap but are not the same events, and several bear markets came with no recession.",
     [("Bear markets (grey bands)", "Peak-to-trough declines of about 20% or more in the S&P 500, 13 since 1946, dated by hand to the month."),
      ("Recessions (dotted red)", "The National Bureau of Economic Research's official dates.")], []),
]


def _figure_ids():
    import yaml  # the repo's own dependency; only needed for this cross-check

    spec = yaml.safe_load((HERE.parent / "ahead_of_curve" / "figures.yaml").read_text(encoding="utf-8"))
    return [f["id"] for f in spec["figures"]]


# Transform keys for each Ellis series label (the note says what the line is; this says what was done to it).
EK = {
    "Real consumer spending": "real yoy", "Real capital spending": "real yoy", "Real hourly earnings": "real yoy",
    "Real GDP": "real yoy", "Employment": "yoy", "Industrial production": "yoy", "CPI inflation": "yoy",
    "Total debt": "yoy", "Change in growth": "accel", "S&P 500": "log", "Fed funds rate": "mavg",
    "10-year Treasury yield": "mavg", "Sentiment index": "level", "Saving rate": "level", "Unemployment rate": "level",
    "Bear markets (grey bands)": "", "Recessions (dotted red)": "",
}
assert {k for r in ELLIS for k, _ in r[5]} == set(EK), {k for r in ELLIS for k, _ in r[5]} ^ set(EK)
assert all(k in T for v in EK.values() for k in v.split())
assert [r[0] for r in ELLIS] == _figure_ids(), "ELLIS rows must match ahead_of_curve/figures.yaml, in order"
assert set(E) == {r[0] for r in ELLIS}
assert all(n in RELEASE_NAMES for r in ELLIS for n in r[6])


def esc(s):
    return html.escape(s, quote=True)


def slug(name):
    return "m-" + "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def tx_html(series, notes=()):
    """One bullet per series with its transform tags, any release-wide notes,
    then a collapsed list of every distinct transform and the series it is applied to."""
    used = {}
    lis = []
    for label, note, keys in series:
        tags = "".join(f"<span>{esc(T[k][0])}</span>" for k in keys.split())
        for k in keys.split():
            used.setdefault(k, []).append(label)
        tag_html = f'<span class="tf">{tags}</span>' if tags else ""
        lis.append(f"<li><b>{esc(label)}.</b> {esc(note)}{tag_html}</li>")
    out = (f'<dd class="tfs"><details><summary>Series and subsets ({len(series)})</summary>'
           f'<ul class="tx">{"".join(lis)}</ul></details></dd>')
    if notes:
        nl = "".join(f"<li><b>{esc(k)}.</b> {esc(v)}</li>" for k, v in notes)
        out += f'<dt>Notes</dt><dd><ul class="tx">{nl}</ul></dd>'
    if used:
        tl = "".join(
            f'<li><b>{esc(T[k][1])}.</b> {esc(T[k][2])}<span class="on">Applied to: {esc(", ".join(on))}</span></li>'
            for k, on in used.items())
        out += (f'<dd class="tfs"><details><summary>Transformations ({len(used)})</summary>'
                f'<ul class="tx">{tl}</ul></details></dd>')
    return out


def tx_text(series, notes=()):
    words = [f"{a} {b} " + " ".join(T[k][1] for k in keys.split()) for a, b, keys in series]
    return words + [k + " " + v for k, v in notes]


def links_html(label, links):
    out = []
    for text, url in links:
        ext = "" if url.startswith("#") else ' target="_blank" rel="noopener"'
        out.append(f'<li><a href="{esc(url)}"{ext}>{esc(text)}</a></li>')
    return f'<dt>{esc(label)}</dt><dd><ul class="links">{"".join(out)}</ul></dd>'


def card(row, tier):
    name, source, when, what, why, hc = row
    tag = {"A": '<span class="tag a">Tier A</span>', "B": '<span class="tag b">Tier B</span>'}.get(tier, "")
    hc_html = f'<dt class="hc">Healthcare read</dt><dd class="hc">{esc(hc)}</dd>' if hc else ""
    tx = TX.get(name, {"s": [], "n": []})
    series, notes = tx["s"], tx.get("n", [])
    links = LINKS.get(name, [])
    text = " ".join([name, source, what, why, hc] + tx_text(series, notes) + [t for t, _ in links]).lower()
    return f'''<article class="m" id="{slug(name)}" data-text="{esc(text)}">
  <header><h3>{esc(name)}</h3><p class="meta">{tag}<span>{esc(when)}</span><span>{esc(source)}</span></p></header>
  <dl><dt>What it is</dt><dd>{esc(what)}</dd><dt>Why it matters</dt><dd class="why">{esc(why)}</dd>{hc_html}
  {tx_html(series, notes) if series else ""}{links_html("On your other charts", links) if links else ""}</dl>
</article>'''


def ellis_card(row):
    fig_id, title, fig, what, why, built, releases = row
    built = [(k, v, EK[k]) for k, v in built]
    fig_html = f"<span>Book {esc(fig)}</span>" if fig.startswith("Fig") else (f"<span>{esc(fig)}</span>" if fig else "")
    links = [("Open this chart", SITE + "ahead_of_curve/#" + fig_id)] + [
        ("In this guide: " + n, "#" + slug(n)) for n in releases]
    text = " ".join([title, "ellis", fig, what, why] + tx_text(built) + releases).lower()
    return f'''<article class="m" id="e-{fig_id}" data-text="{esc(text)}">
  <header><h3>{esc(title)}</h3><p class="meta"><span class="tag e">Ellis chart</span>{fig_html}</p></header>
  <dl><dt>What it shows</dt><dd>{esc(what)}</dd><dt>Why it matters</dt><dd class="why">{esc(why)}</dd>
  {tx_html(built)}{links_html("Chart and the releases behind it", links)}</dl>
</article>'''


def section(anchor, title, blurb, rows, tier=""):
    cards = "\n".join(card(r, tier) for r in rows)
    return f'''<section id="{anchor}" class="grp">
  <div class="grp-head"><h2>{esc(title)}</h2><p>{esc(blurb)}</p></div>
  {cards}
</section>'''


regions = "".join(f"<li><b>{esc(n)}</b> {esc(t)}</li>" for n, t in REGIONS)
n_releases = len(TIER_A) + len(TIER_B) + len(FED) + len(GLOBAL)
n_total = n_releases + len(ELLIS)
ellis_cards = "\n".join(ellis_card(r) for r in ELLIS)

PAGE = f'''<title>Why Each Macro Measure Matters</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: one reading column; each measure is a two-column row (name and
   schedule on the left, what / why / healthcare read / series and subsets /
   notes / collapsed transformations / links on the right). */
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
html {{ scroll-behavior: smooth; }}
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
  padding: 1.1rem 0; border-bottom: 1px solid var(--line); scroll-margin-top: 1rem; }}
.m:target h3 {{ color: var(--accent); }}
.m h3 {{ font-size: 1rem; font-weight: 600; margin: 0 0 .4rem; text-wrap: balance; }}
.meta {{ margin: 0; display: flex; flex-direction: column; gap: .2rem; align-items: flex-start;
  font: .75rem/1.4 var(--mono); color: var(--muted); }}
.tag {{ font-weight: 500; padding: .05rem .4rem; border-radius: 3px; letter-spacing: .03em; }}
.tag.a {{ background: var(--accent); color: var(--bg); }}
.tag.b {{ border: 1px solid var(--muted); color: var(--muted); }}
.tag.e {{ border: 1px solid var(--accent); color: var(--accent); }}
dl {{ margin: 0; display: grid; gap: .15rem; min-width: 0; }}
dt {{ font: 500 .7rem var(--mono); text-transform: uppercase; letter-spacing: .07em; color: var(--muted); margin-top: .5rem; }}
dt:first-child {{ margin-top: 0; }}
dd {{ margin: 0; max-width: 40rem; }}
dd.why {{ font-weight: 500; }}
dt.hc {{ color: var(--hc); }}
dd.hc {{ background: var(--hc-soft); padding: .45rem .65rem; border-radius: 4px; font-size: .93rem; }}
ul.tx {{ margin: 0; padding: 0 0 0 .8rem; list-style: none; border-left: 2px solid var(--line); font-size: .93rem; }}
ul.tx li {{ margin: .3rem 0; }}
ul.tx b {{ font-weight: 600; }}
ul.tx .tf {{ display: inline; }}
ul.tx .tf span {{ display: inline-block; margin-left: .3rem; white-space: nowrap; }}
ul.tx .tf span {{ font: .7rem var(--mono); color: var(--muted); border: 1px solid var(--line); border-radius: 3px; padding: 0 .35rem; }}
ul.tx .on {{ display: block; color: var(--muted); font-size: .86rem; }}
dd.tfs {{ margin-top: .5rem; }}
details > summary {{ cursor: pointer; font: 500 .7rem var(--mono); text-transform: uppercase; letter-spacing: .07em;
  color: var(--accent); padding: .2rem 0; }}
details > summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
details[open] > summary {{ margin-bottom: .3rem; }}
ul.links {{ margin: 0; padding: 0; list-style: none; display: flex; flex-wrap: wrap; gap: .35rem .5rem; font-size: .86rem; }}
ul.links a {{ display: inline-block; padding: .15rem .55rem; border-radius: 4px; background: var(--accent-soft);
  color: var(--accent); text-decoration: none; overflow-wrap: anywhere; }}
ul.links a:hover {{ text-decoration: underline; }}
.note {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 1rem 1.2rem; margin-top: 1rem; }}
.note ul, .note ol {{ margin: .3rem 0 0; padding-left: 1.1rem; }}
.note li {{ margin: .25rem 0; max-width: 42rem; }}
.note a {{ color: var(--accent); }}
#none {{ color: var(--muted); padding: 2rem 0; }}
@media (max-width: 40rem) {{
  .m {{ grid-template-columns: minmax(0, 1fr); }}
  .meta {{ flex-direction: row; flex-wrap: wrap; gap: .2rem .7rem; }}
  h1 {{ font-size: 1.5rem; }}
}}
</style>
<div class="wrap">
  <h1>Why each macro measure matters</h1>
  <p class="lede">Every release and reading posted to #macro and every Joseph Ellis chart: what it measures, why a markets reader should care, how the numbers are transformed, and where else it is charted.</p>
  <div class="tools">
    <input id="q" type="search" placeholder="Filter, e.g. inflation, wages, hospitals" aria-label="Filter measures">
    <span id="count">{n_total} entries</span>
  </div>
  <nav aria-label="Sections">
    <a href="#tier-a">US Tier A ({len(TIER_A)})</a><a href="#tier-b">US Tier B ({len(TIER_B)})</a>
    <a href="#fed">Federal Reserve ({len(FED)})</a><a href="#global">Global macro ({len(GLOBAL)})</a>
    <a href="#ellis">Ellis charts ({len(ELLIS)})</a><a href="#reading">Reading a post</a>
  </nav>

  {section("tier-a", "US releases, Tier A", "Always posted in full the moment they are released. These move markets or bear directly on the Fed.", TIER_A, "A")}
  {section("tier-b", "US releases, Tier B", "Posted as one line, or in full when the move is unusual against five years of history.", TIER_B, "B")}
  {section("fed", "Federal Reserve", "What the Fed decides and says between data releases.", FED)}
  {section("global", "Global macro", "The Sunday digest. The same six readings for the Eurozone, United Kingdom, China and Japan.", GLOBAL)}
  <div class="note" id="regions"><b>Why these four regions</b><ul>{regions}</ul></div>

  <section id="ellis" class="grp">
    <div class="grp-head"><h2>Joseph Ellis charts (Ahead of the Curve)</h2>
      <p>The {len(ELLIS)} charts rebuilt from Joseph Ellis's book. The relevant ones are posted in the thread under each CPI, jobs, spending, GDP, industrial production and sentiment release.</p></div>
    <div class="note" id="ellis-frame"><b>The framework in four points</b><ol>
      <li><b>Watch the rate of change, not the level.</b> Almost every line is the percent change against a year earlier. Turning points in growth come well before turning points in the level.</li>
      <li><b>The economy moves in a fixed order.</b> Real hourly earnings and employment drive consumer spending. Consumer spending drives industrial production. Production drives capital spending. Hiring comes last, and feeds back into spending.</li>
      <li><b>Bear markets begin when growth slows, not when it turns negative.</b> By the time a recession is declared, most of the market damage is done.</li>
      <li><b>So the indicators furthest up the chain matter most.</b> Real hourly earnings and real consumer spending lead. Employment, unemployment and capital spending confirm.</li>
    </ol>
    <ul><li><b>Shading.</b> Grey bands are S&amp;P 500 bear markets; dotted red bands are official recessions. Each can be switched off on the chart page.</li>
      <li><b>Real</b> means adjusted for inflation: a dollar series divided by a price index. The charts do this division themselves so the history reaches back to 1959.</li>
      <li><b>All charts:</b> <a href="{SITE}ahead_of_curve/" target="_blank" rel="noopener">the full gallery</a>, with a 55-year window and each line's 1-year, 10-year and full-history average.</li></ul></div>
    {ellis_cards}
  </section>
  <p id="none" hidden>Nothing matches that filter.</p>

  <section id="reading" class="grp">
    <div class="grp-head"><h2>Reading a post</h2></div>
    <div class="note"><ul>
      <li><b>Tier A or Tier B</b> is shown in the title of every release post.</li>
      <li><b>A sigma figure</b> such as "0.3σ move" compares this month's change with the typical change over the past five years. One sigma or more is unusual, and a Tier B release then posts in full.</li>
      <li><b>MoM annualized</b> is the one-month change scaled to a yearly rate. It shows the current pace; year over year shows the past 12 months.</li>
      <li><b>Seasonally adjusted annual rate</b> means the month's or quarter's figure with the usual seasonal pattern removed, multiplied up to a full year. Home sales, housing starts, construction and GDP are quoted this way.</li>
      <li><b>Percent versus percentage points.</b> A series that is already a rate (unemployment, a delinquency rate, a yield) changes in percentage points. Everything else changes in percent.</li>
      <li><b>In the global digest</b> each line gives the value, the period it covers, and the change from the previous reading. "pt" means percentage points.</li>
      <li><b>A star</b> in the daily reminder marks the three priority topics: consumer spending, employment and real hourly earnings. They are the head of the Ellis chain.</li>
    </ul></div>
  </section>
</div>
<script>
(function () {{
  var q = document.getElementById("q"), items = [].slice.call(document.querySelectorAll(".m")),
      groups = [].slice.call(document.querySelectorAll("section.grp")), count = document.getElementById("count"),
      none = document.getElementById("none"), notes = [document.getElementById("regions"), document.getElementById("ellis-frame")];
  function apply() {{
    var t = q.value.trim().toLowerCase(), shown = 0;
    items.forEach(function (el) {{ var ok = !t || el.dataset.text.indexOf(t) !== -1; el.hidden = !ok; if (ok) shown++; }});
    groups.forEach(function (g) {{ var ms = g.querySelectorAll(".m"); if (ms.length) g.hidden = !g.querySelector(".m:not([hidden])"); else g.hidden = !!t; }});
    notes.forEach(function (n) {{ n.hidden = !!t; }});
    none.hidden = shown !== 0;
    count.textContent = t ? shown + " of " + items.length + " entries" : items.length + " entries";
  }}
  q.addEventListener("input", apply);
  /* A link to an entry that the filter has hidden would go nowhere: clear the filter first. */
  document.addEventListener("click", function (ev) {{
    var a = ev.target.closest && ev.target.closest('a[href^="#"]');
    if (a && q.value) {{ q.value = ""; apply(); }}
  }});
}})();
</script>
'''
OUT.write_text(PAGE, encoding="utf-8", newline="\n")
print(OUT, len(PAGE), n_releases, len(ELLIS))
