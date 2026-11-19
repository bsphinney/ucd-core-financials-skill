from conftest import PAGE_COLS, WIDE_COLS, page_row, wide_row, write_sheet
from core_financials.gl import classify, load_gl, load_subledger
from core_financials.io_util import norm_code

PREAMBLE = [["UCD Transaction Listing Report - GL and Subledger Detail"]] + [[f"Param {i}"] for i in range(27)]


def test_norm_code():
    assert norm_code(410000.0) == "410000"
    assert norm_code(" 775B00 ") == "775B00"
    assert norm_code(None) == ""
    assert norm_code("13U00") == "13U00"


def test_header_row_found_below_parameter_block(tmp_path, cfg):
    rows = [wide_row("12100", "522400", "2025-03-0%d" % i, 10.0 * i, jname=f"J{i}") for i in (1, 2, 3)]
    p = write_sheet(tmp_path / "wide.xlsx", WIDE_COLS, rows, sheet="Sheet1", preamble=PREAMBLE)
    gl = load_gl([p], cfg)
    assert len(gl) == 3
    assert gl["amount"].sum() == 60.0


def test_codes_normalised(tmp_path, cfg):
    p = write_sheet(tmp_path / "page.xlsx", PAGE_COLS, [page_row(12100.0, 410000, "2025-01-05", -100.0)])
    gl = load_gl([p], cfg)
    assert gl.loc[0, "account"] == "410000"
    assert gl.loc[0, "fund"] == "12100"


def test_duplicate_month_files_not_double_counted(tmp_path, cfg):
    rows = [page_row("12100", "522400", "2025-01-05", 50.0), page_row("12100", "410000", "2025-01-06", -80.0)]
    a = write_sheet(tmp_path / "a.xlsx", PAGE_COLS, rows)
    b = write_sheet(tmp_path / "b.xlsx", PAGE_COLS, rows)
    assert load_gl([a, b], cfg)["amount"].sum() == load_gl([a], cfg)["amount"].sum()


def test_page_and_wide_overlap_keeps_supplier(tmp_path, cfg):
    a = write_sheet(tmp_path / "a.xlsx", PAGE_COLS, [page_row("12100", "522400", "2025-03-04", 42.5, jname="JX")])
    b = write_sheet(tmp_path / "b.xlsx", WIDE_COLS,
                    [wide_row("12100", "522400", "2025-03-04", 42.5, supplier="ACME LAB SUPPLY", jname="JX")],
                    sheet="Sheet1", preamble=PREAMBLE)
    gl = load_gl([a, b], cfg)
    assert len(gl) == 1 and gl.iloc[0]["layout"] == "page"
    sub = load_subledger([a, b], cfg)
    assert list(sub["supplier"]) == ["ACME LAB SUPPLY"]


def test_page_summary_rows_not_double_counted_with_wide_lines(tmp_path, cfg):
    """Real exports: the standard listing has one row per journal, the wide one has its individual lines."""
    a = write_sheet(tmp_path / "a.xlsx", PAGE_COLS, [page_row("12100", "522400", "2024-01-03", 4075.50, jname="JX")])
    b = write_sheet(tmp_path / "b.xlsx", WIDE_COLS,
                    [wide_row("12100", "522400", "2024-01-03", v, supplier="ACME", jname="JX")
                     for v in (551.00, 3800.00, -275.50)] +
                    [wide_row("12100", "522400", "2023-09-03", 999.0, supplier="ACME", jname="JOLD")],
                    sheet="Sheet1", preamble=PREAMBLE)
    gl = load_gl([a, b], cfg)
    assert gl["amount"].sum() == 4075.50
    assert load_subledger([a, b], cfg)["amount"].sum() == 4075.50 + 999.0


def test_funds_filtered_to_config(tmp_path, cfg):
    p = write_sheet(tmp_path / "p.xlsx", PAGE_COLS,
                    [page_row("12100", "522400", "2025-01-05", 5.0), page_row("20700", "522400", "2025-01-05", 9.0)])
    gl = load_gl([p], cfg)
    assert list(gl["fund"]) == ["12100"]


def test_classify_roles(tmp_path, cfg):
    accts = ["300001", "770009", "775004", "445100", "410000", "775000", "522400", "500100", "775B12", "599999"]
    p = write_sheet(tmp_path / "p.xlsx", PAGE_COLS,
                    [page_row("12100", a, "2025-01-05", 1.0 + i, jname=f"J{i}") for i, a in enumerate(accts)])
    gl = classify(load_gl([p], cfg), cfg).set_index("account")
    assert list(gl.loc[accts, "role"]) == ["carryforward", "assessment", "assessment", "contra", "income",
                                           "income", "expense", "expense", "income", "expense"]
    assert gl.loc["410000", "group"] == "External Sales & Services"
    assert gl.loc["775B12", "group"] == "Appropriations / Institutional Support"
    assert gl.loc["522400", "group"] == "Lab Supplies & Chemicals"
    assert gl.loc["599999", "group"] == "Other Operating"
    assert gl.loc["500100", "group"] == "Salaries & Wages"
    assert gl.loc["522400", "fy"] == 2025


def test_identical_lines_within_one_file_are_kept(tmp_path, cfg):
    row = page_row("12100", "522400", "2025-01-05", 46.66, jname="JSAME")
    a = write_sheet(tmp_path / "a.xlsx", PAGE_COLS, [row, row])
    b = write_sheet(tmp_path / "b.xlsx", PAGE_COLS, [row, row])
    assert load_gl([a], cfg)["amount"].sum() == 93.32
    assert load_gl([a, b], cfg)["amount"].sum() == 93.32
