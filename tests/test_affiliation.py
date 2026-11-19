import pandas as pd

from conftest import order_row, write_orders
from core_financials.affiliation import build_or_update, guess, load_affiliations
from core_financials.config import load_coa
from core_financials.ppms import load_orders

COA = load_coa()


def test_guess_table():
    assert guess("EXTERNAL - pi@ucla.edu", COA)[:2] == ("Ext-UC", "high")
    assert guess("EXTERNAL - pi@chem.berkeley.edu", COA)[:2] == ("Ext-UC", "high")
    assert guess("EXTERNAL - pi@ucdavis.edu", COA)[:2] == ("UC Davis", "low")
    assert guess("EXTERNAL - pi@stanford.edu", COA)[:2] == ("Ext-NP", "medium")
    assert guess("EXTERNAL - pi@uni.ac.uk", COA)[:2] == ("Ext-NP", "medium")
    assert guess("EXTERNAL - pi@acmebio.com", COA)[:2] == ("Ext-FP", "medium")
    assert guess("EXTERNAL - pi@somewhere.de", COA)[:2] == ("Unknown", "low")
    assert guess("3-ABCDEF1", COA)[:2] == ("UC Davis", "medium")
    assert guess("2-SFCMP-52203-4000-102006", COA)[:2] == ("UC Davis", "medium")
    assert guess("FPMORT5095-SU0002-4305901-770003", COA)[:2] == ("UC Davis", "medium")
    assert guess("4981764654", COA)[:2] == ("Unknown", "low")
    assert guess("Seevix", COA)[:2] == ("Unknown", "low")


def test_build_or_update_preserves_user_edits(tmp_path):
    p = write_orders(tmp_path / "o.xlsx", [order_row(1, "Alpha Lab", 1, "2025/01/02 10:00:00"),
                                           order_row(2, "Beta Lab", 1, "2025/01/02 10:00:00", fin="3-XYZ123")])
    orders = load_orders([p])
    csv = tmp_path / "affiliations.csv"
    pd.DataFrame([{"group": "Alpha Lab", "affiliation": "Ext-FP", "college": "", "department": "",
                   "confidence": "high", "reason": "checked by hand", "confirmed": "Y"}]).to_csv(csv, index=False)
    df = build_or_update(orders, csv, COA)
    alpha = df[df["group"] == "Alpha Lab"].iloc[0]
    assert (alpha["affiliation"], alpha["confirmed"]) == ("Ext-FP", "Y")
    beta = df[df["group"] == "Beta Lab"].iloc[0]
    assert (beta["affiliation"], beta["confirmed"]) == ("UC Davis", "N")
    aff = load_affiliations(csv)
    assert aff["beta lab"]["affiliation"] == "UC Davis"


def test_majority_vote(tmp_path):
    p = write_orders(tmp_path / "o.xlsx", [
        order_row(1, "G", 1, "2025/01/02 10:00:00", fin="EXTERNAL - a@ucla.edu"),
        order_row(2, "G", 1, "2025/01/02 10:00:00", fin="EXTERNAL - a@ucla.edu"),
        order_row(3, "G", 1, "2025/01/02 10:00:00", fin="12345678")])
    df = build_or_update(load_orders([p]), tmp_path / "a.csv", COA)
    assert df.iloc[0]["affiliation"] == "Ext-UC"
