# Publications report — design (approved 2026-11-19)

**Why:** find papers by the core's customers that may use the core's data, flag those whose full
text never names the core, and list labs whose data has not appeared yet so the core can follow up.

**Approach (picked):** Europe PMC REST search (holds all of PubMed plus open-access / NIH full text,
searchable by section). Two queries per person, cached. Separate command `run.py publications <folder>`;
never part of `build` (it is the only step that sends anything over the internet: author names).

**Rules**
- People: every PPMS group (PI, "Last, First") and every submitting user ("Last First") with an
  accepted or completed order. Window: first order → last order + `years_after` (default 3).
- Candidate paper: person is an author; published in the window; not a review; methods, abstract or
  title mention a `technique_terms` term; and linked to the lab: the matched author's affiliation
  contains `institution` (default "Davis"), or the PI and a submitter from the lab are both authors.
- Status: **Names the core** (any `core_names` variant anywhere in the record or full text);
  **Core not named** (full text in Europe PMC, no variant found); **Can't check** (no free full text).
- Follow up: labs with orders in the last `follow_up_years` (default 3) of the export and no candidate
  paper published after their last order.
- Output: `out/internal/publications.xlsx` (Core not named, Can't check, Names the core, Follow up,
  About). Internal only: names and paper flags. Wording is "core not named", never an accusation.

**Tested on:** Proteomics Core real exports. Known case: a submitter (not the PI) with a 2025 order and no paper yet must appear under Follow up; a
same-name researcher at another institution must not match.
