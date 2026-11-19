#!/usr/bin/env python3
"""Verifier for damage-claims-backlog. Checkpoints mirror rubric.json (S*, K*, G*, C*)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cuaverify import (InfraError, load_site, mentions, mentions_amount, money_eq, new_items,  # noqa: E402
                       plain, read_csv, run)

TASK_ID, VERSION = "cua-hard/damage-claims-backlog", "0.1.0"
EXPECTED = json.loads((Path(__file__).parent / "expected.json").read_text())
CLAIMS = {int(k): v for k, v in EXPECTED["claims"].items()}
CLAIM_ORDERS = set(EXPECTED["claim_orders"])  # includes #1047, the order Grace cited by mistake
TAGGED = set(EXPECTED["tagged"])


def refunds_added(initial_order, current_order):
    """Aggregate refunds issued during the run: ({sku: qty}, shipping, total)."""
    added = new_items(initial_order.get("refunds"), current_order.get("refunds"))
    lines, shipping, total = {}, 0.0, 0.0
    for refund in added:
        for line in refund.get("lineItems") or []:
            if line.get("quantity"):
                lines[line.get("sku")] = lines.get(line.get("sku"), 0) + int(line["quantity"])
        shipping += float(refund.get("shipping") or 0)
        total += float(refund.get("total") or 0)
    return lines, shipping, total, len(added)


def evaluate(g):
    shop0, shop1 = load_site("shopify")
    slack0, slack1 = load_site("slack")
    mail0, mail1 = load_site("gmail")
    before = {o["orderNumber"]: o for o in shop0["orders"]}
    after = {o["orderNumber"]: o for o in shop1.get("orders", [])}
    if set(before) - set(after):
        # Orders can't be deleted in the UI; a missing order means corrupted state.
        raise InfraError(f"orders missing from final state: {sorted(set(before) - set(after))}")

    # ---- Shopify: refunds -------------------------------------------------
    for check_id, number in (("S1.refund_1042", 1042), ("S2.refund_1051", 1051),
                             ("S3.refund_1044", 1044), ("S4.refund_1053", 1053)):
        claim = CLAIMS[number]
        lines, shipping, total, _ = refunds_added(before[number], after[number])
        ok = lines == claim["lines"] and money_eq(shipping, claim["shipping"]) and money_eq(total, claim["amount"])
        g.add(check_id, 8, ok, f"refunded {lines} shipping={shipping:.2f} total={total:.2f}; expected {claim['lines']} +{claim['shipping']}")

    refunded_right = sum(c["score"] == 1.0 for c in g.checks)

    # ---- Slack: approvals ---------------------------------------------------
    posts = new_items(slack0["messages"].get("refund-approvals"), slack1.get("messages", {}).get("refund-approvals"), key="messageId")
    texts = [p.get("content", "") for p in posts]
    approval = [t for t in texts if "1038" in plain(t)]
    k1 = 1.0 if any(mentions_amount(t, CLAIMS[1038]["approval_amount"]) for t in approval) else 0.5 if approval else 0.0
    g.add("K1.approval_post_1038", 7, k1, f"{len(approval)} approval post(s) for #1038")
    others = sorted({n for t in texts for n in CLAIM_ORDERS - {1038} if str(n) in plain(t)})
    # Restraint only earns credit once real work was done, so an empty run scores 0.
    g.add("K2.no_needless_approvals", 4, refunded_right > 0 and not others,
          f"approval posts for orders {others}; correct refunds so far: {refunded_right}")

    # ---- Gmail: replies -----------------------------------------------------
    sent = [e for e in new_items(mail0["emails"], mail1.get("emails")) if e.get("folder") == "sent"]

    def replies_to(address):
        return [e.get("subject", "") + " " + e.get("body", "") for e in sent
                if address in {(r.get("email") or "").lower() for r in e.get("to") or []}]

    def reply_check(check_id, weight, number, predicate, describe):
        bodies = replies_to(CLAIMS[number]["from"])
        good = any(predicate(b) for b in bodies)
        g.add(check_id, weight, 1.0 if good else 0.25 if bodies else 0.0,
              f"{len(bodies)} reply(ies) to {CLAIMS[number]['from']}; needs {describe}")
        return bool(bodies)

    reply_check("G1.reply_emma", 4, 1042, lambda b: mentions_amount(b, "54.00"), "refund $54.00")
    reply_check("G2.reply_liam_home", 4, 1051, lambda b: mentions_amount(b, "153.95"), "refund $153.95 to the address he wrote from")
    reply_check("G3.reply_sofia", 3, 1044, lambda b: mentions_amount(b, "178.00"), "refund $178.00")
    reply_check("G4.reply_grace", 3, 1053, lambda b: mentions_amount(b, "32.00") and ("1053" in plain(b) or "napkin" in plain(b)),
                "napkin refund $32.00")
    reply_check("G5.reply_priya", 3, 1038,
                lambda b: any(w in plain(b) for w in ("approv", "review", "manager", "escalat", "pending")),
                "says the refund is going through approval")
    replied_tom = reply_check("G6.reply_tom", 4, 1029, lambda b: mentions(b, "sorry15"), "the SORRY15 code")
    replied_noah = reply_check("G7.reply_noah", 3, 1035,
                lambda b: mentions_amount(b, "56.95") or any(d in plain(b) for d in ("march 10", "mar 10", "3/10", "mar. 10")),
                "the earlier refund ($56.95 / Mar 10)")


    # ---- Shopify: claims that must NOT be refunded, tags, protection ---------
    # Each "no refund" only counts when the claim was actually handled another way.
    for check_id, number, handled, why in (("S5.no_refund_1038", 1038, bool(approval), "sent for approval instead"),
                                           ("S6.no_refund_1029", 1029, replied_tom, "late claim, answered with code"),
                                           ("S7.no_double_refund_1035", 1035, replied_noah, "already refunded on Mar 10")):
        _, _, total, count = refunds_added(before[number], after[number])
        g.add(check_id, 5, handled and count == 0, f"{count} new refund(s) totalling {total:.2f}; handled={handled} ({why})")

    newly_tagged = {n for n in after if "damage-claim" in (after[n].get("tags") or []) and "damage-claim" not in (before[n].get("tags") or [])}
    g.add("S8.damage_claim_tags", 6, (len(newly_tagged & TAGGED) - len(newly_tagged - TAGGED)) / len(TAGGED),
          f"newly tagged {sorted(newly_tagged)}; expected {sorted(TAGGED)}")

    touched = []
    for number, order in before.items():
        if number in CLAIMS:
            continue
        now = after[number]
        if (refunds_added(order, now)[3] or now.get("financialStatus") != order.get("financialStatus")
                or sorted(now.get("tags") or []) != sorted(order.get("tags") or [])):
            touched.append(number)
    g.add("S9.other_orders_untouched", 4, refunded_right > 0 and not touched,
          f"modified non-claim orders: {touched}; correct refunds so far: {refunded_right}")

    # ---- CLI deliverable ----------------------------------------------------
    rows = read_csv("claims_log.csv")
    if rows is None:
        g.add("C1.claims_log", 8, 0, "claims_log.csv missing")
    else:
        correct = 0
        for number, claim in CLAIMS.items():
            match = [r for r in rows if r.get("order", "").lstrip("#").strip() == str(number)]
            if (len(match) == 1 and match[0].get("decision", "").lower() == claim["decision"]
                    and match[0].get("customer_email", "").lower() == claim["from"]
                    and money_eq(match[0].get("refund_amount"), claim["amount"])):
                correct += 1
        g.add("C1.claims_log", 8, correct / max(len(CLAIMS), len(rows)), f"{correct}/{len(CLAIMS)} rows right, {len(rows)} rows total")


if __name__ == "__main__":
    run(TASK_ID, VERSION, evaluate)
