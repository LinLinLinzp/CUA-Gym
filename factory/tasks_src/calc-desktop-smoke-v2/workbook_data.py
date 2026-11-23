"""Visible work order, source rows and author fixture formulas."""

from datetime import time


SHIFT = {"B5": time(9, 0), "B6": 2, "B7": "Morning"}
TABLES = {
    "Dock Stock": (
        ["SKU", "Depot", "Safety reserve", "Eligible units", "Free units"],
        [["FR-104", "Pier 3", 12], ["FR-107", "Pier 3", 8], ["FR-104", "Pier 7", 5]],
    ),
    "Clinic Dispatch": (
        ["SKU", "Route", "Stock", "Safety reserve", "Eligible order units", "Dispatch units", "Backorder units"],
        [["FR-104", "Crosstown", 51, 8], ["FR-107", "North Loop", 30, 4], ["FR-109", "North Loop", 15, 3]],
    ),
    "Transfer Control": (
        ["SKU", "Origin", "Destination", "Reserve", "Requested", "Carton size", "Cleared staged units", "Dispatch units", "Unfilled units"],
        [["FR-104", "Pier 3", "Canal DC", 9, 25, 6], ["FR-107", "Pier 3", "East DC", 6, 28, 8],
         ["FR-109", "Pier 7", "Canal DC", 5, 19, 4]],
    ),
    "Count Log": (
        ["SKU", "Depot", "QA disposition", "Ready time", "Units", "Lot"],
        [["FR-104", "Pier 3", "Released", time(8, 44), 18, "Q711"],
         ["FR-104", "Pier 3", "Hold", time(8, 10), 13, "Q712"],
         ["FR-104", "Pier 3", "Released", time(9, 0), 17, "Q714"],
         ["FR-104", "Pier 3", "Released", time(9, 9), 15, "Q719"],
         ["FR-104", "Pier 7", "Released", time(8, 57), 21, "Q725"],
         ["FR-107", "Pier 3", "Released", time(8, 32), 7, "Q729"],
         ["FR-107", "Pier 3", "Hold", time(8, 36), 15, "Q730"],
         ["FR-107", "Pier 3", "Released", time(9, 5), 11, "Q732"],
         ["FR-104", "Pier 7", "Released", time(9, 2), 9, "Q733"],
         ["FR-104", "Pier 7", "Hold", time(8, 9), 13, "Q734"],
         ["FR-108", "Pier 7", "Released", time(8, 51), 8, "Q736"],
         ["FR-107", "Pier 7", "Released", time(8, 36), 14, "Q737"]],
    ),
    "Order Queue": (
        ["SKU", "Route", "State", "Priority tier", "Units", "Order ref"],
        [["FR-104", "Crosstown", "Confirmed", 1, 23, "CO-719"],
         ["FR-104", "Crosstown", "Confirmed", 2, 25, "CO-720"],
         ["FR-104", "Crosstown", "Draft", 2, 10, "CO-721"],
         ["FR-104", "North Loop", "Confirmed", 1, 13, "CO-722"],
         ["FR-107", "North Loop", "Confirmed", 2, 18, "CO-724"],
         ["FR-107", "North Loop", "Confirmed", 3, 7, "CO-726"],
         ["FR-107", "North Loop", "Cancelled", 1, 11, "CO-727"],
         ["FR-109", "North Loop", "Confirmed", 1, 9, "CO-728"],
         ["FR-109", "North Loop", "Confirmed", 2, 8, "CO-729"],
         ["FR-109", "North Loop", "Draft", 2, 21, "CO-731"],
         ["FR-109", "Crosstown", "Confirmed", 1, 6, "CO-732"]],
    ),
    "Lane Staging": (
        ["SKU", "Origin", "Destination", "Wave", "Clearance", "Units", "Lane slip"],
        [["FR-104", "Pier 3", "Canal DC", "Morning", "Cleared", 17, "TR-101"],
         ["FR-104", "Pier 3", "Canal DC", "Morning", "Cleared", 21, "TR-102"],
         ["FR-104", "Pier 3", "Canal DC", "Morning", "Hold", 15, "TR-104"],
         ["FR-104", "Pier 3", "Canal DC", "Afternoon", "Cleared", 9, "TR-105"],
         ["FR-104", "Pier 3", "East DC", "Morning", "Cleared", 19, "TR-106"],
         ["FR-107", "Pier 3", "East DC", "Morning", "Cleared", 20, "TR-108"],
         ["FR-107", "Pier 3", "East DC", "Afternoon", "Cleared", 25, "TR-109"],
         ["FR-109", "Pier 7", "Canal DC", "Morning", "Cleared", 13, "TR-110"],
         ["FR-109", "Pier 7", "Canal DC", "Morning", "Cleared", 10, "TR-111"],
         ["FR-109", "Pier 3", "Canal DC", "Morning", "Cleared", 17, "TR-113"],
         ["FR-109", "Pier 7", "Canal DC", "Morning", "Hold", 5, "TR-114"]],
    ),
}

WORKSHEETS = ("Shift", *TABLES)
OUTPUTS = {
    "Dock Stock": ("D", "E"), "Clinic Dispatch": ("E", "F", "G"),
    "Transfer Control": ("G", "H", "I"),
}
OVERVIEW = {
    "F5": "=SUM('Dock Stock'!$E$6:$E$8)",
    "F6": "=SUM('Clinic Dispatch'!$F$6:$F$8)",
    "F7": "=SUM('Transfer Control'!$H$6:$H$8)",
    "F8": "=SUM('Clinic Dispatch'!$G$6:$G$8,'Transfer Control'!$I$6:$I$8)",
}


def data_range(sheet, column):
    return f"'{sheet}'!${column}$6:${column}${5 + len(TABLES[sheet][1])}"


def template_formulas():
    counts = [data_range("Count Log", col) for col in "EACBD"]
    orders = [data_range("Order Queue", col) for col in "EABCD"]
    staging = [data_range("Lane Staging", col) for col in "FABCDE"]
    dock, clinic, transfer = {}, {}, {}
    for row in (6, 7, 8):
        dock.update({
            f"D{row}": f'=SUMIFS({counts[0]},{counts[1]},A{row},{counts[3]},B{row},{counts[2]},"Released",{counts[4]},"<="&Shift!$B$5)',
            f"E{row}": f"=MAX(0,D{row}-C{row})",
        })
        clinic.update({
            f"E{row}": f'=SUMIFS({orders[0]},{orders[1]},A{row},{orders[2]},B{row},{orders[3]},"Confirmed",{orders[4]},"<="&Shift!$B$6)',
            f"F{row}": f"=MIN(E{row},MAX(0,C{row}-D{row}))",
            f"G{row}": f"=E{row}-F{row}",
        })
        transfer.update({
            f"G{row}": f'=SUMIFS({staging[0]},{staging[1]},A{row},{staging[2]},B{row},{staging[3]},C{row},{staging[4]},Shift!$B$7,{staging[5]},"Cleared")',
            f"H{row}": f"=MAX(0,INT(MIN(G{row}-D{row},E{row})/F{row}))*F{row}",
            f"I{row}": f"=E{row}-H{row}",
        })
    return {"Shift": OVERVIEW, "Dock Stock": dock, "Clinic Dispatch": clinic, "Transfer Control": transfer}
