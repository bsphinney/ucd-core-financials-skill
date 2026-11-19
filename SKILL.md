---
name: ucd-core-financials
description: Financial and usership reports for UC Davis core facilities that bill through PPMS (Stratocore). Tells the core exactly which Aggie Enterprise and PPMS reports to pull and how, then builds an interactive dashboard, a staff edition, shareable figures, RCCI usership tables, an unbilled-order check, a year-end forecast and a benchmark file. Use when someone mentions UC Davis core facility finances, recharge rates or deficits, PPMS or Stratocore exports, Aggie Enterprise reports, a GL transaction listing, the campus income assessment, RCCI usership tables, Cores Connect, or a core dashboard.
---

# UC Davis core facility financials

This skill turns a core's own exports into the reports the UC Davis Proteomics Core built
for itself, generalised so any PPMS core can run them. Everything runs locally from
files the user exports by hand; there is no connection to Aggie Enterprise or PPMS.

Scripts live next to this file. Run them as `python <skill-dir>/run.py <command> <folder>`,
where `<folder>` is one folder holding the core's exports. Missing Python packages are
installed on first run.

## Workflow

Work through these steps in order. Keep the user in the loop at the points marked **Ask**.

### 1. Set up the core's folder

Ask the user for (or create) one folder for the exports. Then:

```
python run.py init <folder>
```

Ask how many paid staff the core has and set `paid_staff`. With 2 or fewer, no staff
edition is built: its yearly personnel totals would show what each person is paid. Tell the
user that is why.

`init` writes `core-config.yaml`. If a GL export is already in the folder it proposes the
funds, department code and project number it found. **Ask** the user to confirm:
- the core's full name and short name;
- which funds belong to the core (drop grant funds such as 20700 unless they want them);
- the personnel account prefixes (defaults are campus-wide and rarely change).

Field-by-field help: [config reference](reference/config.md). `init` never overwrites an
existing config.

### 2. Get the reports

Show the user the matching sections of the [report-pulling guide](reference/pulling-reports.md),
with `{DEPT}`, `{PROJECT}` and `{FUNDS}` replaced by the codes from `core-config.yaml`.
The minimum useful set is:

| Report | System | Unlocks |
|---|---|---|
| GL Transaction Listing (standard export) | Aggie Enterprise | every money section |
| PPMS Order details | PPMS | customers, RCCI tables, unbilled check |
| PO spend report | Aggie Enterprise | companies paid per account |
| Department P&L (Balances tab) | department finance | official balances, bridge |
| GLIDE report | Aggie Enterprise | card, travel and freight |
| GL and Subledger Detail (wide) | Aggie Enterprise | invoice lines with supplier names |

Many core directors do not have Aggie Enterprise reporting access. Offer the
"Request to department finance staff" text from the guide, ready to paste into an email.

### 3. Check what arrived

```
python run.py inventory <folder>
```

Prints each file, the report it was recognised as, and the dates it covers. It also writes
`out/reports-needed.md`, listing missing reports and missing months. Read it to the user
and say plainly which sections will be skipped.

### 4. Customer affiliations (PPMS cores)

```
python run.py affiliations <folder>
```

Guesses each lab group's affiliation (UC Davis, other UC, external non-profit, industry)
from the PPMS `Fin Account` field into `affiliations.csv`. **Ask** the user to confirm the
low- and medium-confidence rows: show them as a short table (group, guess, why) in
batches of about 20, and write their answers back with `confirmed=Y`. UC Davis rows
need a college and department for RCCI Table 2. Re-running keeps confirmed rows.

### 5. Build

```
python run.py build <folder>
```

Everything goes to `<folder>/out/`:

| Output | Contains dollars or names? | Audience |
|---|---|---|
| `dashboard.html` | yes | director, department finance |
| `dashboard_STAFF.html` | dollars, no personnel detail | core staff |
| `share/*.png, *.svg` | no | other cores, Cores Connect, campus |
| `benchmark.csv` | no | other cores (see step 8) |
| `internal/*.png, *.svg` | yes | director |
| `usership.xlsx` (RCCI Tables 1 and 2) | yes | RCCI submission |
| `checks.md`, `reports-needed.md`, `facts.json` | yes | you and the director |

Figure catalog and what each one answers: [figures](reference/figures.md).

### 6. Report back

Tell the user, in this order:
1. **Failed checks.** If `checks.md` lists any FAIL, say which figures are affected
   before anything else. Never present numbers from a failed check as settled.
2. **What was skipped** and which report would add it.
3. **What to look at first**: open `dashboard.html`; for meetings with other cores,
   use only `share/` and `benchmark.csv`.
4. **Findings worth acting on**: unbilled completed orders, months where the assessment
   is not 15% of external sales, and the forecast range (always called a projection).

Warn that `dashboard.html`, `internal/` and `usership.xlsx` contain dollar amounts and
lab names and should not be sent outside the core and its finance staff.

### 7. One-page summary

When asked for a summary, write `out/summary.md` (and a .docx if they ask) **using only
numbers in `out/facts.json`**. Every number you write must appear there; cite the fact's
source in a footnote line. Follow the `rules` list inside `facts.json`. If a number the
user wants is not in `facts.json`, say so instead of computing it yourself.

### 8. Compare cores

Each core's `benchmark.csv` holds only ratios, shares, counts and days. To compare:

```
python run.py combine a/benchmark.csv b/benchmark.csv --out comparison
```

Comparisons use the most recent fiscal year that every core has complete.

### 9. Publications (optional, online)

Finds papers by the core's customers that may use the core's data and checks whether each
names the core. **This is the only step that goes online**: it sends PI and submitter names
to Europe PMC (which holds all of PubMed plus open-access and NIH full text). Ask before
running it. Never run it as part of `build`.

First fill in `publications:` in `core-config.yaml` with the user:
- `core_names`: every name the core has gone by, plus staff surnames people thank.
- `technique_also` (optional): a second list, one of which must also appear. Use it when
  the first list is shared with other facilities: a proteomics core pairs mass-spec words
  with protein words (`"trypsin"`, `"peptide*"`, `"proteomic*"`).
- `other_facilities`: other facilities offering similar services. A paper naming one of
  them (and not this core) goes to "Names another facility", not the flag list.
- `technique_terms`: words a methods section uses when the service was used
  (`"mass spectrometry"`, `"proteom*"`; `"confocal"`, `"light-sheet"`).

```
python run.py publications <folder>             # every lab; 15-30 minutes, cached
python run.py publications <folder> --limit 20  # quick test on the 20 most recent labs
```

Writes `out/internal/publications.xlsx`:
- **Core not named**: full text checked, none of the names found.
- **Can't check**: only the abstract is free. Someone must read the paper.
- **Names the core**: for annual and RCCI reports.
- **Follow up**: labs with recent orders and no paper yet.

When you report back, say "core not named", never "did not acknowledge": the lab may have
used another facility for that paper. Read a flagged paper's methods before anyone writes
to the lab. The workbook has lab and person names: internal only.

How a paper qualifies: the PI, or someone from the lab who submitted samples, is an author,
because submitters are often first author and the PI may not be. The author must be at the
institution, or the PI and a submitter must both be authors; this drops same-name researchers
elsewhere. The paper must be published between the lab's first order and 3 years after its
last, must not be a review, and must mention a technique term in its methods, abstract or title.

## Rules

These come from mistakes made, or nearly made, in the Proteomics Core's own reports.
How each is calculated: [calculations](reference/calculations.md).

- Sign by the account's first digit: 4 and 7 are income (sign flipped), 5 is expense,
  3 (300001 carry-forward) is excluded and listed for reference only.
- The campus income assessment is accounts 770009 and 775004 only. Bad-debt write-offs
  (445100) are reported on their own line and never added to it.
- Check the assessment against 15% of external sales (410000) month by month, matching
  each charge to the month named in its journal. Report the match rate.
- The fiscal year runs July–June. Label partial years, and never say a figure is
  rising or falling by comparing a partial year with a full one.
- PO amounts are committed (ordered), not posted. Show both side by side.
- PPMS revenue counts accepted or completed order lines only; unconverted quotes are
  reported separately.
- Case-fold PI and group names before counting.
- Customer type comes from the PPMS `Fin Account`, confirmed by the core.
- Assessment wording is neutral unless the core supplies its own (`assessment_note`).
- GLIDE output is category totals only; cardholder and traveller names are never read.
- Shareable outputs carry no dollar amounts and no lab or person names.
- The forecast is a projection, needs at least 3 months of the year, and is always
  shown as a range.

## Things that surprise people

- **Two GL exports.** The standard export has one row per journal; the wide "GL and
  Subledger Detail" export splits journals into invoice lines with supplier names. When
  both are present the standard one is the ledger and the wide one only adds supplier
  detail, so nothing is counted twice.
- **The assessment posts a month late.** Campus charges February's assessment on 31 March
  and names February in the journal. The newest month often has sales but no charge yet;
  it is listed as "not yet charged", not as a mismatch.
- **PPMS dates entered at billing.** Some cores create, accept and complete orders in one
  sitting when they bill. Turnaround and backlog then cannot be measured; the dashboard
  says so and explains what to change in PPMS.
- **P&L vs GL.** The Department P&L classifies revenue its own way, so its totals differ
  from the operating figures. It is used for the official balance and as the bridge's
  starting point. UC sign convention there: negative = surplus.

## Running in claude.ai or Claude Desktop

Upload the skill zip once. In a chat, the user uploads their exports; put them in one
folder in the sandbox and run the same commands. Return `out/dashboard.html` and the
figures as downloadable files. Everything else is the same. `publications` needs internet
access from the sandbox; if it has none, say so and offer to run it in Claude Code.

## Sample data

`sample_data/example_core/` is a fictional "Example Imaging Core" with made-up numbers
and names. Use it to demonstrate the skill or to test a change:
`python run.py build sample_data/example_core`.
