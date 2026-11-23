"""Verifier grounded in the sideboard thread, offered slots and surveyed floor plan."""
import base64
from datetime import datetime
import math
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zlib

from cuaverify import InfraError, OUTPUT_DIR, VAR_DIR, load_site, plain, run

TASK = "cu10-furniture-delivery-reschedule"
VERSION = "1.0.1"
ORDER = "wf-maple-461"
SHIPMENT = "wf-maple-461-s1"
APPOINTMENT = "appt-wf-maple-461-s1"
SLOT = "wf-maple-461-s1-tue-pm"
ASANA_TASK = "install-reading-103"
PROJECT = "maple-install"
CHANNEL = "furniture-deliveries"
THREAD = "maple-sideboard"
OUTPUT = "Maple-Reading-Room-Delivery.drawio"
REFERENCE = "Maple-Reading-Room-Working.drawio"
CARRY_PATH = ("truck", "south-gate", "south-hall", "lift", "room")
ZONE = "America/New_York"
DRAWING_LIMIT = 3_000_000


def keyed(rows, key="id"):
    return {row[key]: row for row in rows}


def omit(row, *keys):
    return {k: v for k, v in row.items() if k not in keys}


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.utcoffset() is not None else None
    except (AttributeError, ValueError):
        return None


def normalize(content):
    body = plain(content)
    body = body.replace("–", "-").replace("—", "-").replace("→", " to ")
    return re.sub(r"(?<=\d)(am|pm)\b", r" \1", body)


def delivery_window(body):
    body = normalize(body)
    occurs = re.search(r"\b(?:nov(?:ember)?\.?\s+24(?:th)?|24(?:th)?\s+nov(?:ember)?\.?|2026-11-24|11/24)(?!\d)", body)
    start = r"(?:noon|midday|12(?::00)?(?:\s*p\.?\s*m\.?)?)"
    finish = r"(?:4(?::00)?\s*p\.?\s*m\.?|(?:16:00|1600)|(?:4(?::00)?|four)(?=\s*(?:et\b|est\b|eastern\b)))"
    window = re.search(rf"(?<![\d:]){start}\s*(?:-|to|through|until|and)\s*{finish}(?![\da-z])", body)
    zone = re.search(r"\b(?:eastern(?:\s+(?:standard\s+)?time)?|est|et|america/new_york)\b", body)
    return bool(occurs and window and zone)


def wayfair_checks(before, after):
    old_rows, new_rows = before["deliveryAppointments"], after["deliveryAppointments"]
    old = keyed(old_rows)[APPOINTMENT]
    changed = keyed(new_rows).get(APPOINTMENT, {})
    old_ids = {r["id"] for r in old_rows}
    replacements = [r for r in new_rows if r["id"] not in old_ids
                    and r.get("shipmentId") == SHIPMENT and r.get("orderId") == ORDER
                    and r.get("status") == "confirmed"]
    if len(replacements) != 1:
        return False, False, False
    new = replacements[0]
    protected_keys = ("orders", "shipments", "orderCancellations", "returns", "damageClaims")
    old_updated, replacement_created = instant(changed.get("updatedAt")), instant(new.get("createdAt"))
    w1 = (
        len(new_rows) == len(old_rows) + 1 and len(new_rows) == len(keyed(new_rows))
        and keyed([r for r in new_rows if r["id"] in old_ids and r["id"] != APPOINTMENT])
        == keyed([r for r in old_rows if r["id"] != APPOINTMENT])
        and all(before[key] == after[key] for key in protected_keys)
        and changed.get("status") == "rescheduled" and changed.get("replacedByAppointmentId") == new["id"]
        and changed.get("updatedBy") == new.get("actorId") == before["account"]["id"]
        and old_updated is not None and old_updated == replacement_created
        and old_updated > instant(old["createdAt"])
        and new.get("previousAppointmentId") == APPOINTMENT
        and omit(old, "status", "updatedAt", "updatedBy", "replacedByAppointmentId")
        == omit(changed, "status", "updatedAt", "updatedBy", "replacedByAppointmentId")
    )
    slot = keyed(keyed(before["shipments"])[SHIPMENT]["availableSlots"])[SLOT]
    w2 = (new.get("previousAppointmentId") == APPOINTMENT and new.get("slotId") == SLOT
          and new.get("timeZone") == ZONE
          and all(instant(new.get(key)) == instant(slot[key]) for key in ("startAt", "endAt")))
    body = normalize(new.get("instructions"))
    w3 = (approved_route(body)
          and re.search(r"\breceiving\b", body)
          and re.search(r"\b(?:check\s*-?\s*in|report|sign\s*-?\s*in|stop|register)\b", body)
          and re.search(r"\b(?:upright|up-right|vertical(?:ly)?|standing|do not tip|don't tip|never tip)\b", body)
          and not re.search(r"\b(?:lay|put|carry)(?:\s+\w+){0,3}\s+(?:flat|sideways)\b", body))
    return w1, w2, bool(w3)


def approved_route(body):
    prohibited = re.sub(
        r"\b(?:avoid|skip|instead of|do not (?:use|enter through)|never (?:use|enter through)|"
        r"not (?:the )?)(?:the )?\s*(?:north gate|gallery hall|courtyard)", "", body)
    return (
        all(re.search(term, body) for term in (r"\bsouth gate\b", r"\bservice hall(?:way)?\b",
                                              r"\bfreight (?:lift|elevator)\b", r"\b(?:reading )?room\s*#?\s*103\b"))
        and not re.search(r"\b(?:north gate|gallery hall)\b|\b(?:cross|cut through)\s+(?:the\s+)?courtyard\b", prohibited)
    )


def asana_checks(before, after):
    old = keyed(before["tasks"], "taskId")[ASANA_TASK]
    now = keyed(after["tasks"], "taskId").get(ASANA_TASK, {})
    a1 = (
        now.get("dueDate") == "2026-11-25"
        and len(before["tasks"]) == len(after["tasks"]) == len(keyed(after["tasks"], "taskId"))
        and keyed([r for r in before["tasks"] if r["taskId"] != ASANA_TASK], "taskId")
        == keyed([r for r in after["tasks"] if r["taskId"] != ASANA_TASK], "taskId")
        and keyed(before["comments"], "commentId") == keyed(after["comments"], "commentId")
        and omit(old, "dueDate", "description", "attachmentIds", "modifiedDate")
        == omit(now, "dueDate", "description", "attachmentIds", "modifiedDate")
    )
    body = normalize(now.get("description"))
    details = normalize(old["description"])
    retained = details in body or (
        re.search(r"\b(?:install|installation)\b.{0,35}\blong sideboard\b", body)
        and re.search(r"\b(?:protect|cover|safeguard)\b.{0,28}\bterrazzo\b", body)
        and re.search(r"\b(?:keep|leave)\b.{0,28}\bbrass floor outlet\b.{0,18}\b(?:accessible|clear|unobstructed)\b", body)
    )
    a2 = bool(retained and delivery_window(body) and approved_route(body))
    return a1, a2, now


def is_task_link(url):
    try:
        parsed = urlsplit(url)
        return (parsed.hostname in {"app.asana.com", "asana.com"}
                and ASANA_TASK in parsed.path.split("/"))
    except ValueError:
        return False


def teams_check(before, after):
    def all_messages(state):
        return {(container, msg["messageId"]): msg
                for container, messages in state["messages"].items() for msg in messages}

    old, now = all_messages(before), all_messages(after)
    if any(now.get(key) != record for key, record in old.items()):
        return False
    replies = [msg for key, msg in now.items() if key not in old and key[0] == CHANNEL
               and msg.get("containerId") == CHANNEL and msg.get("containerType") == "channel"
               and msg.get("senderId") == before["currentUser"]["userId"]
               and msg.get("replyToId") == THREAD and msg.get("messageType") == "message"
               and not msg.get("deletedDateTime")]
    for reply in replies:
        body = normalize(reply.get("content"))
        by_link = any(is_task_link(url.rstrip(").,;")) for url in re.findall(r"https://[^\s<>]+", reply.get("content", "")))
        named_place = "asana" in body and (
            "install long sideboard" in body
            or ("maple house fit-out" in body and ("sideboard" in body or "reading room 103" in body))
        )
        drawing = "draw.io" in body or "drawio" in body or "drawing" in body or "route diagram" in body
        if delivery_window(body) and "south gate" in body and drawing and (named_place or by_link):
            return True
    return False


def element(blob):
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", blob.replace(b"\x00", b""), re.I):
        raise ValueError("external declarations are not part of a draw.io model")
    return ET.fromstring(blob)


def diagram(raw):
    root = element(raw)
    if root.tag == "mxGraphModel":
        return None, None, 1, root
    if root.tag != "mxfile":
        raise ValueError("document is not an editable draw.io file")
    pages = root.findall("diagram")
    if not pages:
        raise ValueError("no editable page")
    page = next((page for page in pages if page.get("id") == "maple-l1"), pages[0])
    model = page.find("mxGraphModel")
    if model is None:
        bits = base64.b64decode("".join((page.text or "").split()), validate=True)
        inflater = zlib.decompressobj(-15)
        unpacked = inflater.decompress(bits, DRAWING_LIMIT * 3 + 1)
        if not inflater.eof or inflater.unconsumed_tail or len(unpacked) > DRAWING_LIMIT * 3:
            raise ValueError("invalid or oversize compressed model")
        model = element(unquote(unpacked.decode("ascii")).encode())
    if model.tag != "mxGraphModel":
        raise ValueError("invalid draw.io model")
    return page.get("id"), page.get("name"), len(pages), model


def cells(model):
    root = model.find("root")
    if root is None:
        raise ValueError("no editable graph root")
    result = {}
    for node in root:
        cell = node if node.tag == "mxCell" else node.find("mxCell")
        if cell is None:
            raise ValueError("invalid draw.io cell")
        fields = dict(cell.attrib)
        if node is not cell:
            fields.update({key: node.get(key) for key in ("id",) if node.get(key)})
            fields["value"] = node.get("label", node.get("value", fields.get("value", "")))
        cid = fields["id"]
        if cid in result:
            raise ValueError("duplicate graph cell")
        result[cid] = fields, cell.find("mxGeometry")
    return result


def styles(raw):
    named, attributes = [], {}
    for entry in raw.split(";"):
        if "=" in entry:
            key, value = entry.split("=", 1)
            if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                value = value.lower()
            attributes[key.strip()] = value.strip()
        elif entry.strip():
            named.append(entry.strip())
    return tuple(named), attributes


def finite(value):
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("non-finite drawing coordinate")
    return numeric


def rect(cell):
    geometry = cell[1]
    if geometry is None:
        raise ValueError("vertex has no geometry")
    return tuple(finite(geometry.get(name, "0")) for name in ("x", "y", "width", "height"))


def normalized_label(value):
    value = re.sub(r"<br\s*/?>|</(?:p|div)>", " ", value or "", flags=re.I)
    return plain(value)


def floor_plan(source, target):
    old_id, old_title, _, old_model = source
    new_id, new_title, count, new_model = target
    if count != 1 or (new_id is not None and (new_id, new_title) != (old_id, old_title)):
        return False
    model_fields = ("pageWidth", "pageHeight", "pageScale")
    if any(finite(old_model.get(key, "1")) != finite(new_model.get(key, "1")) for key in model_fields):
        return False
    if old_model.get("background", "#ffffff").lower() != new_model.get("background", "#ffffff").lower():
        return False
    old_cells = {cid: row for cid, row in cells(old_model).items() if row[0].get("edge") != "1"}
    new_cells = {cid: row for cid, row in cells(new_model).items() if row[0].get("edge") != "1"}
    if set(old_cells) != set(new_cells):
        return False
    for cid, (old, old_geom) in old_cells.items():
        new, new_geom = new_cells[cid]
        if any(old.get(key) != new.get(key) for key in ("parent", "vertex", "link", "visible")):
            return False
        if normalized_label(old.get("value")) != normalized_label(new.get("value")):
            return False
        if styles(old.get("style", "")) != styles(new.get("style", "")):
            return False
        if (old_geom is None) != (new_geom is None):
            return False
        if old_geom is not None:
            if new_geom.get("relative", "0") != old_geom.get("relative", "0") or list(new_geom):
                return False
            if any(abs(left-right) > 0.01 for left, right in zip(rect(old_cells[cid]), rect(new_cells[cid]))):
                return False
    return True


def point_inside_segment_box(start, end, box, stroke_width):
    """Clip the displayed segment to the surveyed keep-clear rectangle."""
    x, y, w, h = box
    pad = max(0.0, stroke_width / 2)
    first, last = 0.0, 1.0
    for a, b, low, high in zip(start, end, (x-pad, y-pad), (x+w+pad, y+h+pad)):
        delta = b-a
        if delta == 0.0:
            if a < low or a > high:
                return False
            continue
        t0, t1 = sorted(((low-a)/delta, (high-a)/delta))
        first, last = max(first, t0), min(last, t1)
        if first > last:
            return False
    return True


def terminal(cell, sty, direction, defaults):
    x, y, w, h = rect(cell)
    dx, dy = defaults
    return (x + w * finite(sty.get(direction+"X", dx)) + finite(sty.get(direction+"Dx", 0)),
            y + h * finite(sty.get(direction+"Y", dy)) + finite(sty.get(direction+"Dy", 0)))


def route_ok(model, trusted_model):
    graph, trusted = cells(model), cells(trusted_model)
    expected = set(zip(CARRY_PATH, CARRY_PATH[1:]))
    found = set()
    keep_clear = rect(trusted["keep-clear"])
    for fields, geometry in graph.values():
        if fields.get("edge") != "1":
            continue
        mapping = fields.get("source"), fields.get("target")
        if mapping not in expected or mapping in found or geometry is None:
            return False
        src, dst = mapping
        found.add(mapping)
        if src not in graph or dst not in graph or any(graph[cid][0].get("vertex") != "1"
                                                        for cid in mapping):
            return False
        _, sty = styles(fields.get("style", ""))
        width = finite(sty.get("strokeWidth", "1"))
        if (width <= 0 or sty.get("endArrow", "classic").lower() == "none"
                or sty.get("startArrow", "none").lower() != "none"
                or sty.get("strokeColor", "#000000").lower() in {"none", "transparent"}
                or finite(sty.get("opacity", "100")) <= 0 or fields.get("visible") == "0"):
            return False
        parent = graph.get(fields.get("parent"), ({}, None))[0]
        if parent.get("visible") == "0":
            return False
        points = [terminal(graph[src], sty, "exit", ("1", "0.5"))]
        for point in geometry.findall("./Array[@as='points']/mxPoint"):
            points.append((finite(point.get("x", 0)), finite(point.get("y", 0))))
        points.append(terminal(graph[dst], sty, "entry", ("0", "0.5")))
        if any(point_inside_segment_box(a, b, keep_clear, width) for a, b in zip(points, points[1:])):
            return False
    return found == expected


def diagrams():
    input_path = Path(__file__).parent / "reference-input" / REFERENCE
    if not input_path.exists():
        input_path = Path(__file__).parent.parent / "input" / REFERENCE
    try:
        trusted = diagram(input_path.read_bytes())
        cells(trusted[3])
    except (OSError, ValueError, KeyError, ET.ParseError, zlib.error) as exc:
        raise InfraError(f"cannot parse trusted floor plan: {exc}") from exc
    try:
        user_file = OUTPUT_DIR / OUTPUT
        if user_file.is_symlink() or not user_file.is_file() or user_file.stat().st_size > DRAWING_LIMIT:
            return False, False, None
        raw = user_file.read_bytes()
        parsed = diagram(raw)
    except (OSError, TypeError, ValueError, KeyError, ET.ParseError, zlib.error):
        return False, False, None
    try:
        route = route_ok(parsed[3], trusted[3])
    except (TypeError, ValueError, KeyError):
        route = False
    try:
        intact = floor_plan(trusted, parsed)
    except (TypeError, ValueError, KeyError):
        intact = False
    return route, intact, raw


def same_origin_file(url):
    try:
        parts = urlsplit(url)
    except (TypeError, ValueError):
        return None
    if parts.scheme not in ("", "https") or parts.hostname not in (None, "app.asana.com", "asana.com"):
        return None
    raw = unquote(parts.path)
    match = re.fullmatch(r"/files/([A-Za-z0-9_-]+)/([A-Za-z0-9_. -]+)", raw)
    if not match or match[2] in (".", ".."):
        return None
    root = VAR_DIR / "files" / "asana"
    path = root / match[1] / match[2]
    return path if path.resolve().is_relative_to(root.resolve()) and not path.is_symlink() else None


def attachment_check(before, after, task, raw):
    if raw is None:
        return False
    prev_task = keyed(before["tasks"], "taskId")[ASANA_TASK]
    previous_ids = set(prev_task.get("attachmentIds", []))
    actor = before["currentUser"]["userId"]
    active_ids = task.get("attachmentIds", [])
    all_previous = {row["attachmentId"] for row in before["attachments"]}
    for row in after["attachments"]:
        aid = row.get("attachmentId")
        if (not aid or aid in previous_ids or aid in all_previous or active_ids.count(aid) != 1
                or row.get("fileName") != OUTPUT or row.get("deletedAt") or row.get("status") == "removed"
                or row.get("taskId", ASANA_TASK) != ASANA_TASK):
            continue
        explicit_actor = row.get("uploaderId")
        if explicit_actor != actor or row.get("fileSize") != len(raw):
            continue
        uploaded = instant(row.get("uploadDate"))
        if not uploaded or uploaded <= instant(prev_task.get("createdDate")):
            continue
        stored = same_origin_file(row.get("fileUrl"))
        try:
            if stored and stored.is_file() and stored.stat().st_size == len(raw) and stored.read_bytes() == raw:
                return True
        except OSError:
            continue
    return False


def evaluate(grader):
    carrier_before, carrier_after = load_site("wayfair")
    asana_before, asana_after = load_site("asana")
    teams_before, teams_after = load_site("microsoft_teams")
    appointment, slot, driver = wayfair_checks(carrier_before, carrier_after)
    drawing, intact, blob = diagrams()
    date, notes, task = asana_checks(asana_before, asana_after)
    attached = attachment_check(asana_before, asana_after, task, blob)
    reply = teams_check(teams_before, teams_after)
    for ident, weight, passed, detail in (
        ("W1", 14, appointment, "Original long-sideboard booking and replacement chain"),
        ("W2", 10, slot, "Tuesday 12–4 Eastern slot"),
        ("W3", 8, driver, "Approved entrance, receiving and upright path"),
        ("D1", 19, drawing, "Editable directed southern route avoiding the courtyard"),
        ("D2", 8, intact, "Original surveyed floor plan retained"),
        ("A1", 10, date, "Original installation task due November 25"),
        ("A2", 9, notes, "Original installation notes and confirmed handoff"),
        ("A3", 14, attached, "Original task attachment matches submitted drawing bytes"),
        ("T1", 8, reply, "Original Teams thread reply and drawing pointer"),
    ):
        grader.add(ident, weight, bool(passed), detail)


if __name__ == "__main__":
    run(TASK, VERSION, evaluate)

