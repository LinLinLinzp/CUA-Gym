"""D11 checks for the published checkpoint list and verifier reports."""

from collections import Counter
import json
from pathlib import Path
import re


COLUMNS = (
    ("id", "检查点编号"),
    ("requirement", "对应任务要求"),
    ("type", "要求类型"),
    ("evidence", "检查内容与证据"),
    ("rule", "判定标准"),
    ("implementation", "实现或评审方式"),
    ("weight", "分值/权重"),
    ("score_mode", "评分方式"),
    ("coverage", "覆盖状态"),
)
REQUIRED = {key: label for key, label in COLUMNS if key != "weight"}
HEADINGS = {
    **{label: key for key, label in COLUMNS},
    "id": "id",
    "checkpoint id": "id",
    "requirement": "requirement",
    "type": "type",
    "evidence": "evidence",
    "decision criteria": "rule",
    "implementation": "implementation",
    "score mode": "score_mode",
    "coverage": "coverage",
}


def markdown_cell(value):
    if value is None:
        return ""
    text = str(value).strip().replace("\\", "\\\\").replace("|", "\\|")
    return "<br>".join(text.splitlines())


def table_cells(line):
    line = line.strip()
    if line.startswith("|") and line.endswith("|"):
        return [cell.strip() for cell in re.split(r"(?<!\\)\|", line[1:-1])]
    return []


def unique_ids(ids, source):
    if not ids or any(not isinstance(value, str) or not value.strip() for value in ids):
        raise ValueError(f"D11 {source} must contain non-empty checkpoint IDs")
    duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"D11 {source} has duplicate checkpoint IDs: {', '.join(duplicates)}")
    return set(ids)


def compare_ids(ids, expected, source):
    actual = unique_ids(ids, source)
    if actual != expected:
        missing = ", ".join(sorted(expected - actual)) or "none"
        extra = ", ".join(sorted(actual - expected)) or "none"
        raise ValueError(f"D11 {source} IDs differ from rubric.json; missing [{missing}]; extra [{extra}]")


def check_checklist(markdown, rubric):
    expected = unique_ids([row.get("id") for row in rubric.get("checkpoints", [])], "rubric.json")
    lines = markdown.splitlines()
    if "## 全部检查点" in lines:
        lines = lines[lines.index("## 全部检查点") + 1:]
    for index, line in enumerate(lines):
        fields = [HEADINGS.get(cell.casefold()) for cell in table_cells(line)]
        if "id" in fields:
            break
    else:
        raise ValueError("D11 verifier-checkpoints.md has no checkpoint table")

    missing = [label for key, label in REQUIRED.items() if key not in fields]
    if missing:
        raise ValueError(f"D11 verifier-checkpoints.md is missing columns: {', '.join(missing)}")
    if any(fields.count(key) != 1 for key in REQUIRED):
        raise ValueError("D11 verifier-checkpoints.md repeats a required column")
    separator = table_cells(lines[index + 1]) if index + 1 < len(lines) else []
    if len(separator) != len(fields) or any(not re.fullmatch(r":?-+:?", cell) for cell in separator):
        raise ValueError("D11 verifier-checkpoints.md has an invalid table header separator")

    positions = {key: fields.index(key) for key in REQUIRED}
    ids = []
    for line in lines[index + 2:]:
        cells = table_cells(line)
        if not cells:
            break
        if len(cells) != len(fields):
            raise ValueError(f"D11 verifier-checkpoints.md has a malformed checkpoint row: {line}")
        checkpoint_id = cells[positions["id"]].strip("`")
        empty = [REQUIRED[key] for key, position in positions.items() if not cells[position].strip("` ")]
        if empty:
            raise ValueError(f"D11 verifier-checkpoints.md checkpoint {checkpoint_id!r} has empty fields: {', '.join(empty)}")
        ids.append(checkpoint_id)
    compare_ids(ids, expected, "verifier-checkpoints.md")
    return expected


def check_report(path: Path, expected, source):
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"D11 {source} could not read verifier report.json: {error}") from error
    checks = report.get("checks") if isinstance(report, dict) else None
    if not isinstance(checks, list) or not all(isinstance(check, dict) for check in checks):
        raise ValueError(f"D11 {source} report.json must contain a checks array")
    compare_ids([check.get("id") for check in checks], expected, source)
