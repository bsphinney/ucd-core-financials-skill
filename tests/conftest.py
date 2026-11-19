"""Builders for tiny export files in the real Aggie Enterprise / PPMS layouts."""
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from core_financials.config import load_config

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


def write_sheet(path: Path, header: list, rows: list, sheet="page", preamble: list | None = None):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for line in preamble or []:
        ws.append(line)
    ws.append(header)
    for r in rows:
        ws.append([r.get(c) for c in header])
    wb.save(path)
    return path


def page_row(fund, account, date, amount, desc="", jname="J1", cat="Payables"):
    d = pd.Timestamp(date)
    return {"Fund": fund, "Fund Description": "Fund " + str(fund), "Account": account,
            "Account Description": desc or f"Acct {account}", "Journal Category": cat, "Journal Name": jname,
            "Journal Line Description": "line", "Accounting Period": d.strftime("%b-%y"),
            "Journal Accounting Date": d.to_pydatetime(), "Actuals": amount}


def wide_row(fund, account, date, amount, supplier="", jname="J1"):
    d = pd.Timestamp(date)
    return {"Fund": fund, "Fund Description": "Fund " + str(fund), "Account": account,
            "Account Description": f"Acct {account}", "JE Category": "Purchase Invoices", "JE Name": jname,
            "JE Accounting Period": d.strftime("%b-%y"), "JE Accounting Date": d.to_pydatetime(),
            "Accounted Net": amount, "Supplier/Customer Name": supplier, "Transaction Line Description": "item"}


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "core-config.yaml"
    p.write_text('core_name: "Test Core"\nshort_name: "Test Core"\nfinancial_department: "XTST001"\n'
                 'funds:\n  "12100": {label: Revenue, role: operating}\n  "16200": {label: Reserve, role: reserve}\n')
    return load_config(p)
