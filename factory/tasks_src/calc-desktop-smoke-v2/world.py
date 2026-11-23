"""Stage a native Calc shift workbook and exact verifier fixtures."""

from datetime import time
import json
from pathlib import Path
import shutil
import sys

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.datetime import to_excel

from workbook_data import OUTPUTS, SHIFT, TABLES, WORKSHEETS, template_formulas


NAVY = "FF18314A"
TEAL = "FF007C84"
WHITE = "FFFFFFFF"
BLUE = "FFF0F5F8"
AMBER = "FFFFF1CC"
DESCRIPTIONS = {
    "Dock Stock": "Free stock by SKU and depot | Count only Released lots physically ready at or before the Shift cutoff.",
    "Clinic Dispatch": "Confirmed orders | Match SKU and route, then include priority tiers at or below the Shift ceiling.",
    "Transfer Control": "Cleared staged stock | Match SKU, origin, destination and the currently selected Shift wave.",
    "Count Log": "05:45 receiving handover | Released and held lots across both piers.",
    "Order Queue": "Clinic service desk export | Priority 1 is most urgent. Draft and cancelled orders are included for reference.",
    "Lane Staging": "Warehouse transfer slips | Select the scheduled wave and use only lines cleared for that lane.",
}
NOTES = {
    "Dock Stock": "Keep the safety reserve untouched. Free units can never be negative.",
    "Clinic Dispatch": "Keep the safety reserve. Ship the lesser of eligible demand and free stock; report all unshipped eligible units.",
    "Transfer Control": "Keep the reserve. Ship only whole cartons without exceeding free staged stock or the request; report the remainder.",
}


def band(sheet, coord, text, *, fill=NAVY, size=11):
    cell = sheet[coord]
    cell.value = text
    cell.font = Font(name="Carlito", color=WHITE, size=size, bold=True)
    cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(vertical="center", indent=1)


def title(sheet, last, heading, note):
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 95
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.merge_cells(f"A1:{last}1")
    band(sheet, "A1", heading, size=16)
    sheet.row_dimensions[1].height = 36
    sheet.merge_cells(f"A2:{last}2")
    sheet["A2"] = note
    sheet["A2"].font = Font(name="Carlito", size=11, color=NAVY)
    sheet.row_dimensions[2].height = 21


def styled_table(book, name, headers, rows):
    sheet = book.create_sheet(name)
    last = get_column_letter(len(headers))
    title(sheet, last, name, DESCRIPTIONS[name])
    if name in NOTES:
        sheet.merge_cells(f"A3:{last}3")
        sheet["A3"] = NOTES[name]
        sheet["A3"].font = Font(name="Carlito", size=11, italic=True, color=NAVY)
        sheet.row_dimensions[3].height = 20
    for col, header in enumerate(headers, 1):
        band(sheet, f"{get_column_letter(col)}5", header, fill=TEAL)
        sheet.column_dimensions[get_column_letter(col)].width = max(14, len(header) + 3)
    sheet.row_dimensions[5].height = 25
    sheet.freeze_panes = "C6"
    if name not in OUTPUTS:
        sheet.auto_filter.ref = f"A5:{last}{5 + len(rows)}"
    for offset, values in enumerate(rows, 6):
        sheet.row_dimensions[offset].height = 21
        for col in range(1, len(headers) + 1):
            letter = get_column_letter(col)
            value = values[col - 1] if col <= len(values) else None
            cell = sheet.cell(offset, col, value)
            color = AMBER if letter in OUTPUTS.get(name, ()) else BLUE if offset % 2 == 0 else WHITE
            cell.fill = PatternFill("solid", fgColor=color)
            cell.font = Font(name="Carlito", size=11, color=NAVY)
            cell.alignment = Alignment(vertical="center", indent=1)
            if isinstance(value, time):
                cell.number_format = "hh:mm"
            elif value is None or isinstance(value, int):
                cell.number_format = "0"
    if name in ("Clinic Dispatch", "Transfer Control"):
        sheet.conditional_formatting.add(f"{last}6:{last}8", CellIsRule(
            operator="greaterThan", formula=["0"], fill=PatternFill("solid", fgColor="FFFCCBD1"),
        ))


def build_workbook():
    book = Workbook()
    sheet = book.active
    sheet.title = "Shift"
    title(sheet, "F", "North Quay | Morning dispatch desk", "18 November 2026 · West docks and clinic delivery · local Portland time")
    for column, width in {"A": 23, "B": 18, "C": 6, "D": 22, "E": 15, "F": 16}.items():
        sheet.column_dimensions[column].width = width
    sheet.merge_cells("A4:B4")
    sheet.merge_cells("D4:E4")
    band(sheet, "A4", "Current shift inputs", fill=TEAL)
    band(sheet, "D4", "Supervisor handover", fill=TEAL)
    band(sheet, "F4", "Units", fill=TEAL)
    for row, label in enumerate(("Dock ready by", "Clinic tier ceiling", "Transfer wave"), 5):
        sheet[f"A{row}"] = label
        sheet[f"B{row}"] = SHIFT[f"B{row}"]
        sheet[f"B{row}"].fill = PatternFill("solid", fgColor=BLUE)
    sheet["B5"].number_format = "hh:mm"
    for row, label in enumerate(("Free dock stock", "Clinic units shipping", "Transfer units shipping", "Clinic + transfer gap"), 5):
        sheet.merge_cells(f"D{row}:E{row}")
        sheet[f"D{row}"] = label
        sheet[f"F{row}"].fill = PatternFill("solid", fgColor=AMBER)
        sheet[f"F{row}"].number_format = "0"
        sheet.row_dimensions[row].height = 22
    for row, text in {
        11: "Work in Dock Stock, Clinic Dispatch and Transfer Control, then link the handover panel above.",
        12: "The three source tabs reflect the shift export. Leave the records and settings as provided.",
        13: "Amber cells are the live calculations. Use SUMIFS for filtered cross-sheet totals and ordinary spreadsheet arithmetic.",
        14: "Blue controls can change after review, so the workbook must continue working when the shift is moved.",
    }.items():
        sheet.merge_cells(f"A{row}:F{row}")
        sheet[f"A{row}"] = text
        sheet[f"A{row}"].font = Font(name="Carlito", size=11, color=NAVY)
        sheet.row_dimensions[row].height = 20
    for name, (headers, rows) in TABLES.items():
        styled_table(book, name, headers, rows)
    return book


def safe_values(book):
    return {sheet.title: {cell.coordinate: to_excel(cell.value) if isinstance(cell.value, time) else cell.value
                          for row in sheet.iter_rows() for cell in row if cell.value is not None}
            for sheet in book.worksheets}


def build_fixture(initial, output, formulas, *, mutate=None):
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(initial, output)
    book = load_workbook(output)
    for name, updates in formulas.items():
        for coord, value in updates.items():
            book[name][coord] = value
    if mutate:
        mutate(book)
    book.save(output)


def set_formula(book, sheet, coord, formula):
    book[sheet][coord] = formula


def main(build):
    initial = build / "input" / "start.xlsx"
    initial.parent.mkdir(parents=True, exist_ok=True)
    book = build_workbook()
    book.save(initial)
    assert list(WORKSHEETS) == book.sheetnames
    formulas = template_formulas()
    expected = {"initial": safe_values(book), "outputs": {sheet: list(rows) for sheet, rows in formulas.items()}}
    (build / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    static = {
        "Shift": {"F5": 39, "F6": 73, "F7": 48, "F8": 34},
        "Dock Stock": dict(zip(formulas["Dock Stock"], [35, 23, 7, 0, 21, 16])),
        "Clinic Dispatch": dict(zip(formulas["Clinic Dispatch"], [48, 43, 5, 18, 18, 0, 17, 12, 5])),
        "Transfer Control": dict(zip(formulas["Transfer Control"], [38, 24, 1, 20, 8, 20, 23, 16, 3])),
    }

    variants = {
        "golden": (formulas, None), "nop": ({}, None),
        "single_complete_transfer": ({"Transfer Control": formulas["Transfer Control"], "Shift": formulas["Shift"]}, None),
        "all_rectangles_totals_only": ({"Shift": formulas["Shift"]}, None),
        "static_final_numbers": (static, None),
        "constant_formula_snapshot": ({name: {cell: f"={value}" for cell, value in sheet.items()}
                                       for name, sheet in static.items()}, None),
        "miss_dock_cutoff": (formulas, lambda w: set_formula(w, "Dock Stock", "D6",
            "=SUMIFS('Count Log'!E6:E17,'Count Log'!A6:A17,A6,'Count Log'!B6:B17,B6,'Count Log'!C6:C17,\"Released\")")),
        "ignore_order_route": (formulas, lambda w: set_formula(w, "Clinic Dispatch", "E6",
            "=SUMIFS('Order Queue'!E6:E16,'Order Queue'!A6:A16,A6,'Order Queue'!C6:C16,\"Confirmed\",'Order Queue'!D6:D16,\"<=\"&Shift!$B$6)")),
        "send_partial_carton": (formulas, lambda w: set_formula(w, "Transfer Control", "H6", "=MAX(0,MIN(G6-D6,E6))")),
        "missing_handover": ({sheet: cells for sheet, cells in formulas.items() if sheet != "Shift"}, None),
        "overwrite_source_note": (formulas, lambda w: set_formula(w, "Count Log", "F17", "changed unrelated lot")),
        "equivalent_if_formula": (formulas, lambda w: set_formula(w, "Dock Stock", "E6", "=IF(D6>C6,D6-C6,0)")),
    }
    for name, (content, mutate) in variants.items():
        build_fixture(initial, build / "variants" / name / "output" / "result.xlsx", content, mutate=mutate)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
