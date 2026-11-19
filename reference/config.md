# core-config.yaml

`python run.py init <folder>` writes this file; edit it by hand afterwards.

| Field | Meaning | Example |
|---|---|---|
| `core_name` | Full name, used in titles and footers | `Example Imaging Core` |
| `short_name` | Short name for the centre of the Sankey | `Imaging Core` |
| `financial_department` | Aggie Enterprise Financial Department code | `XIMG001` |
| `project` | Recharge project number (optional) | `AR09999901` |
| `funds` | Funds to analyse, each with a label and a role | see below |
| `personnel_prefixes` | Account prefixes treated as personnel; removed from the staff edition | `["50"]` |
| `paid_staff` | Paid staff headcount. With 2 or fewer, no staff edition is built, because its yearly personnel totals would reveal individual pay | `null` (unknown: edition built, with a warning) |
| `brand` | Dashboard colours | `{primary: "#022851", accent: "#FFBF00"}` |
| `rcci_window` | Date window (Date Ordered) for RCCI Tables 1 and 2 | `{start: "2024-07-01", end: "2025-06-30"}` |
| `assessment_note` | Your own sentence for the assessment panel; `null` keeps the neutral default | `null` |
| `coa_overrides` | Override any key of `reference/ucd-chart-of-accounts.yaml` | `{}` |

## Funds

```yaml
funds:
  "12100": {label: "Sales and Services Rate Based", role: operating}
  "16200": {label: "Sales and Service Reserves", role: reserve}
  "13U00": {label: "University Common Funds", role: general}
```

Roles: `operating`, `reserve`, `general`, `workshop`, `other`. They are labels for
readers; every listed fund is included in the totals. Quote fund codes so `13U00` and
`12100` stay text. Leave out grant funds (20xxx) unless you want them in the core's
operating picture.

## Overriding campus defaults

```yaml
coa_overrides:
  assessment_rate: 0.15
  expense_groups:
    - {name: "Salaries & Wages", prefixes: ["500", "501"], personnel: true}
    - {name: "Benefits", prefixes: ["508", "505", "506"], personnel: true}
    - {name: "Instrument Service Contracts", accounts: ["532302"]}
    - {name: "Other Operating", catch_all: true}
```

Groups are matched in order and the first match wins: exact `accounts` first, then
`prefixes`. Keep one `catch_all` group last. If you rename groups, update
`per_dollar_buckets` to match.

## publications

Used only by `run.py publications`.

| Key | Default | Meaning |
|---|---|---|
| `core_names` | `[core_name]` | Every name the core has gone by, and staff surnames people thank. A paper "names the core" if any appears in its record or full text. |
| `other_facilities` | `[]` | Facilities offering similar services. A paper naming one of them and not this core is listed under "Names another facility" instead of being flagged. |
| `technique_terms` | none (required) | Words a methods section uses when your service was used. `*` is a wildcard: `"proteom*"`. |
| `institution` | `"Davis"` | The matched author's affiliation must contain this, unless the PI and a submitter are both authors. |
| `years_after` | `3` | How long after a lab's last order a paper still counts. |
| `follow_up_years` | `3` | Labs with orders this recent and no paper since are listed to follow up. |
