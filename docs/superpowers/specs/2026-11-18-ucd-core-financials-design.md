# Design: `ucd-core-financials` skill

Date: 2026-11-18. Author: Claude, for Brett Phinney. Status: awaiting Brett's approval.

## Intent

Other UC Davis core facilities that bill through PPMS (Stratocore) should be able to
get the same financial figures and reports the Proteomics Core built in 2026, from
their own exports, without redoing the months of trial and error.

The skill does two jobs, in this order:

1. **Tell the core which reports to pull and how** (Aggie Enterprise and PPMS).
2. **Turn those exports into the figures and reports.**

Why Brett wants this was not stated. My assumption: cores can understand their own
finances and bring comparable figures to Cores Connect and RCCI.

## Goals

- A core director with Claude Code or Claude Cowork installs the skill, answers a
  short setup, drops exports in a folder, and gets finished output.
- The same input gives the same numbers every time, on any core.
- Every figure passes reconciliation checks before it is shown.
- A core with only some of the reports gets the sections those reports support,
  plus a written list of what to pull for the rest.

## Non-goals

- No live connection to Aggie Enterprise or PPMS. The user exports files by hand.
- No rate-setting or rate-calculation workbook.
- No cross-core comparison or pooled database. Each core runs on its own data.
- No Proteomics-specific work (survey lists, estimates, short course, publications).

## Anti-goals (failure even if it runs)

- Any real Proteomics Core number, PI name or staff name in the public repo.
- A figure that is wrong in a way campus budget staff would catch. Known traps from
  our own work are listed under "Rules carried over".
- Personnel pay detail, or card-holder and traveller names, in an output meant for
  staff or other cores.

## Approaches considered

1. **Instructions only.** The skill is a written spec and Claude writes new code per
   core. Fast to make, but numbers can differ between runs and between cores.
2. **Bundled scripts plus a per-core settings file. Chosen.** Parsing and arithmetic
   are tested Python in the repo. Claude runs setup, runs the scripts, handles odd
   exports, and writes the narrative. Numbers are reproducible and comparable.
3. **Standalone app with no Claude.** Breaks when an export layout changes; not a
   skill. Dropped.

Brett was shown these and did not object to option 2; it is my recommendation, not
his explicit pick.

## What the user does

1. **Install.** Clone the repo and link it into `~/.claude/skills/`.
2. **Setup.** Claude asks for the core's name, Financial Department code, project
   number, and funds, and writes `core-config.yaml` in the user's working folder.
   Funds and personnel accounts are proposed from the GL export once one is present,
   then confirmed by the user.
3. **Get the reports.** Claude gives the pull guide for each report with the core's
   own codes filled in, and a request the user can forward to their finance staff.
4. **Check what's there.** A script inventories the folder: which reports it found,
   the date range each covers, and gaps (the "reports I need" list).
5. **Build.** Scripts compute and render. Claude reports the reconciliation results
   and any caveats.

## Inputs

| Report | Source | Feeds |
|---|---|---|
| UCD Transaction Listing Report – GL and Subledger Detail | Aggie Enterprise | Dashboard, assessment, Sankey, per-$1 split |
| PO spend report (supplier, item, charge account) | Aggie Enterprise | "Companies paid" by account and fiscal year |
| Department P&L, `Balances` sheet | Finance staff | Official fund balances |
| GLIDE report | Aggie Enterprise | Card, travel and freight spend by category |
| Order details report | PPMS | Usership and RCCI tables |

Only the GL listing is required for the dashboard, and only the Order details report
for usership. Everything else adds sections.

Pull guides are written from `How_to_Pull_Aggie_Enterprise_Reports.docx`,
`reports I need.md` and `PRIMARY_DATA_SOURCES.md`, generalised (one month per run for
the wide subledger version, direct report link, KB0010829). Where our notes do not
record an exact click-path (PO spend report, GLIDE, P&L), the guide says so and gives
the request wording to send to finance staff instead of inventing steps.

## Outputs (version 1)

1. **Financial dashboard**, one self-contained HTML file: everything in §8 of
   `Proteomics_Dashboard_Regeneration_Spec.md`.
2. **Staff edition** of the dashboard, with personnel detail deleted from the file.
3. **Shareable figures** as PNG and SVG for slides: follow-the-money Sankey, per-$1
   split, and assessment by fiscal year. These show percentages and per-$1 values
   only, no dollar revenue.
4. **Usership workbook** (`.xlsx`): overview by fiscal year, groups by customer
   category, top PI groups, revenue by service, and the RCCI Table 1 and Table 2
   layout.
5. **Reports-needed list** (`.md`) with coverage dates and request wording.
6. **New figures** (below), in the dashboard and as PNG/SVG.

### New figures (Brett asked for "new awesome figures that would be useful")

Each one is marked **share** (safe for other cores: percentages, ratios, counts) or
**internal** (shows dollars or names).

| Figure | Data | Question it answers | Audience |
|---|---|---|---|
| Cost recovery by fiscal year: earned revenue ÷ operating expense, with a 100% line | GL | How close is the core to paying its own way? | share |
| Customer mix over time, stacked to 100% (UCD, other UC, external academic, industry, government) | PPMS | Who is the core serving, and is that shifting? | share |
| Customer breadth curve: share of revenue from the top 5, 10, 20 PI groups | PPMS | Does the core depend on a few labs? | share (no names) |
| New vs returning PI groups per fiscal year | PPMS | Is the core winning new users or living on regulars? | share |
| Turnaround time: days from accepted to completed, by service and by quarter | PPMS | Is service getting faster or slower? | share |
| Open orders over time (accepted, not yet completed) | PPMS | How big is the backlog, and when does it build? | share |
| Month × fiscal-year heatmap of orders | PPMS | When are the busy and quiet months? | share |
| Fund balance over time: running balance by month, with the official P&L ending balance marked | GL + P&L | When did the core go into or out of deficit? | internal |
| Bridge chart: beginning balance → revenue → expense → assessment → ending balance | P&L + GL | What moved the balance this year? | internal |
| Supplier concentration: top suppliers' share of non-personnel spend | PO report | Where does most of the non-salary money go? | internal |

The RCCI college/department table needs each PI mapped to a college. The config
holds that mapping. Claude proposes it from the `Fin Account` chartstring where it
can and asks the user to confirm the rest.

## Rules carried over from the Proteomics work

These are the points where our first versions were wrong or nearly wrong.

- Sign handling by first digit of `Account`: 4 and 7 are income (flip sign), 5 is
  expense, 3 (`300001` carry-forward) is excluded and shown for reference only.
- **Assessment is accounts 770009 and 775004 only.** Bad-debt contra `445100` is
  reported on its own line, never added to the assessment. (Our July dashboard added
  it and overstated the assessment.)
- Assessment is checked against 15% of external sales (`410000`) month by month, and
  the match rate is reported.
- Fiscal year is July to June. Partial years are labelled, and no "rising" or
  "falling" statement compares a partial year with a full one.
- PO amounts are committed, not posted. Show both totals side by side.
- PPMS revenue counts accepted or completed orders only; unconverted quotes are
  reported separately.
- PI and group names are case-folded before counting.
- Customer category comes from the `Fin Account` field (`EXTERNAL - …`, UCD
  chartstring, other), with an override table in the config for the ones that need a
  person to decide.
- Wording about the assessment is neutral by default. A core can add its own.
- GLIDE output is category totals only.

## Repository

`github.com/bsphinney/ucd-core-financials-skill`, public, cloned to
`~/ucd-core-financials-skill` (outside iCloud Drive).

```
SKILL.md                    when to use, the five steps, the rules above
reference/pulling-reports.md
reference/calculations.md   the generalised dashboard spec
reference/config.md
scripts/                    inventory, GL, PPMS, dashboard, figures, staff redaction
assets/                     HTML template, inlined chart libraries, palette
sample-data/                made-up exports for a fictional core
tests/                      run the scripts on sample data, assert the checks
README.md                   install and a worked example
```

## Constraints

- Python 3 with pandas, openpyxl, xlrd, matplotlib. No network calls at run time.
- Dashboard libraries (Chart.js, treemap, sankey) are inlined, as now.
- Default colours are the validated palette from the spec; the core name and two
  brand colours are configurable.
- Sample data is generated by a script with a fixed seed, in the real column layouts.

### Extras (Brett chose all four, 2026-11-18)

- **Unbilled order check.** List PPMS order lines that are accepted or completed but
  have `Invoiced - Y/N` = N, with the total. Internal only.
- **Year-end forecast.** Project the fiscal year-end fund balance from the
  year-to-date pace, with a low/high range taken from the same months in earlier
  years. Shown as internal; labelled a projection.
- **One-page summary.** Claude writes a plain-English page (`summary.md`, and
  `.docx` if asked) for a chair or advisory board, using only computed numbers:
  what changed this year, cost recovery, customer mix, backlog, risks. Every number
  in it must trace to a script output.
- **Shared benchmark file.** `benchmark.csv` in a fixed format holding only
  share-safe values (percentages, ratios, counts, days): cost recovery %, assessment
  per $1, customer mix %, top-10 concentration %, new-group %, median turnaround.
  The repo also ships a small script that combines several cores' files into a
  side-by-side comparison for Cores Connect. A test checks that the benchmark file
  holds no dollar amounts and no names.

## Settled after the builder review (my calls unless marked)

- **Packaging (Brett: both).** The repo works for Claude Code (clone and link into
  `~/.claude/skills/`). A release script also builds a zip to upload as a skill in
  claude.ai or Claude desktop. The scripts must run in Claude's sandbox: they check
  for pandas, openpyxl, xlrd and matplotlib and install them if missing, and they
  inline all chart libraries.
- **Customer affiliation (Brett not sure of a PPMS report).** First guess from
  `Fin Account`: `EXTERNAL - <email>` is external and a UCD chartstring is UC Davis.
  For external groups, an email domain ending in a UC campus domain is Ext-UC, and
  `.edu`, `.org` or `.gov` is Ext-NP. Everything else is left for the user. Claude
  writes `affiliations.csv` with the guesses and asks the core to confirm or fix the
  uncertain ones; that file is the record from then on. The same file holds each
  UC Davis PI's college and department for RCCI Table 2. If a core finds a PPMS
  report with affiliation, the loader uses it instead. Totals come from the Order
  details report; the guide notes that PPMS's own Usership Summary can differ by a
  few percent because it includes credits and adjustments.

- **GL layout.** The loader accepts both the 34-column `page` export (the dashboard
  needs only this) and the wide 58-column subledger export (adds supplier detail).
  Several monthly files are combined; exact duplicate rows are dropped and the
  inventory reports overlapping periods.
- **What is per core and what is campus-wide.** Campus-wide defaults live in
  `reference/ucd-chart-of-accounts.yaml`: assessment accounts 770009/775004, contra
  445100, carry-forward 300001, revenue accounts 775000/410000/775B*/785*, expense
  groups, and the 15% assessment rate. Each core's `core-config.yaml` sets its funds
  and their roles, personnel accounts, and any overrides. The sample core uses a
  different fund set from Proteomics, so the code can't assume our four funds.
- **PPMS fields.** Revenue = `Price`. Fiscal year from `Date Ordered` (as in the
  Proteomics reconciliation). Orders count only if `Date Accepted` or
  `Date Completed` is filled; the rest are reported as unconverted quotes.
- **RCCI tables.** These copy the campus template
  (`RCCI 2026 usage data template 2026_04_21.xlsx`):
  - Table 1 has one row per PI: Core, PI Affiliation, PI College/School,
    PI Department, PI Name, Spend, Volume.
  - Table 2 is spend and % by college for UC Davis PIs, plus Ext-UC, Ext-NP and
    Ext-FP.
  - The date window is a setting.
- **Per-$1 figure.** Defined from the GL so every core can make it: of each $1 of
  gross revenue, how much went to personnel, supplies and services, other operating,
  the campus assessment, and surplus or deficit. (The Proteomics slide used numbers
  from our BIA rate package, which other cores won't have in the same form.)
- **Sankey.** In the dashboard and staff edition it shows dollars. The shareable
  PNG/SVG shows percent of gross revenue. A test fails if a shareable figure contains
  a dollar amount.
- **Failed checks.** Outputs are still written, but each failed check appears as a
  red banner in the dashboard and in Claude's summary. Arithmetic checks
  (income − expense = net, Sankey balance) must match to the cent. The assessment
  match rate is reported, not enforced.

## Left to the builder

- Script boundaries and names, config field names, test layout.
- How the dashboard template is filled (the current HTML is the visual reference).
- Whether the shareable figures are drawn with matplotlib or exported from the page.

## My calls for Brett to check

- Public repo with only made-up data (Brett confirmed 2026-11-18).
- Which of the new figures are labelled "share" versus "internal".
- Option 2 (bundled scripts).
- Neutral assessment wording.
- Shareable figures never show dollar revenue.
- Version 1 leaves out the 5-year deficit forecast and the RCCI Financial History
  template; both could be a later addition.
