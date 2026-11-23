"""Computer MCP replay for the preopened Calc worksheet, pending desktop calibration."""

from pathlib import Path

from computer import act, key, type_text, wait


HANDOVER = ("=SUM('Dock Stock'.E6:E8)", "=SUM('Clinic Dispatch'.F6:F8)",
            "=SUM('Transfer Control'.H6:H8)", "=SUM('Clinic Dispatch'.G6:G8;'Transfer Control'.I6:I8)")
DOCK = (
    '=SUMIFS(\'Count Log\'.$E$6:$E$17;\'Count Log\'.$A$6:$A$17;A{r};\'Count Log\'.$B$6:$B$17;B{r};\'Count Log\'.$C$6:$C$17;"Released";\'Count Log\'.$D$6:$D$17;"<="&Shift.$B$5)',
    "=MAX(0;D{r}-C{r})",
)
CLINIC = (
    '=SUMIFS(\'Order Queue\'.$E$6:$E$16;\'Order Queue\'.$A$6:$A$16;A{r};\'Order Queue\'.$B$6:$B$16;B{r};\'Order Queue\'.$C$6:$C$16;"Confirmed";\'Order Queue\'.$D$6:$D$16;"<="&Shift.$B$6)',
    "=MIN(E{r};MAX(0;C{r}-D{r}))",
    "=E{r}-F{r}",
)
TRANSFER = (
    '=SUMIFS(\'Lane Staging\'.$F$6:$F$16;\'Lane Staging\'.$A$6:$A$16;A{r};\'Lane Staging\'.$B$6:$B$16;B{r};\'Lane Staging\'.$C$6:$C$16;C{r};\'Lane Staging\'.$D$6:$D$16;Shift.$B$7;\'Lane Staging\'.$E$6:$E$16;"Cleared")',
    "=MAX(0;INT(MIN(G{r}-D{r};E{r})/F{r}))*F{r}",
    "=E{r}-H{r}",
)


def shot(name):
    logs = Path("/logs/agent/desktop")
    logs.mkdir(parents=True, exist_ok=True)
    (logs / name).write_bytes(act("screenshot"))


def write_cells(column, row, formulas):
    key("Ctrl+Shift+F5")
    key("Ctrl+a")
    type_text(f"{chr(64 + column)}{row}")
    key("Return")
    for formula in formulas:
        key("F2")
        type_text(formula)
        key("Return")


def fill_block(start_column, formulas):
    for col, template in enumerate(formulas, start_column):
        write_cells(col, 6, [template.format(r=row) for row in (6, 7, 8)])


def main():
    shot("shift-inputs.png")
    for column, spec, name in ((4, DOCK, "dock-stock"), (5, CLINIC, "clinic-dispatch"),
                               (7, TRANSFER, "transfer-control")):
        key("Ctrl+Page_Down")
        fill_block(column, spec)
        shot(f"{name}.png")
    key("Ctrl+Page_Up", repeat=3)
    write_cells(6, 5, HANDOVER)
    key("Ctrl+s")
    wait(2)
    shot("shift-handover.png")


if __name__ == "__main__":
    main()
