# Macro Data Inventory — Schema

A standing catalog of **every macro dataset we encounter** — whether or not we use it — so we
never re-discover the same source twice and can judge at a glance what exists, how fresh it is,
what it contains, and how hard it is to get. The source of truth is `datasets.yaml` (one entry
per dataset); this file defines the fields.

Modeled on `hc_macro_policy/data_inventory/SCHEMA.md`, adapted for general macro: the HC-subsector
spine is replaced by a macro `category` spine, and an `ellis_figures` field records which
*Ahead of the Curve* chart(s) each series feeds.

When exploring any new dataset, add an entry — even a stub. Fill `stats` once you've actually
probed it (row counts, date range, a latest value), and bump `last_inventoried`.

## Per-dataset fields

| Field | Req? | Meaning |
|---|---|---|
| `id` | ✓ | short snake/kebab slug, unique (e.g. `fred_real_pce`) |
| `name` | ✓ | full dataset/series name as the publisher calls it |
| `publisher` | ✓ | the org that produces it (BEA, BLS, Federal Reserve, U. Michigan, S&P…) |
| `publisher_type` | ✓ | `federal_gov` · `central_bank` · `academic_survey` · `trade_assoc` · `commercial_vendor` · `nonprofit_research` |
| `category` | ✓ | macro spine tag(s): `consumption` · `output` · `production` · `investment` · `labor` · `earnings` · `prices` · `rates` · `credit` · `debt` · `sentiment` · `markets` · `reference` |
| `url` | ✓ | landing page / documentation |
| `access` | ✓ | how to get it — object, see below |
| `cadence` | ✓ | `daily` · `weekly` · `monthly` · `quarterly` · `annual` · `irregular` |
| `release_timing` | | when in the cycle it drops (e.g. "~last business day of month") |
| `lag` | ✓ | typical reporting lag (e.g. "~1 month", "~5-6 weeks") |
| `revises` | | `true`/`false` + note if recent points are provisional |
| `coverage` | ✓ | what it contains — variables, population, methodology |
| `geography` | | `national` · `state` · `metro` |
| `time_span` | | earliest → latest available |
| `key_fields` | | the columns / series we care about |
| `transform` | | the Ellis lens applied for charting — almost always `yoy_roc` (year-over-year rate of change); `raw` for levels (e.g. rates) |
| `ellis_figures` | | which *Ahead of the Curve* figure(s) this series feeds (e.g. `7-3, 8-4`) |
| `stats` | | descriptive snapshot — object, see below (fill after probing) |
| `gaps` | ✓* | what it does NOT cover; caveats; provisional points (*required once `status` is `staged` or live) |
| `relevance` | ✓ | `high`/`medium`/`low` + one-line why for the cycle-forecasting process |
| `status` | ✓ | `in_charts` · `shipped` · `staged` · `candidate` · `rejected` · `not_evaluated` |
| `our_series` | | chart/series ids sourced from it, if any |
| `last_inventoried` | ✓ | ISO date we last characterized it |
| `notes` | | freeform (access gotchas, related series, why rejected…) |

### `access` object
| Key | Meaning |
|---|---|
| `method` | `fred` · `bea_api` · `bls_api` · `csv_download` · `excel_download` · `html_scrape` · `rest_api` · `manual_download` · `paid` |
| `detail` | the actual FRED id / API series id / endpoint / file name |
| `format` | `csv` · `json` · `excel` · `html` |
| `cost` | `free` · `freemium` · `paid` |
| `auth` | `none` · `api_key` · `login` |
| `effort` | `trivial` (one FRED id) · `low` · `moderate` · `high` |

### `stats` object (fill after probing)
| Key | Meaning |
|---|---|
| `observations` | number of periods present |
| `time_range` | earliest → latest observation actually present |
| `latest` | most recent value(s), with date — a concrete snapshot |
| `units` | unit of the headline measure |

## Status meanings
- **in_charts / shipped** — wired into an Ahead-of-the-Curve figure (`our_series` lists the chart ids).
- **staged** — data path confirmed (FRED id verified) + speced, chart not yet built (blocker in `notes`).
- **candidate** — identified, looks useful, not yet probed / no clean free path (e.g. proprietary).
- **rejected** — evaluated and dropped (say why in `notes`).
- **not_evaluated** — logged for completeness; haven't assessed.

_To regenerate a human-readable table from `datasets.yaml`, run
`python -m macro_monitor.data_inventory.render` (writes `readable/MACRO_DATA_INVENTORY.md`)._
