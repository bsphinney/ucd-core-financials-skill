"""Per-core settings (core-config.yaml) merged with campus-wide defaults."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from . import SKILL_ROOT
from .io_util import norm_code

COA_PATH = SKILL_ROOT / "reference" / "ucd-chart-of-accounts.yaml"
DEFAULT_PERSONNEL = ["50"]  # every 50xxxx account is compensation or benefits
DEFAULT_BRAND = {"primary": "#022851", "accent": "#FFBF00"}
FUND_ROLE_GUESS = {"12100": "operating", "16200": "reserve", "13U00": "general", "13U20": "workshop"}


@dataclass
class Config:
    core_name: str
    short_name: str = ""
    financial_department: str = ""
    project: str = ""
    funds: dict = field(default_factory=dict)
    personnel_prefixes: list = field(default_factory=lambda: list(DEFAULT_PERSONNEL))
    brand: dict = field(default_factory=lambda: dict(DEFAULT_BRAND))
    rcci_window: tuple | None = None
    assessment_note: str | None = None
    coa: dict = field(default_factory=dict)


def load_coa(overrides: dict | None = None) -> dict:
    coa = yaml.safe_load(COA_PATH.read_text())
    coa = copy.deepcopy(coa)
    for k, v in (overrides or {}).items():
        coa[k] = v
    # Codes typed without quotes arrive as numbers; every code must be text to match the ledger.
    for k in ("assessment_accounts", "contra_accounts", "carryforward_accounts", "earned_revenue_accounts"):
        coa[k] = [norm_code(c) for c in coa.get(k, [])]
    coa["external_sales_account"] = norm_code(coa.get("external_sales_account", ""))
    for grp in ("revenue_groups", "expense_groups"):
        for g in coa.get(grp, []):
            for f in ("accounts", "prefixes"):
                if f in g:
                    g[f] = [norm_code(c) for c in g[f]]
    return coa


def _as_date(v):
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def load_config(path) -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    funds = {}
    for code, info in (raw.get("funds") or {}).items():
        code = str(code).strip()
        info = dict(info or {})
        info.setdefault("label", code)
        info.setdefault("role", FUND_ROLE_GUESS.get(code, "other"))
        funds[code] = info
    window = raw.get("rcci_window")
    if window:
        window = (_as_date(window.get("start")), _as_date(window.get("end")))
    name = str(raw.get("core_name") or "Core Facility")
    return Config(
        core_name=name,
        short_name=str(raw.get("short_name") or name),
        financial_department=str(raw.get("financial_department") or ""),
        project=str(raw.get("project") or ""),
        funds=funds,
        personnel_prefixes=[str(p) for p in raw.get("personnel_prefixes") or DEFAULT_PERSONNEL],
        brand={**DEFAULT_BRAND, **(raw.get("brand") or {})},
        rcci_window=window,
        assessment_note=raw.get("assessment_note"),
        coa=load_coa(raw.get("coa_overrides")),
    )


TEMPLATE = """# core-config.yaml - settings for one core. Claude fills this in with you during setup.
core_name: "{core_name}"          # full name, used in titles and footers
short_name: "{short_name}"        # short name for the Sankey centre node
financial_department: "{dept}"    # Aggie Enterprise Financial Department code
project: "{project}"              # recharge project number (optional)

# Funds to analyse. role: operating | reserve | general | workshop | other
funds:
{funds}
# Account-code prefixes that are personnel (removed in the staff edition)
personnel_prefixes: ["50"]

brand: {{primary: "#022851", accent: "#FFBF00"}}

# Date window for the RCCI usership tables
rcci_window: {{start: "{win_start}", end: "{win_end}"}}

# Optional: your own wording for the campus assessment panel (default is neutral)
assessment_note: null

# Optional: override campus-wide defaults from reference/ucd-chart-of-accounts.yaml
coa_overrides: {{}}
"""


def write_config_template(path, proposed_funds: dict | None = None, core_name: str = "My Core Facility",
                          dept: str = "", project: str = "") -> None:
    proposed_funds = proposed_funds or {"12100": "Sales and Services Rate Based"}
    lines = []
    for code, desc in proposed_funds.items():
        role = FUND_ROLE_GUESS.get(str(code), "other")
        lines.append(f'  "{code}": {{label: "{desc}", role: {role}}}')
    today = date.today()
    start_fy = today.year - 2 if today.month >= 7 else today.year - 3
    Path(path).write_text(TEMPLATE.format(
        core_name=core_name, short_name=core_name, dept=dept, project=project,
        funds="\n".join(lines), win_start=f"{start_fy}-07-01", win_end=today.isoformat()))
