#!/usr/bin/env python3
"""Generate made-up exports for a fictional core ("Example Imaging Core") in the real report layouts.

Every name, code and amount here is invented. Run: python sample_data/generate.py [out_dir]
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

DEPT, DEPT_DESC = "XIMG001", "Example Imaging Core"
PROJECT, PROJECT_DESC = "AR09999901", "EXAMPLE IMAGING CORE"
FUNDS = {"12100": "Sales and Services Rate Based", "16200": "Sales and Service Reserves",
         "13U00": "COFI University Common Funds"}

PAGE_COLS = ['Entity', 'Entity Description', 'Fund', 'Fund Description', 'Financial Department',
             'Financial Department Description', 'Account', 'Account Description', 'Purpose', 'Purpose Description',
             'Program', 'Program Description', 'Project', 'Project Description', 'Activity', 'Activity Description',
             'Document Type', 'Accounting Sequence Number', 'Tracking Number', 'Reference', 'Journal Source',
             'Journal Category', 'Journal Batch Name', 'Journal Name', 'Journal Line Description',
             'Journal Reference', 'Accounting Period', 'Journal Accounting Date', 'Journal Type',
             'Encumbrance Type Code', 'Journal Status', 'Commitments', 'Obligations', 'Actuals']
WIDE_COLS = ['Entity', 'Entity Description', 'Fund', 'Fund Description', 'Financial Department',
             'Financial Department Description', 'Parent A Account', 'Account', 'Account Description', 'Purpose',
             'Purpose Description', 'Program', 'Program Description', 'Project', 'Project Description', 'Activity',
             'Activity Description', 'Inter Entity', 'Inter Entity Description', 'Document Type',
             'Accounting Sequence Number', 'Tracking Number', 'Reference', 'JE Source', 'JE Category',
             'JE Batch Name', 'JE Batch Description', 'JE Name', 'JE Description', 'Journal Reference',
             'PPM User Expenditure Batch', 'PPM Original Transaction Reference', 'PPM Comments',
             'JE Accounting Period', 'JE Accounting Date', 'JE Type', 'JE Status', 'JE Creation Date',
             'JE Created By', 'JE Posted Date', 'JE Last Approved By', 'Accounted Dr ', 'Accounted Cr ',
             'Accounted Net', 'JE Line Number', 'JE Line Description', 'Transaction Number',
             'Transaction Description', 'Transaction Line Description', 'AP/AR Invoice Number',
             'AP/AR Invoice Date', 'Requester', 'Check ', 'Payment Date', 'PO Number', 'PO Buyer',
             'Supplier/Customer Name', 'Supplier/Customer Number']
PO_COLS = ['Purchase Order', 'Purchase Order Description', 'PO Status', 'Buyer', 'PO Creation Date', 'PO End Date',
           'Supplier Number', 'Supplier Name', 'Supplier Site Name', 'Payee Name', 'Purchase Category',
           'Item Description', 'Item Number', 'PO Amount', 'PO Line Number', 'Item Qty', 'Item UoM',
           'Item Unit Price', 'Item Extended Price', 'Tax Amount', 'PO Line Amount', 'PO Line Spend Amount to Date',
           'PO Line Distribution Number', 'PO Line Distribution Amount', 'PO Line Distribution Spend Amount to Date',
           'Charge Entity', 'Charge Fund', 'Charge Financial Department', 'Charge Account', 'Charge Purpose',
           'Charge Program', 'Charge Project']
PNL_COLS = ['Financial Department', 'Fund', 'Project Description', 'Sum of 3XXXXX-Beginning Balance',
            'Sum of 4XXXXX-All Revenue', 'Sum of 5XXXXX-All Expenses', 'Sum of Ending Balance (3X + 4X + 5X + 8X)']
GLIDE_COLS = ['Report Type', 'Journal Source', 'External System Identifier', 'ERP Creation Date', 'Accounting Date',
              'Transaction Status', 'GL Entity', 'GL Fund', 'GL Fund Name', 'GL Financial Department',
              'GL Natural Account', 'GL Natural Account Name', 'GL Project', 'PPM Comment', 'Debit Amount',
              'Credit Amount', 'Description', 'udfString1', 'udfString2']
ORDER_COLS = ['Order Number', 'User', 'Group', 'Fin Account', 'Service Name', 'Service Group', 'Project Name',
              'Unit price', 'Quantity ordered', 'Price', 'Invoiced - Y/N,', 'Date Ordered', 'Date Accepted',
              'Date Completed', 'Assigned to', 'Additional Info-attached manifest']

ACCOUNTS = {
    "410000": "External Sales and Services", "775000": "Internal Recharge Revenue",
    "785000": "Intercampus Recharge Revenue", "775B10": "Appropriation Transfers In",
    "770009": "Central Campus Income Assessment Expense", "775004": "Central Campus Income Assessment Revenue",
    "445100": "Other Operating Revenues Contra Bad Debts", "770006": "Other Support Services",
    "500100": "Salaries - Staff Career", "501000": "Salaries - Student Assistants", "508000": "Employee Benefits",
    "522400": "Lab Supplies and Accessories", "522401": "Lab Chemicals and Gases", "530102": "Outside Purchased Services",
    "532302": "Repairs and Maintenance", "525900": "Capital Expense Equipment", "539000": "Freight and Shipping",
    "540100": "Travel - Domestic", "300001": "Net Position Department Share",
}
SUPPLIERS = {"522400": ["NORTHWIND SCIENTIFIC LLC", "FABRIKAM LABWARE INC"],
             "522401": ["TAILSPIN GASES CO"], "530102": ["LITWARE ANALYTICS SERVICES"],
             "532302": ["CONTOSO INSTRUMENTS SERVICE"], "525900": ["CONTOSO INSTRUMENTS INC"],
             "539000": ["ADATUM FREIGHT"]}

SYLL_A = ["Var", "Bel", "Cor", "Dal", "Est", "Fen", "Gor", "Hal", "Isk", "Jor", "Kel", "Lun", "Mor", "Nev", "Ost",
          "Pell", "Quin", "Ros", "Sav", "Tor", "Ulm", "Vex", "Wyn", "Yar", "Zel"]
SYLL_B = ["anth", "ewick", "orrow", "ishby", "aquin", "ondel", "ustry", "emoor", "arvel", "ilton"]
FIRST = ["Ariel", "Bryn", "Cass", "Dara", "Emery", "Finn", "Gale", "Harper", "Indy", "Jules", "Kai", "Lane", "Morgan",
         "Noor", "Oakley", "Parker", "Quinn", "Reese", "Sage", "Tatum"]
SERVICES = [("Confocal session (hour)", "Microscopy", 390), ("Light-sheet session (hour)", "Microscopy", 570),
            ("Image analysis (hour)", "Analysis", 480), ("Sample preparation", "Prep", 240),
            ("Training session", "Training", 900)]
EXTERNAL_DOMAINS = ["ucla.edu", "berkeley.edu", "ucsf.edu", "stanford.edu", "uni-example.ac.uk", "acmebio.com",
                    "globex-therapeutics.com", "example.org"]
STAFF = ["Tech One", "Tech Two", "Manager Example"]


def _write(path, header, rows, sheet, preamble=None):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for line in preamble or []:
        ws.append(line)
    ws.append(header)
    for r in rows:
        ws.append([r.get(c) for c in header])
    wb.properties.created = wb.properties.modified = datetime(2026, 10, 1)
    wb.save(path)


def _months(start, end):
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def _fy(d):
    return d.year + 1 if d.month >= 7 else d.year


def make_gl(rng):
    rows = []
    seq = [100000]

    def add(fund, acct, date, amount, cat, jname=None, supplier="", line=""):
        seq[0] += 1
        rows.append({"fund": fund, "account": acct, "date": date, "amount": round(amount, 2), "category": cat,
                     "journal": jname or f"{cat} {seq[0]}", "supplier": supplier, "line": line, "seq": seq[0]})

    for y, m in _months((2024, 1), (2026, 9)):
        d = lambda day: datetime(y, m, day)  # noqa: E731
        ext = 0.0
        for day in (8, 22):
            amt = round(rng.uniform(7000, 15000), 2)
            ext += amt
            add("12100", "410000", d(day), -amt, "Receivables")
        assess_acct = "775004" if d(1) >= datetime(2025, 7, 1) else "770009"
        assess = round(0.15 * ext, 2) + (12.34 if (y, m) == (2024, 6) else 0.0)
        add("12100", assess_acct, d(28), assess, "Allocations", jname=f"Income assessment {y}-{m:02d}")
        for day in (5, 15, 25):
            add("12100", "775000", d(day), -rng.uniform(13000, 21000), "Recharge")
        add("12100", "785000", d(18), -rng.uniform(1500, 5500), "Recharge")
        if m == 8:
            add("13U00", "775B10", d(2), -60000.0, "Allocations", jname=f"FY{_fy(d(2))} appropriation")
        if m == 7:
            add("12100", "300001", d(1), -rng.uniform(15000, 30000), "Carry Forward", jname="ANNUAL CARRY FORWARD")
            add("16200", "300001", d(1), -rng.uniform(70000, 90000), "Carry Forward", jname="ANNUAL CARRY FORWARD")
        sal = 34000 if _fy(d(1)) < 2026 else 36500
        add("12100", "500100", d(28), sal + rng.uniform(-500, 500), "Payroll")
        add("13U00", "500100", d(28), 6000.0, "Payroll")
        add("12100", "501000", d(28), rng.uniform(1500, 3000), "Payroll")
        add("12100", "508000", d(28), rng.uniform(11000, 13000), "Payroll")
        add("13U00", "508000", d(28), 2100.0, "Payroll")
        for acct, lo, hi, n in [("522400", 1200, 3500, 3), ("522401", 400, 1500, 2), ("530102", 500, 2500, 1),
                                ("539000", 80, 400, 1), ("540100", 0, 1200, 1)]:
            for _ in range(n):
                sup = rng.choice(SUPPLIERS.get(acct, [""]))
                add("12100", acct, d(rng.randint(3, 26)), rng.uniform(lo, hi), "Purchase Invoices", supplier=sup,
                    line=f"{ACCOUNTS[acct].lower()} order")
        if m in (1, 4, 7, 10):
            add("12100", "532302", d(12), rng.uniform(12000, 18000), "Purchase Invoices",
                supplier=SUPPLIERS["532302"][0], line="service contract quarter")
        add("12100", "770006", d(20), rng.uniform(60, 220), "Recharge", jname=f"Aggieship freight {y}-{m:02d}")
        if (y, m) == (2025, 3):
            add("12100", "445100", d(30), 1200.0, "Receivables", jname="Bad debt write-off")
        if (y, m) == (2024, 10):
            add("12100", "525900", d(17), 48000.0, "Purchase Invoices", supplier=SUPPLIERS["525900"][0],
                line="stage controller upgrade")
        if (y, m) == (2025, 11):
            add("16200", "525900", d(6), 31000.0, "Purchase Invoices", supplier=SUPPLIERS["525900"][0],
                line="detector replacement")
    # a fund outside the config, to prove it is filtered out
    add("20700", "522400", datetime(2025, 2, 3), 999.0, "Purchase Invoices")
    return rows


def gl_page_rows(gl):
    out = []
    for r in gl:
        out.append({
            "Entity": "3110", "Entity Description": "UC Davis Campus", "Fund": r["fund"],
            "Fund Description": FUNDS.get(r["fund"], "Private Contracts"), "Financial Department": DEPT,
            "Financial Department Description": DEPT_DESC, "Account": r["account"],
            "Account Description": ACCOUNTS[r["account"]], "Purpose": "40",
            "Purpose Description": "Instruction Dept Research", "Program": "000",
            "Program Description": "Default Program Value", "Project": PROJECT, "Project Description": PROJECT_DESC,
            "Activity": "000000", "Activity Description": "Default Activity Value", "Document Type": "Journal",
            "Accounting Sequence Number": str(r["seq"]), "Journal Source": r["category"],
            "Journal Category": r["category"], "Journal Batch Name": f"Batch {r['seq']}",
            "Journal Name": r["journal"], "Journal Line Description": r["line"] or "Journal Import Created",
            "Accounting Period": r["date"].strftime("%b-%y"), "Journal Accounting Date": r["date"],
            "Journal Type": "A", "Journal Status": "Posted", "Commitments": 0, "Obligations": 0,
            "Actuals": r["amount"]})
    return out


def gl_wide_rows(gl):
    out = []
    for r in gl:
        if not (r["date"].year == 2025 and r["date"].month == 3 and r["account"].startswith("5")
                and r["fund"] in FUNDS):
            continue
        out.append({
            "Entity": "3110", "Entity Description": "UC Davis Campus", "Fund": r["fund"],
            "Fund Description": FUNDS[r["fund"]], "Financial Department": DEPT,
            "Financial Department Description": DEPT_DESC, "Parent A Account": "52000A-Supplies and Services",
            "Account": r["account"], "Account Description": ACCOUNTS[r["account"]], "Project": PROJECT,
            "Project Description": PROJECT_DESC, "JE Source": r["category"], "JE Category": r["category"],
            "JE Name": r["journal"], "JE Accounting Period": "Mar-25", "JE Accounting Date": r["date"],
            "JE Type": "A", "JE Status": "Posted", "Accounted Dr ": max(r["amount"], 0),
            "Accounted Cr ": max(-r["amount"], 0), "Accounted Net": r["amount"],
            "JE Line Description": r["line"], "Transaction Line Description": r["line"],
            "Supplier/Customer Name": r["supplier"], "PO Number": f"UCDPO{r['seq']:08d}" if r["supplier"] else ""})
    return out


def po_rows(rng):
    rows = []
    n = 1077000
    for y, m in _months((2023, 12), (2026, 4)):
        for acct in ["522400", "522401", "530102"]:
            n += 1
            amt = round(rng.uniform(800, 4000), 2)
            sup = rng.choice(SUPPLIERS[acct])
            rows.append({"Purchase Order": str(n), "PO Status": "CLOSED", "Buyer": "Buyer Example",
                         "PO Creation Date": datetime(y, m, rng.randint(1, 26)).strftime("%m-%d-%Y"),
                         "Supplier Name": sup, "Item Description": f"{ACCOUNTS[acct]} item",
                         "PO Line Distribution Amount": amt, "PO Amount": amt,
                         "Charge Entity": "3110 - UC Davis Campus",
                         "Charge Fund": "12100 - Sales and Services Rate Based",
                         "Charge Financial Department": f"{DEPT} - {DEPT_DESC}",
                         "Charge Account": f"{acct} - {ACCOUNTS[acct]}",
                         "Charge Project": f"{PROJECT} - {PROJECT_DESC}"})
    for created, acct, amt, fund in [("07-02-2024", "532302", 64000.0, "12100"),
                                     ("07-01-2025", "532302", 66000.0, "12100"),
                                     ("10-02-2024", "525900", 48000.0, "12100"),
                                     ("11-01-2025", "525900", 31000.0, "16200")]:
        n += 1
        rows.append({"Purchase Order": str(n), "PO Status": "OPEN", "PO Creation Date": created,
                     "Supplier Name": SUPPLIERS[acct][0], "Item Description": f"{ACCOUNTS[acct]}",
                     "PO Line Distribution Amount": amt, "PO Amount": amt,
                     "Charge Fund": f"{fund} - {FUNDS[fund]}", "Charge Account": f"{acct} - {ACCOUNTS[acct]}"})
    return rows


PO_PREAMBLE = [["UCD Comprehensive Spend Report"], [], ["Report Run Date", "2026-04-02 11:46:48 AM"], [],
               ["Procurement BU", "UCD Business Unit", "PO Creation Date From", "PO Creation Date To"],
               ["PO Number", "All", "Buyer", "All", "Supplier Name", "All"],
               ["PO Amount Range From", "PO Amount Range To", "PO Status", "All"],
               ["Charge Entity", "All", "Charge Fund", "All", "Charge Financial Department", DEPT],
               ["Charge Program", "All", "Charge Project", "All"],
               ["Project Expenditure Type", "All", "Project Task", "All"], []]


def pnl_rows(gl):
    """FY2026 Department P&L built from the sample ledger, so its activity reconciles with the GL."""
    begin = {"12100": -21500.0, "13U00": 0.0, "16200": -81000.0}
    rows = [dict(zip(PNL_COLS, (DEPT, "12100", "EXAMPLE SIDE PROJECT", 0, 520, -520, 0)))]
    tot = [0.0, 0.0, 0.0, 0.0]
    for i, fund in enumerate(["12100", "13U00", "16200"]):
        fy = [r for r in gl if r["fund"] == fund and datetime(2025, 7, 1) <= r["date"] < datetime(2026, 7, 1)]
        rev = round(sum(r["amount"] for r in fy if r["account"][0] in "47"), 2)
        exp = round(sum(r["amount"] for r in fy if r["account"][0] == "5"), 2)
        end = round(begin[fund] + rev + exp, 2)
        rows.append(dict(zip(PNL_COLS, (None if i == 0 else DEPT, None if i == 0 else fund, PROJECT_DESC,
                                        begin[fund], rev, exp, end))))
        for j, v in enumerate((begin[fund], rev, exp, end)):
            tot[j] += v
    rows.append(dict(zip(PNL_COLS, ["Grand Total", None, None] + [round(t, 2) for t in tot])))
    return rows


def glide_rows(rng):
    rows = []
    names = ["Pat Example", "Sam Placeholder"]
    for y, m in _months((2025, 7), (2026, 9)):
        for cat, acct, lo, hi in [("Travel - Domestic", "540100", 0, 900), ("Freight Out", "539000", 20, 250),
                                  ("Supplies - Card Purchases", "522400", 50, 600)]:
            amt = round(rng.uniform(lo, hi), 2)
            if amt <= 0:
                continue
            d = datetime(y, m, rng.randint(2, 27))
            rows.append({"Report Type": "GL Expense", "Journal Source": "UCD Card", "Accounting Date": d,
                         "ERP Creation Date": d, "Transaction Status": "PROCESSED", "GL Entity": "3110",
                         "GL Fund": "12100", "GL Fund Name": FUNDS["12100"], "GL Financial Department": DEPT,
                         "GL Natural Account": acct, "GL Natural Account Name": cat, "GL Project": PROJECT,
                         "PPM Comment": f"{rng.choice(names)} purchase", "Debit Amount": amt, "Credit Amount": None,
                         "Description": cat, "udfString1": rng.choice(names)})
        rows.append({"Report Type": "GL Revenue", "Accounting Date": datetime(y, m, 15), "GL Fund": "12100",
                     "GL Natural Account": "410000", "GL Natural Account Name": "External Sales",
                     "Debit Amount": None, "Credit Amount": round(rng.uniform(100, 900), 2)})
    return rows


def _groups(rng):
    used, groups = set(), []
    kinds = ["ucd"] * 24 + ["ext"] * 14 + ["po"] * 2
    for kind in kinds:
        while True:
            last = rng.choice(SYLL_A) + rng.choice(SYLL_B)
            first = rng.choice(FIRST)
            if (last, first) not in used:
                used.add((last, first))
                break
        if kind == "ucd":
            fin = f"{rng.randint(1, 3)}-{last[:3].upper()}{rng.randint(100, 999)}"
        elif kind == "ext":
            fin = f"EXTERNAL - {first.lower()}.{last.lower()}@{rng.choice(EXTERNAL_DOMAINS)}"
        else:
            fin = str(rng.randint(10 ** 9, 10 ** 10 - 1))
        groups.append({"group": f"{last}, {first}", "fin": fin, "weight": rng.choice([1, 1, 1, 2, 3, 6]),
                       "start": rng.choice([2023, 2024, 2024, 2025, 2025, 2026]), "users": [
                           f"{rng.choice(FIRST)} {rng.choice(SYLL_A)}{rng.choice(SYLL_B)}" for _ in range(2)]})
    return groups


def order_rows(rng):
    rows, n = [], 200000
    groups = _groups(rng)
    end = datetime(2026, 9, 30)
    for y, m in _months((2023, 7), (2026, 9)):
        for g in groups:
            if _fy(datetime(y, m, 1)) < g["start"] + (1 if g["start"] == 2023 else 0) - 1:
                continue
            if rng.random() > 0.12 * g["weight"]:
                continue
            n += 1
            ordered = datetime(y, m, rng.randint(1, 26), rng.randint(8, 17), rng.randint(0, 59), rng.randint(0, 59))
            r = rng.random()
            accepted = None if r < 0.03 else ordered + timedelta(hours=rng.randint(1, 72))
            completed = None
            if accepted is not None:
                done = accepted + timedelta(days=rng.randint(2, 30), hours=rng.randint(0, 8))
                open_ = (end - ordered).days < 45 and rng.random() < 0.6 or rng.random() < 0.02
                completed = None if open_ or done > end else done
            for svc, sgroup, price in rng.sample(SERVICES, rng.choice([1, 1, 2])):
                qty = rng.randint(1, 12)
                fmt = lambda t: t.strftime("%Y/%m/%d %H:%M:%S") if t else None  # noqa: E731
                rows.append({"Order Number": str(n), "User": rng.choice(g["users"]), "Group": g["group"],
                             "Fin Account": g["fin"], "Service Name": svc, "Service Group": sgroup,
                             "Unit price": price, "Quantity ordered": qty, "Price": price * qty,
                             "Invoiced - Y/N,": "N" if completed and rng.random() < 0.03 else "Y",
                             "Date Ordered": fmt(ordered), "Date Accepted": fmt(accepted),
                             "Date Completed": fmt(completed), "Assigned to": rng.choice(STAFF)})
    # same lab, different capitalisation (real exports have this)
    rows[5]["Group"] = rows[5]["Group"].upper()
    return rows


CONFIG = """# Example configuration for the fictional sample core. Copy and edit for a real core.
core_name: "Example Imaging Core"
short_name: "Imaging Core"
financial_department: "XIMG001"
project: "AR09999901"
funds:
  "12100": {label: "Revenue (12100)", role: operating}
  "16200": {label: "Reserve Funds (16200)", role: reserve}
  "13U00": {label: "General Funds (13U00)", role: general}
personnel_prefixes: ["500", "501", "505", "506", "508"]
brand: {primary: "#022851", accent: "#FFBF00"}
rcci_window: {start: "2023-07-01", end: "2026-03-31"}
assessment_note: null
coa_overrides: {}
"""


def generate(out_dir, seed: int = 2026) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    gl = make_gl(rng)
    _write(out / "gl_page_2024-01_to_2026-09.xlsx", PAGE_COLS, gl_page_rows(gl), "page")
    wide_pre = [["UCD Transaction Listing Report - GL and Subledger Detail"], [], ["Date: 2026-04-13"], [],
                ["Parameters"]] + [[f"{k}: "] for k in ["From Date", "To Date", "From Period", "To Period",
                                                         "Journal Source", "Journal Category", "Journal Batch Name",
                                                         "Journal Name", "Journal Type", "Posting Status",
                                                         "Transaction Number", "PO Number",
                                                         "Supplier/Customer Name", "Entity", "Fund",
                                                         "Financial Department", "Account", "Purpose", "Program",
                                                         "Project", "Activity", "Inter Entity"]] + [[]]
    _write(out / "gl_wide_2025-03.xlsx", WIDE_COLS, gl_wide_rows(gl), "Sheet1", preamble=wide_pre)
    _write(out / "po_spend_2023-12_to_2026-04.xlsx", PO_COLS, po_rows(rng), "Sheet1", preamble=PO_PREAMBLE)
    _write(out / "pnl_fy2026.xlsx", PNL_COLS, pnl_rows(gl), "Balances")
    _write(out / "glide_fy2026.xlsx", GLIDE_COLS, glide_rows(rng), "page")
    _write(out / "ppms_order_details.xlsx", ORDER_COLS, order_rows(rng), "Order details report")
    (out / "core-config.yaml").write_text(CONFIG)


if __name__ == "__main__":
    generate(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "example_core")
