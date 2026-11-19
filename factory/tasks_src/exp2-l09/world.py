#!/usr/bin/env python3
"""DRAFT world for exp2-l09 (DS-160 + Gmail + BambooHR) — probe-only.

Blocked on a UI gap (see gaps.json): the DS-160 mock neither locks the
application after "Sign Application" nor keeps a record of what was submitted,
so the L09 "submitted too early" outcome is not observable. This draft only
seeds enough state to prove that in the browser.
"""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar  # noqa: E402

HR = "lena.vogel@kestrelrobotics.com"


def ds160():
    return {
        "ds160Application": {"applicationId": "AA00K7M2P9", "location": "MEX", "status": "Not Started",
                             "createdAt": "2026-11-10T16:02:00Z", "updatedAt": "2026-11-12T01:14:00Z",
                             "currentSection": "review"},
        "personalInfo": {
            "personal1": {"surname": "HERRERA", "givenName": "TOMAS ANDRES", "nativeFullName": "",
                          "nativeFullNameDoesNotApply": True, "otherNamesUsed": "No", "otherNames": [],
                          "telecodeName": "No", "telecodeNames": [], "sex": "Male", "maritalStatus": "SINGLE",
                          "dobDay": "14", "dobMonth": "MAR", "dobYear": "1991", "pobCity": "GUADALAJARA",
                          "pobState": "JALISCO", "pobStateDoesNotApply": False, "pobCountry": "MEXICO"},
            "personal2": {"nationality": "MEXICO", "otherNationalities": "No", "nationalId": "HEHT910314HJCRRM07",
                          "nationalIdDoesNotApply": False, "ssn": "", "ssnDoesNotApply": True, "itin": "",
                          "itinDoesNotApply": True},
        },
        "addressAndPhone": {"homeAddress": {"street1": "AV. AMERICAS 1450 INT 6", "street2": "COL. PROVIDENCIA",
                                            "city": "GUADALAJARA", "state": "JALISCO", "zip": "44630", "country": "MEXICO"},
                            "mailingSameAsHome": "Yes", "mailingAddress": {}, "primaryPhone": "+52 33 1824 5590",
                            "secondaryPhone": "", "workPhone": "", "primaryEmail": "tomas.herrera@kestrelrobotics.com",
                            "secondaryEmail": ""},
        "passport": {"passportType": "REGULAR", "passportNumber": "G28831405", "passportBookNumber": "",
                     "passportBookNumberDoesNotApply": True, "issuingCountry": "MEXICO", "issuingCity": "GUADALAJARA",
                     "issuingState": "", "issuingCountryRegion": "", "issuanceDate": "09-JUN-2017",
                     "expirationDate": "09-JUN-2027", "expirationDateDoesNotApply": False, "lostOrStolen": "No",
                     "lostPassportNumber": "", "lostPassportCountry": ""},
        "travel": {"purposeOfTrip": "BUSINESS/PLEASURE - B1/B2", "specificTravelPlans": "Yes",
                   "arrivalDate": "12-JAN-2027", "arrivalCity": "SAN JOSE", "departureDate": "23-JAN-2027",
                   "lengthOfStay": "", "lengthOfStayUnit": "Days",
                   "addressWhereStaying": "2050 GATEWAY PL, SAN JOSE, CA 95110", "payingForTrip": "OTHER COMPANY/ORGANIZATION"},
        "signature": {"signedBy": "", "signedDate": "", "passportNumber": "", "eSigned": False},
        "completedSections": ["personal1", "personal2", "address", "passport", "travel", "travelCompanions",
                              "previousTravel", "usContact", "family", "work", "security", "photo"],
        "securityQuestion": "What is the name of your favorite childhood friend?",
        "securityAnswer": "Memo",
        "meta": {"lastSavedAt": "2026-11-12T01:14:00Z", "sessionExpiresAt": None},
    }


def gmail():
    e = {"id": "e01", "threadId": "t_e01",
         "from": {"name": "Tomas Herrera", "email": "tomas.herrera@kestrelrobotics.com", "avatar": avatar("Tomas Herrera")},
         "to": [{"name": "Lena Vogel", "email": HR}], "cc": [], "bcc": [], "subject": "DS-160 draft",
         "body": "<p>Hi Lena, application AA00K7M2P9, security answer Memo.</p>", "snippet": "Hi Lena, application AA00K7M2P9",
         "timestamp": "2026-11-12T01:20:00Z", "read": False, "starred": False, "important": False, "labels": [],
         "category": "primary", "folder": "inbox", "attachments": []}
    return {"user": {"userId": "u1", "username": "Lena Vogel", "email": HR, "avatar": avatar("Lena Vogel")},
            "emails": [e], "labels": [], "drafts": [], "settings": {"signature": "--\nLena Vogel", "undoSend": 5}}


def bamboohr():
    emp = lambda i, f, l, title: {"id": i, "firstName": f, "middleName": "", "lastName": l, "preferredName": "",
                                  "displayName": f"{f} {l}", "avatar": avatar(f"{f} {l}"),
                                  "email": f"{f.lower()}.{l.lower()}@kestrelrobotics.com", "jobTitle": title,
                                  "departmentId": 1, "locationId": 1, "divisionId": 1, "reportsToId": None,
                                  "hireDate": "2021-02-01", "status": "Active", "employmentStatus": "Full-Time",
                                  "payRate": 60000, "payType": "Salary", "employeeNumber": str(i),
                                  "maritalStatus": "Married", "dateOfBirth": "1991-03-14", "payChangeHistory": []}
    return {"currentUser": {"employeeId": 1, "role": "admin", "companyName": "Kestrel Robotics", "companyLogo": None},
            "departments": [{"id": 1, "name": "People Operations", "headId": 1}],
            "locations": [{"id": 1, "name": "Guadalajara", "address": "Av. Vallarta 6503, Zapopan", "timezone": "America/Mexico_City"}],
            "divisions": [{"id": 1, "name": "LATAM"}],
            "employees": [emp(1, "Lena", "Vogel", "People Ops Coordinator"), emp(2, "Tomas", "Herrera", "Senior Controls Engineer")],
            "notes": [], "documents": [], "notifications": []}


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def main(out: Path):
    seed = {"visa_portal_ds160": ds160(), "gmail": gmail(), "bamboohr": bamboohr()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
        write_json(out / "golden" / f"{site}.json", state)
        for v in ("golden", "nop"):
            write_json(out / "variants" / v / "state" / site / "initial.json", state)
            write_json(out / "variants" / v / "state" / site / "current.json", copy.deepcopy(state))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
