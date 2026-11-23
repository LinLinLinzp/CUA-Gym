"""Preserve the first issued envelope packet when a stale draft is saved."""


PACKET_FIELDS = {
    "documents": ("id", "name", "fileSize", "sha256", "storedName", "downloadUrl"),
    "recipients": ("id", "name", "email", "role", "routingOrder"),
    "fields": ("id", "documentId", "recipientId", "type", "required", "x", "y"),
}
TERMINAL = {"voided", "completed", "declined", "expired"}


def _index(state):
    if not isinstance(state, dict) or not isinstance(state.get("envelopes"), list):
        raise ValueError("An envelope list is required")
    entries = {}
    for row in state["envelopes"]:
        ident = row.get("id") if isinstance(row, dict) else None
        if not isinstance(ident, str) or not ident or ident in entries:
            raise ValueError("Envelopes must have unique IDs")
        entries[ident] = row
    return entries


def _packet(envelope):
    packet = {key: envelope[key] for key in ("sentAt", "subject", "message")}
    for column, fields in PACKET_FIELDS.items():
        packet[column] = [{key: row[key] for key in fields if key in row} for row in envelope[column]]
    return packet


def _first_issue(proposed, old, user):
    try:
        if proposed["status"] != "sent" or not isinstance(proposed["sentAt"], str):
            return False
        packet = _packet(proposed)
        if not packet["documents"] or not any(rec["role"] == "signer" for rec in packet["recipients"]):
            return False
        history = proposed["history"]
        baseline = old["history"] if old else history[:1]
        if not baseline or history[:-1] != baseline or history[-1]["action"] != "sent":
            return False
        event = history[-1]
        return (proposed["sentSnapshot"] == packet == event["snapshot"]
                and proposed["sentAt"] == event["timestamp"]
                and event["actorName"] == user["name"] and event["actorEmail"] == user["email"])
    except (AttributeError, KeyError, TypeError, IndexError):
        return False


def _preserves_packet(before, after):
    old_history = before.get("history", [])
    new_history = after.get("history")
    if not isinstance(new_history, list) or new_history[:len(old_history)] != old_history:
        return False
    if any(after.get(key) != before.get(key) for key in ("sentSnapshot", "sentAt", "subject", "message", "documents")):
        return False
    if before.get("status") in TERMINAL:
        return (after.get("status") == before["status"] and new_history == old_history
                and all(after.get(key) == before.get(key) for key in
                        ("voidReason", "voidedAt", "recipients", "fields")))
    if after.get("status") == "draft":
        return False
    appended = new_history[len(old_history):]
    if any(not isinstance(event, dict) or event.get("action") == "sent" for event in appended):
        return False
    if after.get("status") == "voided":
        reason = after.get("voidReason")
        return (isinstance(reason, str) and bool(reason.strip()) and bool(appended)
                and appended[-1].get("action") == "voided"
                and appended[-1].get("timestamp") == after.get("voidedAt"))
    return True


def preserve_issued_history(current, proposed, action):
    """Apply this policy under the sitehost lock only for the opted-in site."""
    if action not in {"set", "set_current"}:
        raise ValueError("Issued envelope history cannot be reset")
    before, after = _index(current), _index(proposed)
    saved = []
    for ident, incoming in after.items():
        old = before.get(ident)
        if old and (old.get("sentSnapshot") or old.get("sentAt")):
            saved.append(incoming if _preserves_packet(old, incoming) else old)
        elif incoming.get("sentSnapshot") or incoming.get("sentAt") or incoming.get("status") != "draft":
            if not _first_issue(incoming, old, current.get("user", {})):
                raise ValueError("First-send packet does not match the issued envelope")
            saved.append(incoming)
        else:
            saved.append(incoming)
    saved.extend(old for ident, old in before.items()
                 if ident not in after and (old.get("sentSnapshot") or old.get("sentAt")))
    return {**proposed, "envelopes": saved}
