# Figures

Every figure is written as PNG (for slides) and SVG (editable text) into `out/share/`
or `out/internal/`. Each carries a footer naming the core, the source report and the date.

## Shareable (`out/share/`): no dollar amounts, no names

| File | Question it answers | Source |
|---|---|---|
| `cost_recovery_by_fy` | How much of operating cost does earned revenue cover? Partial years hatched. | GL |
| `per_dollar` | Where does each dollar of revenue go? | GL |
| `assessment_per_dollar_by_fy` | How many cents per revenue dollar go to the campus assessment? | GL |
| `sankey_share` | Follow the money, as shares of gross revenue | GL |
| `customer_mix` | Who does the core serve, and is it shifting? | PPMS |
| `concentration` | Does the core depend on a few labs? | PPMS |
| `new_vs_returning` | Is the core winning new labs or living on regulars? | PPMS |
| `turnaround` | Is service getting faster or slower? (only when PPMS dates are meaningful) | PPMS |
| `backlog` | How many orders are open at month end? (same condition) | PPMS |
| `orders_heatmap` | Which months are busy or quiet? | PPMS |

## Internal (`out/internal/`): contains dollars or supplier names

| File | Question it answers | Source |
|---|---|---|
| `balance_series` | Running operating surplus or deficit since the ledger starts | GL |
| `bridge` | What moved the balance in the latest complete year? | GL + P&L |
| `forecast` | Where will this year end? (projection, range; needs 3+ months) | GL |
| `assessment_by_fy` | Assessment dollars per fiscal year | GL |
| `supplier_concentration` | Share of non-personnel PO spend going to the top suppliers | PO report |

## Dashboard (`dashboard.html`)

A single self-contained file (no internet needed) with: overview tiles, the assessment
panel with the 15% check, Sankey, an expense treemap and revenue donut (click to drill
into accounts, then into transactions and companies paid), income vs expense by year or
month with a fund filter, net by year and fund, top accounts, cost recovery and per-dollar
split, balance and bridge and forecast, carry-forward, official P&L balances, GLIDE,
supplier concentration, customers and usage, turnaround, seasonality, top groups and
services, and completed-but-not-invoiced orders. A banner at the top reports the
reconciliation checks.

`dashboard_STAFF.html` is the same without individual salary and benefit accounts (shown
only as combined annual totals) and without the unbilled list.

## Comparison across cores

`python run.py combine` writes `benchmark_comparison.xlsx` and a small-multiples PNG, one
panel per metric, for the most recent fiscal year all cores have complete.
