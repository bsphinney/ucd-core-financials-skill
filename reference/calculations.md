# How every figure is calculated

Campus-wide defaults (account codes, groups, rate) are in
`reference/ucd-chart-of-accounts.yaml`. A core can override any of them with
`coa_overrides:` in its `core-config.yaml`.

## Reading the ledger

- Rows are kept only for the funds listed in `core-config.yaml`.
- Identical rows pulled in two overlapping files are counted once. Genuinely repeated
  lines inside one file (two identical charges on one day) are both kept.
- When both GL exports are present, the **standard export is the ledger**. It carries
  one summary row per journal, while the wide "GL and Subledger Detail" export splits
  the same journal into invoice lines. Mixing them would double-count. Wide rows only
  supply supplier detail for each account's drill-down. A core with only wide exports
  uses them as the ledger.
- Fiscal year: July 1 – June 30, named by the year it ends (FY2026 = Jul 2025–Jun 2026).
  A fiscal year is *complete* only when all 12 months have rows.

## Sign and role of each account

The first digit of the account decides its role:

| First digit | Role | Sign in reports |
|---|---|---|
| 4, 7 | income | flipped, so revenue is positive |
| 5 | expense | as posted |
| 3 (300001) | carry-forward | excluded from every operating figure; listed for reference |

Special accounts override the digit rule:
- **Assessment**: 770009 and 775004 (Central Campus Income Assessment), shown as a cost.
- **Bad-debt write-offs**: 445100, reported on their own line and never added to the
  assessment.
- **Recharges paid out from revenue accounts** (an income-class account with a net
  debit, e.g. 770006): shown as a deduction, not as negative revenue.

## Core totals

- Gross revenue = sum of the revenue groups, before the assessment.
- Operating income = gross revenue − assessment − write-offs − deductions.
- Operating expense = class-5 accounts.
- Operating net = operating income − operating expense.
- Earned revenue = internal recharge (775000) + external sales (410000).
- Cost recovery = earned revenue ÷ operating expense, by fiscal year.

Every build checks these identities (see `checks.md`): income − expense = net; gross −
assessment − write-offs − deductions = income; Sankey inflow = outflow; expense groups
sum to expense; each group equals its accounts; PPMS revenue by year = total.

## Campus income assessment

- Total = accounts 770009 + 775004.
- Shown three ways: dollars per fiscal year (internal), cents per dollar of gross revenue
  (shareable), and share of external sales.
- **15% check.** For each month, the assessment *for* that month is compared with 15% of
  that month's external sales (410000), to the cent. The month comes from the journal
  name ("Campus Income Assessment - February 2024"), because campus posts each charge at
  the end of the following month; without a named month, the posting month is used.
  Months after the most recent charge are listed as "not yet charged", not as mismatches.

## Per-dollar split

For each complete fiscal year, every dollar of gross revenue is split into personnel,
supplies & services, other operating, campus assessment, and what is left (surplus) or
the shortfall (deficit). Buckets are set in `per_dollar_buckets`.

## Sankey

Revenue groups flow into the core; the core flows out to expense groups, the assessment,
bad-debt write-offs, recharges and deductions, and the surplus (or a "draw on reserves"
inflow when there is a deficit). Outflows under 2% are folded into "Smaller items" in the
shareable version. Inflow always equals outflow.

## Balance, bridge, forecast

- Balance series: cumulative operating net, month by month, from the start of the ledger.
- Bridge (latest complete fiscal year): beginning balance → + gross revenue → − each
  expense bucket → − assessment → = ending balance. The beginning balance comes from
  the Department P&L (sign flipped from the UC convention) or is $0 without it.
- Forecast (current fiscal year, needs at least 3 months posted): year-to-date net plus
  the remaining months as they went in each earlier complete year. Shown as a central
  projection with a low–high range; always called a projection.

## PPMS usership

- Revenue = `Price` of order lines that are accepted or completed. Lines never accepted or
  completed are unconverted quotes, counted separately.
- Fiscal year from `Date Ordered`.
- Groups are case-folded before counting.
- Customer mix: share of revenue by affiliation (from confirmed `affiliations.csv`).
- Concentration: share of revenue from the top 5, 10 and 20 groups.
- New vs returning: a group is new in the first fiscal year it appears in the export
  (so the first year of the export is all "new" and is not shown).
- Turnaround: days from accepted to completed, per order. If 80% or more of orders go
  from accepted to completed within an hour, the dates were entered at billing and
  turnaround and backlog are reported as not measurable.
- Backlog: orders accepted but not completed at each month end.
- Heatmap: orders placed per month; months outside the export's dates are blank.
- Unbilled: completed lines with `Invoiced = N`.

## Affiliation guesses

From `Fin Account`. UC Davis chartstrings are UC Davis. For `EXTERNAL - …` accounts the
email domain decides: ucdavis.edu is UC Davis, another UC campus or lab domain is other
UC, `.edu`/`.org`/`.gov` and foreign academic domains are non-profit (medium confidence),
`.com`/`.bio`/`.io` are industry, and no domain is "not yet classified". Each guess
has a confidence and a reason. The core confirms them in `affiliations.csv`; confirmed rows
are never overwritten.

## RCCI tables

- Table 1: one row per PI group in the RCCI date window: affiliation, college/school,
  department, PI, spend, number of orders. Sorted UC Davis, other UC, external
  non-profit, industry, unclassified.
- Table 2: spend by college/school (UC Davis) or affiliation, with the share of the total.
