"""Normalize a projection from the native application for byte-exact reset checks."""
import json
from pathlib import Path
import sys


def write_snapshot(destination, data):
    if not isinstance(data, dict) or not data:
        raise ValueError("Native site projection must contain business records")
    path = Path(destination)
    temp = path.with_suffix(".new")
    temp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    temp.replace(path)


if __name__ == "__main__":
    write_snapshot(sys.argv[1], json.load(sys.stdin))
