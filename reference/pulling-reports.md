# Pulling the reports

One section per report. Replace `{DEPT}` with the core's Aggie Enterprise Financial
Department code, `{PROJECT}` with its recharge project number, and `{FUNDS}` with the
fund codes in `core-config.yaml`.

Put every export, unrenamed or renamed, in one folder. The skill recognises each report by
its columns, not its file name, and finds the header row even below a block of report
parameters. Excel (.xlsx or .xls) and CSV both work.

**Access.** Aggie Enterprise reports need finance reporting access. If a report is
missing from your menu, ask your department's Security Liaison, or submit a ServiceHub
request for GL reporting access. If you would rather not pull them yourself, send the
request at the end of this page to your department finance contact.

---

## 1. GL Transaction Listing (standard export) — the most important one

**What it gives:** every journal posted to the core's funds. Every money figure (income,
expense, assessment, Sankey, per-dollar split, cost recovery, balance, forecast) comes
from it.

**What to ask for:** a GL transaction listing for Financial Department `{DEPT}`, funds
`{FUNDS}`, all accounts, every accounting period from at least two full fiscal years ago
to today, exported to Excel. The export the skill reads has columns including `Fund`,
`Account`, `Journal Name`, `Journal Accounting Date` and `Actuals`.

**Filters:** Financial Department `{DEPT}`; leave Account blank (all accounts); Fund blank
or `{FUNDS}`.

**Range:** start on 1 July so the first fiscal year is complete. Re-pull the whole range
each time rather than appending; the skill counts a row once even if two files overlap.

**Common problems**
- *Header not on the first row.* Fine; the skill finds it.
- *Fund or account codes shown as numbers* (e.g. `12100.0`). Fine; codes are read as text.
- *A month missing.* `inventory` lists missing months in `reports-needed.md`.

Our notes do not include an exact click-path for this export. Department finance staff
pull it routinely; the request wording at the end of this page works.

## 2. UCD Transaction Listing Report – GL and Subledger Detail (wide export)

**What it gives:** the same transactions split into individual invoice lines, with the
supplier name and line description. Used for "which companies did we pay" inside each
expense account. Optional.

**Where:** go straight to
`https://aggieenterprise.ucdavis.edu/aggie-enterprise-reports/ucd-transaction-listing-report-gl-and-subledger-detail`
and choose Run Report. (Or search Reports for "UCD Transaction Listing Report — GL and
Subledger Detail".) The official guide is ServiceHub knowledge-base article **KB0010829**;
Aggie Enterprise also runs live demo sessions.

**Filters**

| Filter | Enter |
|---|---|
| Financial Department | `{DEPT}` |
| Accounting Period | **one month per run**: the report times out on longer ranges |
| Account | blank for everything, or `52000A` (Supplies & Services) / `53000A` (Other Operating) |
| Project | `{PROJECT}` (optional) |
| Fund | blank, or `{FUNDS}` |

**Export:** Excel (.xlsx). Name files by month, e.g. `{DEPT}_2025-03.xlsx`.

**Common problems**
- *Times out.* Narrow to one month.
- *No data.* Check the department code and that the period is in the fiscal year you mean
  (July–June).
- *Can't find account 52000A.* Try `52000` without the letter, or browse the account
  hierarchy to "Supplies and Services".
- The header sits about 29 rows down, below the parameters. That is expected.

## 3. PO spend report ("UCD Comprehensive Spend Report")

**What it gives:** every purchase order line with supplier, item and charge account.
Feeds "companies paid" by account and fiscal year, supplier concentration, and the PO
vs GL comparison. Optional.

**Filters:** Charge Financial Department = `{DEPT}`; PO Creation Date from the start of the
GL range to today.

**Export:** Excel. Columns the skill needs: `Supplier Name`, `Charge Account`,
`PO Line Distribution Amount`, `PO Creation Date` (and `Charge Fund` if present).

**Remember:** PO amounts are what was *ordered*. Multi-year service contracts are ordered
up front, so a PO total can be far above what has posted to the GL.

## 4. Department P&L with Balances tab

**What it gives:** the official fund balances (beginning, revenue, expense, ending) and the
starting point for the "what moved the balance" bridge. Optional.

**Where:** ask your department finance contact for the "Department P&L with the Balances
tab" for `{DEPT}`, current fiscal year to date. It is usually prepared by the department,
not pulled from a menu.

**Sign convention:** UC style, negative = surplus (credit), positive = deficit. The skill
flips the beginning balance for the bridge and says so.

## 5. GLIDE report

**What it gives:** card, travel and freight spending by category. Only category totals are
used; cardholder and traveller names are never read. Optional.

**Filters:** Financial Department `{DEPT}`, the same date range as the GL. The skill keeps
only rows whose Report Type is `GL Expense`.

## 6. PPMS Order details report

**What it gives:** every order line with the lab group, user, service, price, dates and
the `Fin Account`. Feeds customer mix, concentration, new vs returning labs, turnaround,
backlog, seasonality, RCCI Tables 1 and 2, and the unbilled-order check.

**Where:** in PPMS, Reports → Order details. Include the `Fin Account` column and the
full history (from the first year you want to compare, ideally five or more years).

**Export:** Excel. Keep these columns: `Order Number`, `Group`, `User`, `Fin Account`,
`Service`, `Price`, `Date Ordered`, `Date Accepted`, `Date Completed`, `Invoiced - Y/N,`.

**Common problems**
- *All orders accepted and completed within seconds.* The core enters orders at billing
  time. Usage and revenue are fine; turnaround and backlog cannot be measured, and the
  dashboard says so. To measure them, accept orders when samples arrive and complete them
  when results go out.
- *Quotes in the export.* Orders never accepted or completed are counted separately as
  unconverted quotes, not as revenue.

## 7. PPMS Usership Summary (optional, for comparison)

PPMS's own Usership Summary can differ from the Order details totals by a few percent,
because it includes credits and adjustments that are not order lines. Pull it only if you
want to reconcile the two.

---

## Request to department finance staff

> Hi {finance contact},
>
> For our core's financial review, could you send me these exports for Financial
> Department {DEPT} (funds {FUNDS}), as Excel files?
>
> 1. A GL transaction listing, all accounts, from 1 July {start year} through today.
> 2. The UCD Comprehensive Spend Report (PO spend) for the same department and dates.
> 3. The current Department P&L, including the Balances tab.
> 4. The GLIDE report for the same dates.
> 5. If easy: the "GL and Subledger Detail" listing for a few recent months (one month
>    per run), so we can see suppliers on each expense line.
>
> Thank you!
