"""Check correct live spreadsheet formulas against changed shift conditions."""

from copy import deepcopy
from datetime import time
import json
import math
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.datetime import to_excel
from openpyxl.utils.exceptions import InvalidFileException

from cuaverify import InfraError, OUTPUT_DIR, run
from formulas import SUPPORTED, WorkbookFormulas


PROBES = (
    {},
    {"Shift": {"B5": 515 / 1440, "B6": 3, "B7": "Afternoon"}},
    {"Shift": {"B5": 548 / 1440, "B6": 1}, "Clinic Dispatch": {"C6": 7},
     "Transfer Control": {"F6": 9, "E7": 1}},
    {"Count Log": {"E6": 31, "C7": "Released"}, "Order Queue": {"C8": "Confirmed", "E6": 61},
     "Lane Staging": {"E8": "Cleared", "F11": 39}},
)
BLOCKS = {
    "Dock Stock": ("R1.dock", "Dock releases matched by SKU, depot and ready time, with reserve held"),
    "Clinic Dispatch": ("R2.clinic", "Eligible confirmed route orders, dispatch capacity and quantified backorders"),
    "Transfer Control": ("R3.transfer", "Cleared current-wave units and only whole available cartons transferred"),
    "Shift": ("R4.handover", "Four recomputing totals for the supervisor handover"),
}


def same(left, right):
    if type(left) in (int, float) and type(right) in (int, float):
        return math.isclose(left, right, rel_tol=0, abs_tol=1e-9)
    return type(left) is type(right) and left == right


def read_submission():
    path = OUTPUT_DIR / "result.xlsx"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
        return {}, set(), {}
    try:
        workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
        with_workbook = {}
        formula_cells = set()
        limits = {}
        try:
            for sheet in workbook.worksheets:
                if (sheet.max_row or 0) > 150 or (sheet.max_column or 0) > 25:
                    return {}, set(), {}
                sheet_data = {}
                for row in sheet.iter_rows(min_row=1, max_row=150, min_col=1, max_col=25):
                    for cell in row:
                        if cell.value is None:
                            continue
                        value = cell.value
                        sheet_data[cell.coordinate] = to_excel(value) if isinstance(value, time) else value
                        if cell.data_type == "f" and isinstance(value, str):
                            formula_cells.add((sheet.title, cell.coordinate))
                with_workbook[sheet.title] = sheet_data
                limits[sheet.title] = sheet.max_row or 30
            return with_workbook, formula_cells, limits
        finally:
            workbook.close()
    except (OSError, BadZipFile, InvalidFileException, ValueError, KeyError, IndexError, ParseError):
        return {}, set(), {}


def scenarios(data):
    for probe in PROBES:
        variant = deepcopy(data)
        for name, edits in probe.items():
            variant.setdefault(name, {}).update(edits)
        yield variant


def table(data, sheet, columns, stop):
    return [[data[sheet][f"{col}{row}"] for col in columns] for row in range(6, stop + 1)]


def direct_results(source):
    counts = table(source, "Count Log", "ABCDE", 17)
    orders = table(source, "Order Queue", "ABCDE", 16)
    staged = table(source, "Lane Staging", "ABCDEF", 16)
    cutoff, priority, wave = (source["Shift"][cell] for cell in ("B5", "B6", "B7"))
    dock, clinic, transfer = {}, {}, {}
    for row, (sku, depot, reserve) in enumerate(table(source, "Dock Stock", "ABC", 8), 6):
        eligible = sum(qty for code, place, status, ready, qty in counts
                       if (code, place, status) == (sku, depot, "Released") and ready <= cutoff)
        dock.update({f"D{row}": eligible, f"E{row}": max(0, eligible - reserve)})
    for row, (sku, route, stock, reserve) in enumerate(table(source, "Clinic Dispatch", "ABCD", 8), 6):
        eligible = sum(qty for code, place, state, tier, qty in orders
                       if (code, place, state) == (sku, route, "Confirmed") and tier <= priority)
        shipping = min(eligible, max(stock - reserve, 0))
        clinic.update({f"E{row}": eligible, f"F{row}": shipping, f"G{row}": eligible - shipping})
    for row, (sku, origin, depot, reserve, demand, pack) in enumerate(table(source, "Transfer Control", "ABCDEF", 8), 6):
        eligible = sum(qty for code, start, end, scheduled, status, qty in staged
                       if (code, start, end, scheduled, status) == (sku, origin, depot, wave, "Cleared"))
        shipping = max(0, min(eligible - reserve, demand)) // pack * pack
        transfer.update({f"G{row}": eligible, f"H{row}": shipping, f"I{row}": demand - shipping})
    total = lambda rows, column: sum(rows[f"{column}{row}"] for row in (6, 7, 8))
    shift = {"F5": total(dock, "E"), "F6": total(clinic, "F"), "F7": total(transfer, "H"),
             "F8": total(clinic, "G") + total(transfer, "I")}
    return {"Dock Stock": dock, "Clinic Dispatch": clinic, "Transfer Control": transfer, "Shift": shift}


def working_formulas(sheet, want, engine):
    try:
        return all((sheet, cell) in engine.formula_cells and same(engine.cell(sheet, cell), value)
                   for cell, value in want.items())
    except SUPPORTED:
        return False


def preserved(source, saved, outputs):
    if source.keys() != saved.keys():
        return False
    for sheet, before in source.items():
        after = {cell: value for cell, value in saved[sheet].items() if cell not in outputs.get(sheet, ())}
        if before.keys() != after.keys() or any(not same(before[cell], after[cell]) for cell in before):
            return False
    return True


def evaluate(grader):
    try:
        reference = json.loads(Path(__file__).with_name("expected.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InfraError(f"Missing shift reference: {exc}") from exc
    source, outputs = reference["initial"], reference["outputs"]
    saved, formulas, limits = read_submission()
    passed = dict.fromkeys(BLOCKS, bool(saved))
    if saved:
        for scenario, submitted in zip(scenarios(source), scenarios(saved)):
            engine = WorkbookFormulas(submitted, formulas, limits)
            for sheet, expected in direct_results(scenario).items():
                passed[sheet] &= working_formulas(sheet, expected, engine)

    for name, (checkpoint, diagnostic) in BLOCKS.items():
        weight = 16 if name == "Shift" else 27
        grade = passed[name]
        if name == "Shift":
            grade &= all(passed.values())
        grader.add(checkpoint, weight, grade, diagnostic)
    grader.add("R5.preservation", 3, any(passed.values()) and preserved(source, saved, outputs),
               "Original shift controls, all source cells and non-output workbook areas unchanged")


if __name__ == "__main__":
    run("cua-smoke/calc-desktop-smoke", "0.2.0", evaluate)
