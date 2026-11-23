"""Narrow canonical proof for a native mock's generated startup records."""

import hashlib
import json
import re
from datetime import datetime

# Fingerprint of the untouched stock Project Tracker/Tasks/Team graph from the
# pinned Airtable mock. The shape includes every field, value and relationship.
AIRTABLE_STOCK = "7fd335385a163f663c2e80b17c34d7e6b4778610461b686d8234b7287051d9d3"
GENERATED = re.compile(r"(?:base|tbl|fld|rec|view)_[a-z0-9]+")
BOOT_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z")


def canonical_json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def airtable_stock(base, tables):
    identities = {}

    def visit(value, key=None):
        if isinstance(value, dict):
            return {visit(k): visit(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [visit(v) for v in value]
        if key == "createdTime":
            if not isinstance(value, str) or not BOOT_TIME.fullmatch(value):
                raise ValueError("invalid stock creation timestamp")
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return "<boot-time>"
        if isinstance(value, str) and GENERATED.fullmatch(value):
            if value not in identities:
                identities[value] = f"<generated-{len(identities)}>"
            return identities[value]
        return value

    return visit({"base": base, "tables": tables})


def canonical_site_state(site, initial, current):
    """Keep raw bytes except for the exactly validated, randomly named Airtable sample."""
    if site != "airtable" or initial is None or current is None:
        return current
    try:
        seed = json.loads(initial)
        state = json.loads(current)
        new_bases = state["bases"].keys() - seed["bases"].keys()
        new_tables = state["tables"].keys() - seed["tables"].keys()
        if len(new_bases) != 1 or len(new_tables) != 2:
            return current
        base_id, = new_bases
        base = state["bases"][base_id]
        if base["id"] != base_id or len(base["tables"]) != 2 or set(base["tables"]) != new_tables:
            return current
        if not GENERATED.fullmatch(base_id) or not all(GENERATED.fullmatch(key) for key in new_tables):
            return current
        tables = [state["tables"][key] for key in base["tables"]]
        if any(row["id"] != key or row["baseId"] != base_id
               for key, row in zip(base["tables"], tables)):
            return current
        stock = airtable_stock(base, tables)
        if hashlib.sha256(canonical_json(stock)).hexdigest() != AIRTABLE_STOCK:
            return current
        # Normalize only these new entries. Changes to seeded records, UI
        # selections, account state or unexpected records remain observable.
        del state["bases"][base_id]
        state["bases"][stock["base"]["id"]] = stock["base"]
        for key, row in zip(base["tables"], stock["tables"]):
            del state["tables"][key]
            state["tables"][row["id"]] = row
        return canonical_json(state)
    except (KeyError, TypeError, AttributeError, ValueError, UnicodeError):
        return current
