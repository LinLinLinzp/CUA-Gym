"""Transition the signed-review DS-160 profile under the sitehost write lock."""

import re
import secrets
import unicodedata
from copy import deepcopy


SNAPSHOT_SECTIONS = (
    "personalInfo", "addressAndPhone", "passport", "travel", "travelCompanions",
    "previousUSTravel", "usContact", "family", "workEducation", "security", "photo", "signature",
)
REQUIRED_SECTIONS = {
    "personal1", "personal2", "address", "passport", "travel", "travelCompanions",
    "previousTravel", "usContact", "family", "work", "security", "photo", "review",
}


def words(value):
    ascii_value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[A-Z0-9]+", ascii_value.upper()))


def draft_application(state):
    if not isinstance(state, dict) or not isinstance(state.get("ds160Application"), dict):
        raise ValueError("Missing application draft")
    application = state["ds160Application"]
    if application.get("status") == "Submitted" or state.get("submission") or state.get("submissionHistory"):
        raise ValueError("Sign the application to request a confirmation")
    return application


def apply_ds160_write(current, action, proposal, submitted_at):
    """Reject direct receipt writes and retain the first accepted snapshot."""
    if action not in {"set", "set_current", "ds160_submit"}:
        raise ValueError("This application cannot be reset or overwritten")
    application = current.get("ds160Application") or {}
    if application.get("status") == "Submitted" or current.get("submission"):
        return current
    if action != "ds160_submit":
        draft_application(proposal)
        return proposal

    if not application.get("applicationId") or not application.get("location"):
        raise ValueError("Retrieve the application before signing")
    draft = current if proposal is None else proposal
    reviewed = draft_application(draft)
    if any(reviewed.get(key) != application[key] for key in ("applicationId", "location")):
        raise ValueError("The reviewed application does not match the saved application")
    if not REQUIRED_SECTIONS.issubset(draft.get("completedSections") or []):
        raise ValueError("Complete the required sections and review before signing")
    if any(not isinstance(draft.get(section), dict) for section in SNAPSHOT_SECTIONS):
        raise ValueError("Required application data is missing")

    signature = draft["signature"]
    personal = draft["personalInfo"].get("personal1") or {}
    given, surname = words(personal.get("givenName")), words(personal.get("surname"))
    passport = words(draft["passport"].get("passportNumber"))
    if not given or not surname or words(signature.get("signedBy")) not in {f"{given} {surname}", f"{surname} {given}"}:
        raise ValueError("Enter the applicant's full name as it appears in the application")
    if not passport or words(signature.get("passportNumber")) != passport:
        raise ValueError("The signing passport number must match the reviewed application")
    if signature.get("eSigned") is not True:
        raise ValueError("Certify the application before signing")

    locked = deepcopy(draft)
    locked["signature"]["signedDate"] = submitted_at
    locked["ds160Application"].update(status="Submitted", currentSection="confirmation", updatedAt=submitted_at)
    receipt = {
        "applicationId": application["applicationId"],
        "location": application["location"],
        "submittedAt": submitted_at,
        "confirmationNumber": f"DS-{secrets.token_hex(4).upper()}",
        "data": {section: deepcopy(locked[section]) for section in SNAPSHOT_SECTIONS},
    }
    locked["submission"] = receipt
    locked["submissionHistory"] = [deepcopy(receipt)]
    if "sign" not in locked["completedSections"]:
        locked["completedSections"].append("sign")
    return locked
