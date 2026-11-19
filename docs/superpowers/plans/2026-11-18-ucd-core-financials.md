# UCD Core Financials Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Claude skill that tells a UC Davis core how to pull its Aggie Enterprise and PPMS reports, then turns them into a financial dashboard, slide figures, an RCCI usership workbook, a benchmark file and a one-page summary.

**Architecture:** A pure-Python package `core_financials/` does all parsing, arithmetic, checks and rendering. `run.py` at the skill root is the single entry point Claude calls. `SKILL.md` plus `reference/*.md` tell Claude the workflow, the report-pulling guides and the rules. Campus-wide accounting rules live in `reference/ucd-chart-of-accounts.yaml`; each core's settings live in `core-config.yaml` in the user's working folder.

**Tech Stack:** Python ≥3.10, pandas, openpyxl, xlrd, matplotlib, PyYAML, pytest. The HTML has Chart.js 4.4.1, chartjs-chart-treemap 3.1.0 and chartjs-chart-sankey 0.12.1, all inlined.

**Spec:** `docs/superpowers/specs/2026-11-18-ucd-core-financials-design.md`

**Repo:** `~/ucd-core-financials-skill` → `github.com/bsphinney/ucd-core-financials-skill` (public)

## Global Constraints

- **No real Proteomics data in the repo.** That means no real Proteomics Core figures, PI names, staff names, department code or project code. A repo-wide hashed-token test enforces it (Task 1).
- **No network calls at run time.** The only exception is `_deps.ensure()` installing missing pip packages.
- **The dashboard is one self-contained `.html` file:** all CSS, JS, libraries and data inline, and no `<script src=`.
- **Shareable outputs carry no `$` and no PI or group names.** These are files under `out/share/` and `benchmark.csv`.
- **Fiscal year:** `FY = year + 1 if month >= 7 else year`. FY2026 runs from 2025-07-01 to 2026-06-30.
- **A fiscal year is "complete" only if all 12 months appear in the data.** Trend statements and the forecast compare complete years only.
- **Signs:** GL `amount` is debit-positive.
  - Income from class 4/7 accounts = `-amount`. Expense from class 5 = `amount`.
  - Class 3 is excluded from every operating figure.
- **Assessment is the accounts `770009` and `775004` only.** Contra `445100` is its own line, never part of the assessment.
- **Categorical palette, in this fixed order, never cycled:** `#C07F00 #3D8FD9 #5FAA4E #A96FE8 #E86A3B #17A89A #C94F63`. Surplus `#37c893`, deficit `#ff6b7d`. Defaults for `brand.primary` `#022851` and `brand.accent` `#FFBF00`.
- **Assessment wording is neutral by default.** A config `assessment_note` string replaces it.
- **PPMS:**
  - Revenue = `Price`.
  - FY comes from `Date Ordered`.
  - A line is revenue only if `Date Accepted` or `Date Completed` is non-blank.
  - Group names are compared case-folded and whitespace-trimmed.
- **Failed checks never stop output.** They appear in `out/checks.md`, in a red dashboard banner and in the CLI output. Arithmetic checks use a tolerance of $0.01.

## Review Focus

1. **Header row not on row 1.** A real export has a parameter block above the header (wide GL at row 29, PO report at row 12). The loader must find the header row by matching signature columns. Tested in Task 2.
2. **The same month pulled twice, or overlapping monthly files.** Exact duplicate rows must not double the totals. Tested in Task 2.
3. **Codes read as numbers.** `Fund` 12100 or `Account` 410000 may arrive as ints or floats, while `775B00` is alphanumeric. Every code must become a string such as `"410000"` before classification. Tested in Task 2.
4. **A core with only PPMS files, or only a GL file.** `build` must produce the sections it can, skip the rest with a note, and exit 0. Tested in Task 11.
5. **PPMS dates.** They arrive as `"2022/09/27 09:41:18"` strings, Excel datetimes or blanks. A blank `Date Completed` must count as open (backlog), not as an error. Tested in Task 5.

---

## File Structure

```
SKILL.md                         workflow Claude follows (Task 12)
README.md, LICENSE (MIT), requirements.txt, pytest.ini, .gitignore
run.py                           adds skill dir to sys.path, calls core_financials.cli.main
reference/
  ucd-chart-of-accounts.yaml     campus-wide accounting defaults (Task 1)
  pulling-reports.md             step-by-step pull guides + request wording (Task 12)
  calculations.md                every rule, generalised from the Proteomics spec (Task 12)
  config.md                      core-config.yaml fields (Task 12)
  figures.md                     catalog of figures, share vs internal (Task 12)
core_financials/
  __init__.py, __main__.py
  _deps.py                       ensure() installs missing packages
  config.py                      Config, load_config, load_coa, write_config_template
  fiscal.py                      fiscal_year, fy_months, complete_fys
  io_util.py                     find_header_row, read_table, norm_code
  gl.py                          load_gl, classify
  aggie.py                       load_po, load_balances, load_glide
  ppms.py                        load_orders
  affiliation.py                 guess, build_or_update, load_affiliations
  finance.py                     GL metrics
  usership.py                    PPMS metrics
  checks.py                      Check, run_checks, write_checks_md
  inventory.py                   detect, scan, reports_needed_md
  figures.py                     matplotlib figures
  dashboard.py                   build_dashboard (+ staff redaction)
  rcci.py                        write_usership_workbook
  benchmark.py                   write_benchmark, combine_benchmarks
  summary.py                     build_facts
  pipeline.py                    run_build (orchestrates everything)
  cli.py                         argparse commands
assets/
  dashboard_template.html
  vendor/chart.umd.min.js, chartjs-chart-treemap.min.js, chartjs-chart-sankey.min.js, LICENSES.md
sample_data/
  generate.py                    deterministic fictional core (seed 2026)
  example_core/                  generated files, committed
tools/build_skill_zip.py         makes dist/ucd-core-financials.zip
tests/                           one test file per module + test_repo_hygiene.py + test_end_to_end.py
```

**Normalised GL frame** (output of `gl.load_gl`, the input everywhere else). Every column is a string except where noted:
- codes and descriptions: `fund`, `fund_desc`, `account`, `account_desc`;
- journal fields: `journal_category`, `journal_name`, `period`;
- `date` (Timestamp);
- `amount` (float, debit-positive);
- `supplier` and `line_desc` (`""` when absent);
- `source_file`.

`gl.classify` adds `acct_class` (first char of `account`), `fy` (int) and `role`, which is one of:
`income | expense | assessment | contra | carryforward | other`. It also adds `group`, the revenue or expense group name, or `""`.

**Normalised orders frame** (output of `ppms.load_orders`):
- order and party: `order`, `user`, `group`, `group_key` (case-folded), `fin_account`;
- service: `service`, `service_group`;
- amounts: `unit_price`, `qty`, `price` (floats);
- `invoiced` (bool);
- dates (Timestamp or NaT): `ordered`, `accepted`, `completed`;
- `assigned_to`;
- derived: `fy` (int), `is_revenue` (bool).

---

### Task 1: Scaffold, config, chart of accounts, fiscal year, repo hygiene

**Files:**
- Create: `run.py`, `requirements.txt`, `pytest.ini`, `.gitignore`, `LICENSE`, `core_financials/{__init__,__main__,_deps,config,fiscal}.py`, `reference/ucd-chart-of-accounts.yaml`
- Test: `tests/test_config.py`, `tests/test_fiscal.py`, `tests/test_repo_hygiene.py`

**Interfaces:**
- Produces:
  - `Config` dataclass with these fields:
    - `core_name: str`, `short_name: str`, `financial_department: str`, `project: str`
    - `funds: dict[str, dict]`, mapping a code to `{label, role}`, where role is one of `operating|reserve|general|workshop|other`
    - `personnel_prefixes: list[str]` (default `["500","501","505","506","508"]`)
    - `brand: dict`, `rcci_window: tuple[date, date]`, `assessment_note: str|None`
    - `coa: dict`, the chart of accounts merged with the config's `coa_overrides`
  - `load_config(path) -> Config`
  - `load_coa(overrides: dict|None=None) -> dict`
  - `write_config_template(path, proposed_funds: dict[str,str]|None=None) -> None`
  - `fiscal_year(ts) -> int`
  - `fy_months(dates: pd.Series) -> dict[int, set[int]]`
  - `complete_fys(dates) -> list[int]`
  - `_deps.ensure(pkgs: list[str]) -> None`

`reference/ucd-chart-of-accounts.yaml` keys and exact values:
```yaml
assessment_accounts: ["770009", "775004"]
contra_accounts: ["445100"]
carryforward_accounts: ["300001"]
assessment_rate: 0.15
external_sales_account: "410000"
earned_revenue_accounts: ["775000", "410000"]
revenue_groups:            # ordered; first match wins; last is catch-all
  - {name: "Internal Recharge (UCD)", accounts: ["775000"]}
  - {name: "External Sales & Services", accounts: ["410000"]}
  - {name: "Appropriations / Institutional Support", prefixes: ["775B"]}
  - {name: "Intercampus Recharge (other UCs)", prefixes: ["785"]}
  - {name: "Other Revenue", catch_all: true}
expense_groups:
  - {name: "Salaries & Wages", prefixes: ["500", "501"], personnel: true}
  - {name: "Benefits", prefixes: ["508", "505", "506"], personnel: true}
  - {name: "Lab Supplies & Chemicals", prefixes: ["522", "520"]}
  - {name: "Services & Repairs", prefixes: ["530", "532", "534"]}
  - {name: "Equipment", prefixes: ["525"]}
  - {name: "Freight & Shipping", prefixes: ["539"]}
  - {name: "Other Operating", catch_all: true}
per_dollar_buckets:
  personnel: ["Salaries & Wages", "Benefits"]
  supplies_services: ["Lab Supplies & Chemicals", "Services & Repairs"]
  other_operating: ["Equipment", "Freight & Shipping", "Other Operating"]
uc_domains: [ucdavis.edu, berkeley.edu, ucsf.edu, ucla.edu, uci.edu, ucsd.edu, ucsb.edu, ucsc.edu, ucr.edu, ucmerced.edu, ucop.edu, ucanr.edu, lbl.gov, llnl.gov]
```

- [ ] **Step 1: Write failing tests**
  - `test_fiscal_year_boundaries`: 2025-06-30 → 2025; 2025-07-01 → 2026.
  - `test_complete_fys`: dates covering Jan–Jun 2024 plus Jul 2024–Jun 2025 plus Jul 2025 give `complete_fys == [2025]`.
  - `test_load_config_merges_overrides`: a YAML with `coa_overrides: {assessment_rate: 0.12}` gives `cfg.coa["assessment_rate"] == 0.12` and `cfg.coa["contra_accounts"] == ["445100"]`.
  - `test_fund_codes_are_strings`: YAML `funds: {12100: ...}` gives the key `"12100"`.
  - `test_write_config_template_roundtrip`: write a template with proposed funds `{"12100":"Sales and Services Rate Based"}`, then load it. The result has `funds["12100"]["role"] == "operating"`, and `"12100"` defaults to `operating`.
  - `test_repo_hygiene`: walk every text file in the repo (os.walk, excluding `.git` and `dist`). Split each file into lowercase tokens with `re.findall(r"[a-z0-9]+")`, hash each token with SHA-256, and assert that none is in `FORBIDDEN_SHA256`.
    - That set holds the digests of a token list the controller supplies at execution time: the real department and project codes, staff surnames and real PI surnames from the source data. The plain tokens never appear in the repo, including this plan.
    - Also forbid every 6-digit-or-more dollar figure from the Proteomics sources: the controller supplies the digests of those numbers with their commas removed.
- [ ] **Step 2:** `pytest -q` → FAIL (modules missing).
- [ ] **Step 3: Implement.**
  - `write_config_template` emits commented YAML with every Config field.
  - `_deps.ensure` runs `pip install --user` for missing imports. If that fails it retries with `--break-system-packages`.
  - `run.py` puts its own dir first on `sys.path` and calls `core_financials.cli.main()`. Create `cli.py` with a stub `main()` that prints usage; Task 11 fills it.
  - `requirements.txt`: `pandas>=2.0 openpyxl>=3.1 xlrd>=2.0 matplotlib>=3.7 PyYAML>=6`.
- [ ] **Step 4:** `pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat: scaffold, config, chart of accounts, fiscal year`.

### Task 2: Table reading and GL loader + classification

**Files:**
- Create: `core_financials/io_util.py`, `core_financials/gl.py`
- Test: `tests/test_gl.py`, `tests/conftest.py` (fixture builders that write tiny xlsx files to `tmp_path`)

**Interfaces:**
- Consumes: `Config`, `fiscal_year`.
- Produces:
  - `find_header_row(path, sheet, signature: set[str], max_rows=60) -> int` (0-based)
  - `read_table(path, signature, sheet=None) -> pd.DataFrame`. This handles `.xlsx` via openpyxl and `.xls` via xlrd; if `sheet` is None, it searches every sheet.
  - `norm_code(x) -> str`. `410000.0` becomes `"410000"`, `"775B00 "` becomes `"775B00"`, and None becomes `""`.
  - `load_gl(paths: list[Path], cfg) -> pd.DataFrame` (the normalised GL frame, filtered to `cfg.funds`)
  - `classify(gl, cfg) -> pd.DataFrame`

Layout mapping:

| Normalised column | 34-column "page" export | 58-column wide export |
|---|---|---|
| Signature columns | `{"Fund","Account","Journal Accounting Date","Actuals"}` | `{"Fund","Account","JE Accounting Date","Accounted Net"}` |
| `amount` | `Actuals` | `Accounted Net` |
| `date` | `Journal Accounting Date` | `JE Accounting Date` |
| `journal_category` | `Journal Category` | `JE Category` |
| `journal_name` | `Journal Name` | `JE Name` |
| `period` | `Accounting Period` | `JE Accounting Period` |
| `supplier` | not present (`""`) | `Supplier/Customer Name` |
| `line_desc` | `Journal Line Description` | `Transaction Line Description` |

When the same file set contains both layouts, de-duplicate on the key `(fund, account, date, round(amount,2), journal_name)`, keeping the wide row because it carries the supplier. Exact duplicate rows within one layout are dropped.

`classify` rules, in order:
1. `account` in carryforward → `carryforward`.
2. In assessment accounts → `assessment`.
3. In contra accounts → `contra`.
4. Class 4 or 7 → `income`.
5. Class 5 → `expense`.
6. Anything else → `other`.

The `group` column is filled from the coa ordered rules: revenue groups for `income`, expense groups for `expense`. Accounts are matched first, then prefixes, then the catch-all.

- [ ] **Step 1: Write failing tests**
  - `test_header_row_found_below_parameter_block`: a sheet with 28 parameter rows, then the wide header at row 29. `load_gl` returns 3 rows.
  - `test_codes_normalised`: Account given as int 410000 and Fund as float 12100.0 → `"410000"` and `"12100"`.
  - `test_duplicate_month_files_not_double_counted`: the same page file passed twice → the sum of `amount` equals that of a single file.
  - `test_page_and_wide_overlap_keeps_supplier`: a page row and a wide row for the same transaction → 1 row, `supplier == "ACME LAB SUPPLY"`.
  - `test_funds_filtered_to_config`: a row in fund `20700`, which is not in the config, is dropped.
  - `test_classify_roles`: accounts 300001, 770009, 775004, 445100, 410000, 775000, 522400, 500100 → roles `carryforward, assessment, assessment, contra, income, income, expense, expense`. Groups: 410000 → `External Sales & Services`, 775B12 → `Appropriations / Institutional Support`, 522400 → `Lab Supplies & Chemicals`, 599999 → `Other Operating`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement as specified.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: GL loader for page and wide exports, classification`.

### Task 3: Finance metrics

**Files:**
- Create: `core_financials/finance.py`
- Test: `tests/test_finance.py`

**Interfaces:**
- Consumes: classified GL frame and `Config`.
- Produces. Every function returns plain JSON-ready dicts or lists; amounts are rounded to cents only at output.
  - `kpis(gl) -> {"income","expense","net"}`
    - income = `-sum(amount)` over roles `income, assessment, contra`
    - expense = `sum(amount)` over role `expense`
  - `revenue_groups(gl, cfg) -> list[{"name","amount","accounts":[{"account","desc","amount"}],"by_fy":{fy:amt}}]`
    - Gross is taken over role `income` accounts whose net income is > 0.
  - `deductions(gl, cfg) -> list[{"account","desc","amount"}]`
    - These are role-`income` accounts whose net income is < 0, for example a 770006 recharge paid out. Amounts are positive.
  - `expense_groups(gl, cfg) -> list[...]`, in the same shape as revenue groups, in coa order. Empty groups are omitted.
  - `assessment(gl, cfg) -> dict`. Keys:
    - `total` = `sum(amount)` over role `assessment`
    - `contra_total`
    - `by_fy`
    - `pct_gross` and `pct_earned`, where earned = the income of `earned_revenue_accounts`
    - `per_dollar_external` = total ÷ external-sales income
    - `match = {"months": n, "matched": k, "rate": k/n}`. A month counts as matched when `abs(assessment_month - rate*external_sales_month) <= 0.01`, checked over months with external sales ≠ 0.
  - `sankey(gl, cfg) -> list[{"from","to","flow"}]`
    - Revenue groups flow to `cfg.short_name`.
    - `cfg.short_name` then flows to each expense group, to `"Campus Assessment"` (assessment + contra) and to `"Recharges & deductions"` (the sum of deductions).
    - If the result is positive it flows to `"Net Surplus"`. If it is negative, `"Draw on reserves / deficit"` flows into the core instead.
  - `per_dollar(gl, cfg, fy: int|None=None) -> dict`
    - Keys: `personnel, supplies_services, other_operating, assessment, surplus` (fractions of gross revenue).
    - `other_operating` includes the deductions.
    - `surplus = 1 - sum(others)`, which may be negative.
  - `cost_recovery_by_fy(gl, cfg) -> {fy: earned_income / expense}`
  - `series(gl, freq: "FY"|"M", fund: str|None) -> list[{"key","income","expense","net"}]`
  - `fund_summary(gl, cfg) -> list[{"fund","label","fy","income","expense","net"}]`
  - `carryforward(gl) -> list[{"fund","fy","amount"}]`
  - `balance_series(gl) -> list[{"month","cumulative_net"}]`. This is the cumulative operating net (surplus positive) by month.
  - `bridge(gl, cfg, fy, beginning: float|None) -> list[{"step","amount"}]`
    - Steps: `Beginning balance`, `+ Revenue (gross)`, `− Personnel`, `− Supplies & services`, `− Other operating`, `− Campus assessment`, `= Ending balance`. A missing beginning balance is treated as 0.
    - Signs are surplus-positive. The P&L uses credit-negative signs, so `beginning` is passed already flipped (Task 4 does this).
  - `forecast(gl, cfg) -> dict|None`
    - Returns None when the latest FY is complete or when there is no earlier complete FY.
    - Otherwise: `ytd_net`, then for each earlier complete FY the net of the months not yet seen this year. `projected = ytd_net + mean(those)`, `low = ytd_net + min`, `high = ytd_net + max`, plus `months_seen` and `based_on_fys`.
  - `top_accounts(gl, role, n=15) -> list`
  - `account_detail(gl, account) -> {"by_fy":{...},"transactions":[...]}`
  - `compute_finance(gl, cfg, balances_beginning: float|None) -> dict`, which bundles all of the above under fixed keys, the same names as the functions.

- [ ] **Step 1: Write failing tests** on a hand-built frame of about 15 rows in `conftest.py` (`small_gl`). It has two FYs: FY2025 complete with 12 months, and FY2026 with Jul–Sep only.
  - `test_kpis_identity`: `income - expense == net`, with values computed by hand in the test.
  - `test_assessment_excludes_contra`: assessment 150.00 and contra 40.00 → `total == 150.0` and `contra_total == 40.0`.
  - `test_assessment_match_rate`: 3 months of external sales of 1000, with assessment 150, 150 and 149 → `matched == 2`, `rate == 2/3`.
  - `test_sankey_balances`: inflow to core == outflow from core within 0.01, in both a surplus case and a deficit case.
  - `test_per_dollar_sums_to_one` (within 1e-9). Also a deficit case gives `surplus < 0`.
  - `test_deduction_account_is_outflow`: a 770006 debit of 25 appears in `deductions` and not in `revenue_groups`.
  - `test_forecast`: the expected values are hand-computed.
  - `test_forecast_none_without_prior_complete_fy`.
  - `test_bridge_ends_at_computed_balance`: the last step equals the beginning plus the sum of the signed steps.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: finance metrics`.

### Task 4: PO spend, P&L balances, GLIDE loaders and metrics

**Files:**
- Create: `core_financials/aggie.py`
- Test: `tests/test_aggie.py`

**Interfaces:**
- Consumes: `read_table`, `norm_code`, `fiscal_year`, `Config`.
- Produces:
  - `load_po(paths, cfg) -> DataFrame[supplier, item, account, fund, amount, created, fy]`
    - Signature: `{"Supplier Name","Charge Account","PO Line Distribution Amount","PO Creation Date"}`.
    - `account` and `fund` are parsed from `"NNNNNN - Name"`.
    - The frame is filtered to `cfg.funds`.
    - `PO Creation Date` arrives as `MM-DD-YYYY` strings or datetimes.
  - `suppliers_by_account(po) -> {account: {fy: [{"supplier","amount"}]}}`
  - `supplier_concentration(po, n=10) -> {"top":[{"supplier","share"}],"top_n_share": float}`
    - Computed over non-personnel accounts. Shares are fractions.
  - `po_vs_gl(po, gl) -> list[{"account","po_committed","gl_posted"}]`
  - `load_balances(path) -> list[{"fund","beginning","revenue","expense","ending"}]`
    - Read from sheet `Balances`. Signature: any column starting `Sum of 3`, `Sum of 4`, `Sum of 5` and `Sum of Ending`.
    - `Fund` is forward-filled, and the `Grand Total` row is dropped.
    - Values stay in the P&L's own signs (credit negative). Callers flip them for display.
  - `balances_total(rows) -> dict`
  - `load_glide(paths) -> DataFrame[category, fy, amount]`
    - Signature: `{"Report Type","GL Natural Account Name","Debit Amount","Credit Amount","Accounting Date"}`.
    - Filtered to `Report Type == "GL Expense"`; `amount = Debit - Credit`.
    - **Only these three columns are ever returned.** Person-name columns are never read into the result.
  - `glide_by_category(glide) -> list[{"category","amount","by_fy"}]`

- [ ] **Step 1: Write failing tests**
  - `test_po_header_row_12_and_code_parsing`: `"522400 - Lab Supplies and Accessories"` → `"522400"`.
  - `test_po_filtered_to_funds`.
  - `test_concentration_shares_sum_le_1`.
  - `test_balances_forward_fill_and_grand_total_dropped`.
  - `test_glide_drops_name_columns`: a fixture with `udfString1="Jane Traveler"` → the string `"Jane"` appears nowhere in `glide_by_category(...)` serialised to JSON.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: PO spend, P&L balances, GLIDE loaders`.

### Task 5: PPMS orders loader, affiliation guessing, usership metrics

**Files:**
- Create: `core_financials/ppms.py`, `core_financials/affiliation.py`, `core_financials/usership.py`
- Test: `tests/test_ppms.py`, `tests/test_affiliation.py`, `tests/test_usership.py`

**Interfaces:**
- Consumes: `read_table`, `fiscal_year`, `Config`.
- Produces:
  - `load_orders(paths) -> DataFrame` (the normalised orders frame).
    - Signature: `{"Order Number","Group","Fin Account","Price","Date Ordered"}`.
    - The `Invoiced - Y/N,` column name includes the trailing comma. Match it by prefix `Invoiced`.
  - `guess(fin_account: str, coa) -> tuple[str, str, str]`, returning `(affiliation, confidence, reason)`.
    - `affiliation` is one of `UC Davis | Ext-UC | Ext-NP | Ext-FP | Unknown`; `confidence` is one of `high | medium | low`.
    - The rules:

      | `Fin Account` | Result |
      |---|---|
      | `EXTERNAL - <email>`, domain is or ends with a `uc_domains` entry other than `ucdavis.edu` | `Ext-UC`, high |
      | `EXTERNAL`, domain `ucdavis.edu` | `UC Davis`, low (reason "external billing with UCD email") |
      | `EXTERNAL`, domain ends `.edu` / `.org` / `.gov`, or contains `.ac.` or `.edu.` | `Ext-NP`, medium |
      | `EXTERNAL`, domain ends `.com` / `.bio` / `.io` | `Ext-FP`, medium |
      | `EXTERNAL`, any other domain | `Unknown`, low |
      | Not `EXTERNAL`, matches `^\d-[A-Z0-9]+` (KFS) or `^[A-Z0-9]{5,}-[A-Z0-9]+` (Aggie Enterprise chartstring) | `UC Davis`, medium |
      | Bare digits | `Unknown`, low (reason "looks like a PO number") |
      | Anything else | `Unknown`, low |

  - `build_or_update(orders, path, coa) -> pd.DataFrame`
    - Columns: `group, affiliation, college, department, confidence, reason, confirmed`.
    - A group's guess is the majority vote across its Fin Accounts.
    - Rows already in the file are never overwritten. New groups are appended with `confirmed="N"`.
  - `load_affiliations(path) -> dict[group_key, dict]`
  - `usership.py`. All functions take `(orders, aff)` where relevant and use `is_revenue` rows only:
    - `overview_by_fy -> [{"fy","revenue","orders","groups","users"}]`. Orders are counted as distinct `order`.
    - `mix_by_fy -> [{"fy", "<affiliation>": share, ...}]`. Shares are fractions of revenue and sum to 1.
    - `concentration -> {"top5","top10","top20","n_groups"}`, as fractions of revenue over the whole data.
    - `new_vs_returning -> [{"fy","new","returning"}]`. A group is new in the FY of its first revenue order. The first FY in the data is dropped because it has no baseline.
    - `turnaround -> {"by_service":[{"service","median","p25","p75","n"}],"by_quarter":[{"quarter","median","n"}]}`.
      - Days run from accepted to completed. Only rows with both dates count; negative values are dropped.
      - `service` is `service_group`, or `service` when that is blank.
    - `backlog_monthly -> [{"month","open"}]`. This counts distinct orders with accepted ≤ month-end and (completed is NaT or completed > month-end).
    - `orders_heatmap -> {"fys":[...],"months":[7..12,1..6],"counts":[[...]]}`.
    - `revenue_by_service -> [{"service","revenue","orders"}]`.
    - `top_groups(n=20) -> [{"group","affiliation","revenue","orders"}]`.
    - `unbilled -> {"lines":[{"order","group","service","price","completed"}],"total"}`. These are rows with `is_revenue`, completed not NaT, and `invoiced` False.
    - `quotes -> {"count","total"}`, computed over the non-revenue rows.
    - `compute_usership(orders, aff) -> dict`, which bundles everything above under keys named after the functions.

- [ ] **Step 1: Write failing tests**
  - `test_dates_parsed_from_strings_and_blanks`: `"2022/09/27 09:41:18"` → a Timestamp, and blank → NaT.
  - `test_is_revenue_rule`.
  - `test_group_key_casefold`: `"Kim Lab"` and `"kim lab "` → the same key.
  - `test_guess_table`: one assertion per row of the rules table.
  - `test_build_or_update_preserves_user_edits`: write a CSV row with `affiliation=Ext-FP, confirmed=Y`, then rebuild → it is unchanged and a new group is appended.
  - `test_mix_sums_to_one`.
  - `test_concentration_monotonic`: `top5 <= top10 <= top20 <= 1`.
  - `test_new_vs_returning_hand_example`.
  - `test_backlog_counts_open_orders`: an order accepted in Jan with no completed date is open at every later month-end.
  - `test_unbilled_only_completed_not_invoiced`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: PPMS orders, affiliation guessing, usership metrics`.

### Task 6: Sample data generator

**Files:**
- Create: `sample_data/generate.py`, `sample_data/example_core/*` (generated, committed), `sample_data/example_core/core-config.yaml`
- Test: `tests/test_sample_data.py`

**Interfaces:**
- Consumes: the loaders from Tasks 2, 4 and 5 (used only in the tests).
- Produces: `generate(out_dir: Path, seed: int = 2026) -> None`, which writes these files:
  - `gl_page_2024-01_to_2026-09.xlsx`: sheet `page`, all 34 page columns in real order (list them from the spec's §1 plus the full real header).
  - `gl_wide_2025-03.xlsx`: 28 parameter rows, then the 58-column header at row 29. The rows are a subset of March 2025 expense rows, with suppliers.
  - `po_spend_2023-12_to_2026-04.xlsx`: header at row 12.
  - `pnl_fy2026.xlsx`: sheet `Balances`.
  - `glide_fy2026.xlsx`: sheet `page`. Name columns are filled with fake names, to prove they are dropped.
  - `ppms_order_details.xlsx`.

Fictional core details:
- `core_name: "Example Imaging Core"`, `short_name: "Imaging Core"`, department `XIMG001`, project `AR09999901`.
- Funds `12100` (operating), `16200` (reserve) and `13U00` (general). There is no workshop fund.

Contents:
- GL from Jan 2024 to Sep 2026. FY2024 is partial, FY2025 and FY2026 are complete, and FY2027 is partial.
- The monthly 770009 assessment (775004 from FY2026) is exactly 15% of 410000 in every month except one deliberate mismatch.
- It includes one 445100 row, annual 300001 rows and one 770006 debit.
- About 40 groups and about 700 order lines, using a fake surname list (no real UC Davis PIs).
- Fin Accounts mix `EXTERNAL - x@ucla.edu`, `@stanford.edu`, `@acmebio.com`, KFS-like strings and bare digits.
- About 3% of lines are quotes (no accepted date), about 3% are not invoiced, and about 5% are open (no completed date).

- [ ] **Step 1: Write failing tests**
  - `test_generate_is_deterministic`: two runs produce byte-identical CSV dumps of each loaded frame.
  - `test_sample_loads`: every file is detected by its loader and is non-empty.
  - `test_sample_has_assessment_mismatch_month`: match `rate < 1` and `> 0.9`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement, and run `python sample_data/generate.py`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: deterministic sample data for a fictional core`.

### Task 7: Checks and inventory

**Files:**
- Create: `core_financials/checks.py`, `core_financials/inventory.py`
- Test: `tests/test_checks.py`, `tests/test_inventory.py`

**Interfaces:**
- Consumes: the `compute_finance` dict, the `compute_usership` dict, `po_vs_gl` and the loaders.
- Produces:
  - `Check` dataclass: `name, passed: bool, detail: str, kind: "arithmetic"|"info"`.
  - `run_checks(fin: dict|None, use: dict|None) -> list[Check]`. The checks:
    - `income − expense = net`
    - `gross − assessment − contra − deductions = income`
    - Sankey in = out
    - Expense groups sum = expense
    - Each group's accounts sum = the group amount
    - Usership overview revenue sum = `sum(price[is_revenue])`
    - Info only: the assessment match rate, and a PO-vs-GL line for each account with both
  - `write_checks_md(checks, path)`
  - `detect(path) -> str|None`, returning one of `gl_page, gl_wide, po_spend, pnl_balances, glide, ppms_orders`. Detection tries each signature via `find_header_row`.
  - `scan(folder) -> list[{"path","kind","start","end","rows"}]`. Unknown files are listed with kind `None`.
  - `reports_needed_md(inv, cfg) -> str`. It covers:
    - which kinds are missing and what each would add;
    - date gaps: GL months missing between the first and last month; PO coverage ending more than 60 days before the GL's last month;
    - a request paragraph for finance staff with `cfg.financial_department`, the funds and the needed periods filled in.

- [ ] **Step 1: Write failing tests**
  - `test_checks_pass_on_sample`.
  - `test_check_fails_when_tampered`: subtract 1.00 from one expense-group amount → the named check fails.
  - `test_detect_each_sample_file`.
  - `test_reports_needed_lists_missing_po_and_gl_gap`: copy the sample folder without the PO file and with one GL month removed → the text contains `PO spend report` and the missing month label (`Mar-2025` format).
  - `test_reports_needed_fills_department`: `XIMG001` appears.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: reconciliation checks and report inventory`.

### Task 8: Figures (share and internal)

**Files:**
- Create: `core_financials/figures.py`
- Test: `tests/test_figures.py`

**Interfaces:**
- Consumes: `compute_finance` and `compute_usership` dicts, plus `Config`.
- Produces: `render_figures(fin, use, cfg, out_dir) -> dict[str, list[Path]]`.
  - It writes PNG (200 dpi) and SVG for each figure, with `svg.fonttype = "none"` so the text is searchable.
  - Share figures go in `out_dir/share/`, internal ones in `out_dir/internal/`.
  - Each figure is skipped quietly when its input is None or empty.

Share figures. These show percentages, ratios, counts or days only. Axis tick formatters must never use `$`.
- `cost_recovery_by_fy`: bars with a dashed 100% line, partial FYs hatched.
- `per_dollar`: one horizontal 100% stacked bar per complete FY, labelled in ¢.
- `assessment_per_dollar_by_fy`: assessment as ¢ per $1 of gross revenue.
- `sankey_share`: a two-column flow drawn with matplotlib patches, labels in % of gross.
- `customer_mix`: 100% stacked area by FY.
- `concentration`: bars for top-5, top-10 and top-20 share.
- `new_vs_returning`: grouped bars of counts.
- `turnaround`: box per service plus a median-by-quarter line.
- `backlog`: line of open orders.
- `orders_heatmap`.

Internal figures:
- `balance_series`
- `bridge` (waterfall)
- `supplier_concentration`, top 10 by share, with supplier names
- `forecast`, YTD plus a projected range
- `assessment_by_fy` in dollars

Colours come from the fixed palette in order. Titles are plain sentences. The footer on every figure reads `"<core_name> · source: <report> · generated <date>"`.

- [ ] **Step 1: Write failing tests**
  - `test_share_figures_have_no_dollars_or_names`: render from the sample data. For every SVG in `share/`, extract the `<text>` contents and assert there is no `$` and no case-folded group name from the sample orders.
  - `test_expected_files_exist`: all 10 share and 5 internal figures exist as both png and svg.
  - `test_missing_input_skips`: `render_figures(fin=None, ...)` writes only the PPMS figures.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: share and internal figures`.

### Task 9: Dashboard HTML and staff edition

**Files:**
- Create: `assets/dashboard_template.html`, `assets/vendor/*` (via `npm pack chart.js@4.4.1 chartjs-chart-treemap@3.1.0 chartjs-chart-sankey@0.12.1` in a scratch dir; copy `dist/chart.umd.js`, the treemap and sankey `dist/*.min.js`, and their LICENSE texts into `assets/vendor/LICENSES.md`), `core_financials/dashboard.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `compute_finance`, `compute_usership`, the aggie metrics and `list[Check]`.
- Produces:
  - `build_dashboard_data(fin, use, aggie: dict, checks, cfg, staff: bool) -> dict`
  - `write_dashboard(data, cfg, out_path) -> Path`, which replaces `/*__DATA__*/` with `const DATA = {...};` and `/*__VENDOR__*/` with the three inlined libraries.

Visual reference: the layout of the existing Proteomics dashboard (dark navy theme, gold accents, KPI row, sections). The builder may look at it but must copy no data from it. Sections, in order (the spec §8 sections 1–13, adapted):
1. Checks banner. It is red when any arithmetic check fails, and otherwise a small green "all checks passed".
2. KPIs.
3. Campus assessment panel, with neutral text or `cfg.assessment_note`, the match rate and the per-FY bars.
4. Sankey.
5. Expense treemap, with click → account modal.
6. Revenue donut, with click → modal.
7. Income vs expense, toggling FY / Monthly and filtering by fund.
8. Net by FY.
9. Fund breakdown.
10. Top revenue and expense tables. Expense rows drill down to transactions with a filter box. Every account modal leads with "Spend by fiscal year" and, when PO data exists, "Companies paid — by fiscal year" plus the PO-committed vs GL-posted line.
11. Fund × FY matrix.
12. Carry-forward reference table.
13. Official fund balances.
14. Card, travel & freight.
15. Cost recovery.
16. Fund balance over time.
17. Bridge.
18. Forecast.
19. Usership: mix, concentration, new vs returning, turnaround, backlog, heatmap.
20. Unbilled orders table.

A section whose data is missing renders a one-line "Add the <report> to see this" note.

Staff edition (`staff=True`):
- Delete every account whose code starts with a `personnel_prefixes` entry from the account lists, transactions and top-expense table.
- Insert aggregate rows `Salaries & Wages` and `Benefits` holding FY totals only.
- Drop the unbilled table, because it names groups.
- Show a `STAFF EDITION` header and banner.

- [ ] **Step 1: Write failing tests**
  - `test_dashboard_self_contained`: the output has no `<script src=` and no `http` inside `<script>` blocks other than library licence comments, and the size is < 3 MB on the sample.
  - `test_dashboard_data_roundtrip`: parse the embedded `DATA` JSON → `kpis.net` equals `compute_finance(...)["kpis"]["net"]`.
  - `test_staff_edition_has_no_personnel_accounts`: for each personnel account code in the sample GL, the code appears nowhere in the staff HTML. `"STAFF EDITION"` is present.
  - `test_missing_sections_show_note`: build with `aggie={}` → the text `Add the PO spend report` is present.
  - `test_failed_check_shows_red_banner`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Use `canvas.addEventListener('click', …)` with `getElementsAtEventForMode(e,'nearest',{intersect:true},true)` for the treemap and donut drill-downs (spec gotcha).
- [ ] **Step 4:** Run → PASS. Then open the sample dashboard in a browser with the `run` skill or Chrome, check that every chart renders and that a treemap click opens its modal, and take a screenshot.
- [ ] **Step 5:** Commit `feat: interactive dashboard and staff edition`.

### Task 10: Usership/RCCI workbook, benchmark, summary facts

**Files:**
- Create: `core_financials/rcci.py`, `core_financials/benchmark.py`, `core_financials/summary.py`
- Test: `tests/test_rcci.py`, `tests/test_benchmark.py`, `tests/test_summary.py`

**Interfaces:**
- Consumes: the orders frame, the affiliations dict, the `compute_usership` and `compute_finance` dicts, and `Config`.
- Produces:
  - `write_usership_workbook(orders, aff, use, cfg, path) -> Path`. Its sheets:
    - `Overview` (by FY: revenue, orders, groups, users; partial FY flagged).
    - `By customer type` (revenue and orders by FY × affiliation).
    - `Top PI groups` (top 20).
    - `By service`.
    - `RCCI Table 1`, with these exact columns: `Core, PI Affiliation, PI College/School, PI Department, PI Name, Spend, Volume (orders)`. There is one row per group with revenue inside `cfg.rcci_window`. Rows are sorted by affiliation in the order `UC Davis, Ext-UC, Ext-NP, Ext-FP, Unknown`, then by college, then by PI.
      - For UC Davis groups the College/School value comes from the affiliations file. For external groups it repeats the affiliation code, as the campus template does.
    - `RCCI Table 2`: spend and % by college for UC Davis, then Ext-UC, Ext-NP, Ext-FP, then a Grand Total. % values are live Excel formulas.
    - `Unconfirmed`: groups with `confirmed == "N"`.
    - `Notes`: the window, the source file names, the quote total excluded, and a line about PPMS Usership Summary differences.
  - `write_benchmark(fin, use, cfg, path) -> Path`. This is a long CSV with the columns `core, fy, metric, value, unit`.
    - `metric` is one of: `cost_recovery`, `assessment_per_dollar`, `per_dollar_personnel`, `per_dollar_supplies_services`, `per_dollar_other`, `per_dollar_surplus`, `mix_<affiliation>`, `top10_share`, `new_group_share`, `median_turnaround_days`, `orders`, `groups`.
    - `unit` is one of `ratio | fraction | days | count`.
    - FY values that are not complete are suffixed `-partial`.
  - `combine_benchmarks(paths, out_xlsx, out_png) -> None`. It produces a wide comparison table (metric × core for the latest common complete FY) and a small-multiples PNG.
  - `build_facts(fin, use, checks, inv, cfg) -> dict`, written to `out/facts.json`. It holds every number the one-page summary may quote, each with a `source` string.

- [ ] **Step 1: Write failing tests**
  - `test_rcci_table1_columns_and_order`.
  - `test_rcci_window_filters`: an order outside the window is excluded.
  - `test_rcci_table2_total_equals_table1_sum`.
  - `test_benchmark_no_dollars_no_names`: `unit` never equals `usd`, no value string contains `$`, and no sample group name appears.
  - `test_combine_two_cores`: generate the sample twice with different seeds and core names, combine them → the xlsx has two core columns.
  - `test_facts_have_sources`: every leaf in `facts.json` has `source`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: RCCI workbook, benchmark file, summary facts`.

### Task 11: Pipeline and CLI

**Files:**
- Create: `core_financials/pipeline.py`. Modify: `core_financials/cli.py`, `core_financials/__main__.py`
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `run_build(folder: Path, out: Path|None=None) -> dict`. This returns `{"outputs": [paths], "skipped": [{"section","reason"}], "checks": [...]}`; `out` defaults to `folder/"out"`.
  - CLI (`python run.py <cmd>`):
    - `init <folder>`: writes `core-config.yaml`. If a GL file is present, it proposes the funds found in it with their `Fund Description`.
    - `inventory <folder>`: prints the inventory table and writes `out/reports-needed.md`.
    - `affiliations <folder>`: builds or updates `affiliations.csv` and prints the counts of unconfirmed groups by confidence.
    - `build <folder>`: runs everything. It prints the outputs, the skipped sections and any FAILED checks. It exits 0, or 2 when no recognised input exists.
    - `combine <csv>... --out <dir>`
  - Output layout under `out/`:
    - `dashboard.html`, `dashboard_STAFF.html`
    - `share/`, `internal/`
    - `usership.xlsx`, `benchmark.csv`, `facts.json`, `checks.md`, `reports-needed.md`

- [ ] **Step 1: Write failing tests**
  - `test_build_sample_end_to_end`: copy `sample_data/example_core` to `tmp_path` and run `build`. Every output listed above exists, there are no failed arithmetic checks, and the exit code is 0.
  - `test_build_ppms_only`: only the PPMS file and config → exit 0. The dashboard exists with usership sections, and `skipped` names the GL sections.
  - `test_build_gl_only`: the converse of `test_build_ppms_only`.
  - `test_build_empty_folder_exit_2`.
  - `test_init_proposes_funds_from_gl`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Call `_deps.ensure([...])` at the start of `cli.main`.
- [ ] **Step 4:** Run the full suite with `pytest -q` → all PASS.
- [ ] **Step 5:** Commit `feat: build pipeline and CLI`.

### Task 12: SKILL.md, reference docs, README

**Files:**
- Create: `SKILL.md`, `reference/pulling-reports.md`, `reference/calculations.md`, `reference/config.md`, `reference/figures.md`, `README.md`
- Test: `tests/test_docs.py`

`SKILL.md` frontmatter:
- `name: ucd-core-financials`
- `description:` should trigger on these mentions: UC Davis core facility finances, PPMS / Stratocore, Aggie Enterprise reports, GL transaction listing, recharge, income assessment, RCCI usership, Cores Connect, core dashboard.

Body, under 300 lines. It covers:
1. Setup: `python run.py init`, then confirm the funds and personnel prefixes with the user.
2. Getting reports: show the matching section of `pulling-reports.md` with the core's codes filled in, and offer the finance-staff request.
3. `inventory`.
4. `affiliations`, then ask the user to confirm the low and medium rows in a short table.
5. `build`.
6. Report:
   - any failed checks;
   - the skipped sections;
   - share vs internal outputs, with the warning that internal outputs contain dollars and names.
7. Write `out/summary.md` (and `.docx` if asked) from `facts.json` only, quoting no number that is not in it.
8. Rules list, copied from the spec's "Rules carried over".
9. A note on running in claude.ai: the scripts are in the skill folder, and the user uploads exports into the chat.

`reference/pulling-reports.md` has one section per report: what it's for, where to find it, the filters, the export format, the file naming, and the common errors. Use `{DEPT}`, `{PROJECT}` and `{FUNDS}` placeholders.
- **GL listing:** the direct link `https://aggieenterprise.ucdavis.edu/aggie-enterprise-reports/ucd-transaction-listing-report-gl-and-subledger-detail`, one month per run for the wide version, ServiceHub KB0010829, and access via the department Security Liaison.
- **PO spend report** (the "UCD Comprehensive Spend Report"): Charge Financial Department filter, and the PO creation date range.
- **Department P&L:** ask the department finance contact for the "Department P&L with Balances tab".
- **GLIDE:** the report name and the GL Expense rows.
- **PPMS Order details:** Reports → Order Details, with the Fin Account column and the full history.
- **PPMS Usership Summary:** optional, for comparison.

Where our notes lack an exact click-path, say so and give the request wording instead.

- [ ] **Step 1: Write failing test** `test_docs.py`:
  - SKILL.md frontmatter parses, `name == "ucd-core-financials"` and the description is under 1024 characters.
  - Every `reference/*.md` that SKILL.md links to exists.
  - Every CLI command named in SKILL.md exists in the `cli.py` argparse.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Write the docs. README covers:
  - install for Claude Code: `git clone` then `ln -s ~/ucd-core-financials-skill ~/.claude/skills/ucd-core-financials`;
  - install for claude.ai/desktop: upload `dist/ucd-core-financials.zip`;
  - a worked example on `sample_data/example_core` with three embedded share figures;
  - a privacy section;
  - the line `Built by the UC Davis Proteomics Core (Brett Phinney).`
- [ ] **Step 4:** Run the full suite → PASS.
- [ ] **Step 5:** Commit `docs: SKILL.md, report-pulling guides, reference, README`.

### Task 13: Zip packaging, final review, publish

**Files:**
- Create: `tools/build_skill_zip.py`
- Test: `tests/test_zip.py`

**Interfaces:** `build_zip(repo: Path, out: Path) -> Path` creates `dist/ucd-core-financials.zip`.
- The zip has a top-level folder `ucd-core-financials/` containing `SKILL.md`, `run.py`, `requirements.txt`, `core_financials/`, `assets/`, `reference/` and `sample_data/`.
- It excludes `tests/`, `docs/`, `tools/`, `__pycache__` and `.git`.
- `dist/` is gitignored, and the zip is attached to a GitHub release instead.

- [ ] **Step 1:** Write `test_zip_contents` (required paths present, excluded paths absent, size < 10 MB).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full suite → PASS. In a fresh scratch dir, unzip the archive and run `python ucd-core-financials/run.py build ucd-core-financials/sample_data/example_core` → exit 0.
- [ ] **Step 5:** Commit `feat: skill zip packaging`.
- [ ] **Step 6:** Whole-branch review with a fresh reviewer.
- [ ] **Step 7:** Publish:
  - `gh repo create bsphinney/ucd-core-financials-skill --public --source . --push`;
  - `gh release create v0.1.0 dist/ucd-core-financials.zip`;
  - link the skill into `~/.claude/skills/ucd-core-financials`.
