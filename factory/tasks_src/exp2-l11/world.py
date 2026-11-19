#!/usr/bin/env python3
"""World for the psyc3150-late-work-grading task (Canvas LMS + Gmail + Google Sheets + local CSV).

Writes into <out>/:
  seed/{canvas_lms,gmail,google_sheets}.json     initial state per site
  seed/files/canvas_lms/<policy pdf>             10-page course policy PDF (linked from the syllabus)
  golden/{canvas_lms,gmail,google_sheets}.json   state after a correct run
  golden_output/grade_entries.csv                correct CLI deliverable
  input/submissions_export.csv                   Canvas submission export (UTC timestamps)
  expected.json                                  truth for the verifier
  variants/<name>/{state/<site>/{initial,current}.json,output/grade_entries.csv}

Story: Jordan Ellis is a TA for PSYC 3150 at Lakeshore State University. Lab Report 3
and the Lab Report 2 resubmissions still have to be posted. The rubric scores are in
the TA tracker; what decides the posted score is the long course-policy PDF (lever L11):
15-minute grace, latest-attempt timestamps, TA "extensions" being void, the 48-hour
flexible-deadline accommodation counted from the end of its window and never
retroactive, Dean-verified absences waiving penalties, the 5-day cut-off, and the
resubmission 85% cap / one-per-term / higher-of rules. Gmail holds the approvals,
letters and notices (including a "wrong Aisha" correction); the export is in UTC.
"""

import copy
import csv
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worldkit import avatar, file_url, long_pdf  # noqa: E402

CLOCK = "2026-11-18T09:30:00-06:00"
NOW_Z = "2026-11-18T15:30:00.000Z"          # when the golden run "types" grades
GRADED_AT = "2026-11-18T16:05:00.000Z"
POLICY_PDF = "PSYC3150_Course_Policies_Fall2026.pdf"
DOMAIN = "lakeshore.edu"
JORDAN_EMAIL = f"jellis@{DOMAIN}"
KEVIN_EMAIL = f"ktran@{DOMAIN}"
PROF_EMAIL = f"hokafor@{DOMAIN}"

UTC = timezone.utc


def z(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------------------------------------------------------------- people
# key: (user_id, first, last, sis, section)
STUDENTS = [
    ("bello", 101, "Aisha", "Bello", "LS2210417", 1),
    ("alvarez", 102, "Diego", "Alvarez", "LS2210388", 1),
    ("fischer", 103, "Ben", "Fischer", "LS2211052", 1),
    ("cho", 104, "Hannah", "Cho", "LS2210921", 1),
    ("lee", 105, "Marcus", "Lee", "LS2211376", 1),
    ("okonkwo", 106, "Grace", "Okonkwo", "LS2210644", 1),
    ("novak", 107, "Liam", "Novak", "LS2211190", 1),
    ("park", 108, "Owen", "Park", "LS2210735", 1),
    ("moore", 109, "Ethan", "Moore", "LS2211423", 1),
    ("vogel", 110, "Lena", "Vogel", "LS2210862", 1),
    ("martin", 111, "Chloe", "Martin", "LS2211008", 1),
    ("turner", 112, "Isaac", "Turner", "LS2210579", 1),
    ("rahman", 113, "Aisha", "Rahman", "LS2211287", 2),
    ("herrera", 114, "Tomás", "Herrera", "LS2210493", 2),
    ("brandt", 115, "Sofia", "Brandt", "LS2211134", 2),
    ("haddad", 116, "Samir", "Haddad", "LS2210716", 2),
    ("petrova", 117, "Nadia", "Petrova", "LS2211341", 2),
    ("shah", 118, "Priya", "Shah", "LS2210958", 2),
    ("santos", 119, "Julia", "Santos", "LS2211065", 2),
    ("mensah", 120, "Kofi", "Mensah", "LS2210602", 2),
    ("doyle", 121, "Ryan", "Doyle", "LS2211219", 2),
    ("zhao", 122, "Emily", "Zhao", "LS2210827", 2),
    ("wright", 123, "Jacob", "Wright", "LS2211398", 2),
    ("lindgren", 124, "Maya", "Lindgren", "LS2210541", 2),
]
S = {s[0]: s for s in STUDENTS}


def full(key):
    return f"{S[key][2]} {S[key][3]}"


def semail(key):
    return f"{S[key][2].lower().replace('á', 'a')}.{S[key][3].lower()}@students.{DOMAIN}"


KEVIN_DONE = ["shah", "santos", "mensah", "doyle", "zhao", "wright", "lindgren"]

# ---------------------------------------------------------------- Lab 3 facts
LAB3_DUE = "2026-11-07T05:59:00Z"            # Fri Nov 6, 11:59 pm CST
LAB2_DUE = "2026-10-17T04:59:00Z"            # Fri Oct 16, 11:59 pm CDT
LAB2_RELEASED = "2026-10-30T21:10:00Z"       # announcement Fri Oct 30, 4:10 pm CDT
RESUB_CLOSE = "2026-11-07T05:59:00Z"         # 7th calendar day, 11:59 pm Central

# rubric score, [attempt timestamps UTC]
LAB3 = {
    "bello": (44, ["2026-11-08T16:05:00Z"]),
    "alvarez": (42, ["2026-11-06T21:10:00Z", "2026-11-07T19:20:00Z"]),
    "fischer": (39, ["2026-11-08T22:00:00Z"]),
    "cho": (45, ["2026-11-08T14:30:00Z"]),
    "lee": (41, ["2026-11-07T06:09:00Z"]),
    "okonkwo": (48, ["2026-11-08T23:30:00Z"]),
    "novak": (43, ["2026-11-09T20:00:00Z"]),
    "park": (37, ["2026-11-10T17:00:00Z"]),
    "moore": (41, ["2026-11-13T15:00:00Z"]),
    "vogel": (45, ["2026-11-07T04:48:00Z"]),
    "martin": (38, ["2026-11-06T18:00:00Z"]),
    "turner": (33, ["2026-11-06T15:45:00Z"]),
    "rahman": (47, ["2026-11-10T02:40:00Z"]),
    "herrera": (46, ["2026-11-09T03:15:00Z"]),
    "brandt": (40, ["2026-11-08T03:00:00Z"]),
    "haddad": (49, ["2026-11-05T23:12:00Z"]),
    "petrova": (36, ["2026-11-06T22:30:00Z"]),
    "shah": (42, ["2026-11-06T04:20:00Z"]),
    "santos": (46, ["2026-11-05T19:40:00Z"]),
    "mensah": (35, ["2026-11-07T02:55:00Z"]),
    "doyle": (40, ["2026-11-06T23:58:00Z"]),
    "zhao": (44, ["2026-11-04T21:15:00Z"]),
    "wright": (39, ["2026-11-07T05:31:00Z"]),
    "lindgren": (47, ["2026-11-06T16:02:00Z"]),
}

# Exceptions as the policy PDF + inbox establish them.
INSTRUCTOR_EXTENSIONS = {"herrera": "2026-11-09T05:59:00Z", "rahman": "2026-11-10T05:59:00Z"}
SAS_LETTERS = {"okonkwo": "2026-09-14", "novak": "2026-09-21", "brandt": "2026-11-10"}
DEAN_VERIFIED = {"park": ("2026-11-04", "2026-11-08")}

# Lab 2 resubmissions: original, resubmission rubric score, attempt-2 timestamp
LAB2_RESUB = {
    "cho": (31, 46, "2026-11-04T20:00:00Z"),
    "lee": (38, 41, "2026-11-05T03:30:00Z"),
    "shah": (29, 44, "2026-11-03T17:00:00Z"),
    "santos": (44, 48, "2026-11-06T02:00:00Z"),
    "mensah": (33, 40, "2026-11-09T15:00:00Z"),
    "doyle": (35, 39, "2026-11-06T23:10:00Z"),
}
RESUB_USED_LAB1 = [("shah", "2026-10-09", "KT"), ("wright", "2026-10-08", "JE"), ("zhao", "2026-10-10", "KT")]
POINTS = 50


def late_days(submitted: str, deadline: str) -> int:
    """Policy 7.2 + 14.3: 15-minute grace; beyond it every started 24 h from the deadline is a day."""
    delta = (z(submitted) - z(deadline)).total_seconds()
    if delta <= 15 * 60:
        return 0
    return math.ceil(delta / 86400)


def lab3_truth(key, *, ignore=()):
    """(days_late, final). `ignore` lists policy provisions a careless run would miss."""
    rubric, attempts = LAB3[key]
    submitted = attempts[0] if "latest_attempt" in ignore else attempts[-1]
    deadline = LAB3_DUE
    if key in INSTRUCTOR_EXTENSIONS:
        deadline = INSTRUCTOR_EXTENSIONS[key]
    if key in SAS_LETTERS:
        letter = SAS_LETTERS[key]
        applies = letter < LAB3_DUE[:10] or "retroactive" in ignore
        if applies:
            if "acc_window" in ignore:
                return 0, rubric                     # treats the letter as a blanket waiver
            deadline = (z(deadline) + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if "grace" in ignore:
        delta = (z(submitted) - z(deadline)).total_seconds()
        days = 0 if delta <= 0 else math.ceil(delta / 86400)
    else:
        days = late_days(submitted, deadline)
    if key in DEAN_VERIFIED and "medical" not in ignore:
        start, end = DEAN_VERIFIED[key]
        due_local = (z(LAB3_DUE) - timedelta(hours=6)).date().isoformat()
        within = start <= due_local <= end
        in_time = z(submitted) <= z(end + "T23:59:59Z") + timedelta(days=7, hours=6)
        if within and in_time:
            return 0, rubric
    if days > 5 and "cutoff" not in ignore:
        return days, 0
    return days, max(0, rubric - days * POINTS * 0.10)


def lab2_truth(key, *, ignore=()):
    original, resub, ts = LAB2_RESUB[key]
    if z(ts) > z(RESUB_CLOSE) and "window" not in ignore:
        return original
    if key in [k for k, _, _ in RESUB_USED_LAB1] and "term_cap" not in ignore:
        return original
    capped = resub if "cap85" in ignore else min(resub, POINTS * 0.85)
    if "higher_of" in ignore:
        return capped
    return max(original, capped)


# Hand-checked expectations (asserted against the rule engine above).
EXPECT_LAB3 = {
    "bello": (2, 34), "alvarez": (1, 37), "fischer": (2, 29), "cho": (2, 35), "lee": (0, 41),
    "okonkwo": (0, 48), "novak": (1, 38), "park": (0, 37), "moore": (7, 0), "vogel": (0, 45),
    "martin": (0, 38), "turner": (0, 33), "rahman": (0, 47), "herrera": (0, 46), "brandt": (1, 35),
    "haddad": (0, 49), "petrova": (0, 36),
}
EXPECT_LAB2 = {"cho": 42.5, "lee": 41, "shah": 29, "santos": 44, "mensah": 33, "doyle": 39}
TODO_LAB3 = [k for k in S if k not in KEVIN_DONE]


def num(x) -> str:
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:g}"


# ---------------------------------------------------------------- policy PDF
def policy_sections():
    return [
        ("Section 1. Course Overview", [
            "PSYC 3150, Research Methods in Psychology, introduces the logic and practice of empirical research in "
            "psychology. Students learn how psychologists turn questions into testable hypotheses, how they choose "
            "between observational, correlational, quasi-experimental and experimental designs, and how they collect, "
            "analyze and report data in a way that other researchers can evaluate and reproduce.",
            "The course combines two weekly lectures with a weekly lab section. Lectures introduce concepts; lab "
            "sections are where students practice them with real data sets, design their own small studies and write "
            "them up. The four lab reports are the backbone of the course and are where most of the writing and "
            "analysis skills are assessed.",
            "This document is the complete statement of course policies for Fall 2026. The syllabus page in Canvas "
            "gives a short summary for convenience; where the two differ, this document governs. Students are "
            "responsible for reading all of it, including the sections on extensions, resubmissions, accommodations, "
            "absences and the definitions in Section 14, which qualify the general rules stated earlier.",
        ]),
        ("Section 2. Learning Outcomes", [
            "By the end of the course students will be able to: (a) evaluate the internal and external validity of a "
            "research design; (b) identify confounds and propose controls for them; (c) choose and justify an "
            "appropriate sampling strategy; (d) write measurable operational definitions for psychological "
            "constructs; (e) run and interpret descriptive statistics, t tests, one-way ANOVA and simple regression in "
            "jamovi; (f) report results in APA (7th edition) style; and (g) recognize the ethical obligations that "
            "researchers have to participants, including informed consent, debriefing and the protection of "
            "confidential data.",
            "These outcomes map onto the department's undergraduate program goals 2 (scientific inquiry and critical "
            "thinking) and 4 (communication). Lab reports are scored with rubrics that name the outcomes they assess, "
            "so that feedback on each report can be traced back to the skills it is meant to build.",
        ]),
        ("Section 3. Instructional Team and Communication", [
            "Instructor: Dr. Helen Okafor (hokafor@lakeshore.edu), Clark Hall 214. Office hours Tuesday 1:00-3:00 p.m. "
            "and by appointment. Teaching assistants: Jordan Ellis (jellis@lakeshore.edu), lab section 01, Wednesday "
            "2:00-3:50 p.m.; Kevin Tran (ktran@lakeshore.edu), lab section 02, Thursday 10:00-11:50 a.m. TA office "
            "hours are posted on the Canvas calendar each week.",
            "Teaching assistants lead the lab sections, grade the lab reports of the students in their section using "
            "the published rubric, and record scores in Canvas. Questions about the content of feedback should go to "
            "the TA who graded the report first. Requests that involve a deadline, an exception or a change of grade "
            "go to the instructor, as described in Sections 9, 10 and 15.",
            "Please use your Lakeshore email account for course correspondence and include PSYC 3150 and your lab "
            "section in the subject line. The teaching team answers email within two business days; messages sent "
            "late at night or over the weekend may not be answered before a deadline, so plan ahead.",
        ]),
        ("Section 4. Materials and Technology", [
            "Required text: Morling, B. Research Methods in Psychology: Evaluating a World of Information (4th ed.). "
            "Additional readings are posted as PDFs in the Canvas Files area. All analyses use jamovi, which is free "
            "and installed in the Clark Hall computer lab. Students are expected to bring a laptop to lab sections; "
            "loaner laptops are available from the library on a first-come basis.",
            "Lab reports are submitted through Canvas as a single PDF. Students should keep the confirmation that "
            "Canvas shows after each submission. Problems with Canvas itself are handled under Section 14.4; problems "
            "with a personal device, a home internet connection or a cloud storage service are not grounds for an "
            "exception, and students are encouraged to submit a draft early and replace it later if needed.",
        ]),
        ("Section 5. Course Components and Grading", [
            "Final grades are computed from the following weighted components: lab reports 40% (four reports, 50 "
            "points each); online quizzes 15% (four quizzes, 20 points each); midterm exam 20%; final research paper "
            "25%. Participation in lab sections is required for credit on the corresponding lab report but is not "
            "graded separately.",
            "Letter grades follow the department scale: A 93 and above, A- 90-92.99, B+ 87-89.99, B 83-86.99, B- 80-82.99, "
            "C+ 77-79.99, C 73-76.99, C- 70-72.99, D+ 67-69.99, D 60-66.99, F below 60. Final percentages are not "
            "rounded up. Canvas displays a running total during the term; the running total is informational and "
            "excludes work that has not been graded yet.",
            "Grades for each assignment are released together for the whole class once all reports have been "
            "scored. The instructor announces each release in Canvas; the date of that announcement is the release "
            "date referred to elsewhere in this document.",
        ]),
        ("Section 6. Lab Reports", [
            "Each lab report follows the structure of an empirical journal article: title page, abstract, "
            "introduction, method, results, discussion and references, with tables and figures formatted in APA "
            "style. Reports are written individually even when the data were collected in groups. The assignment "
            "page for each report in Canvas lists the specific data set, the required analyses and the rubric.",
            "Lab Report 1 (observational coding) is due Friday, September 25; Lab Report 2 (experimental design) is "
            "due Friday, October 16; Lab Report 3 (survey methods and scale reliability) is due Friday, November 6; "
            "Lab Report 4 (factorial designs) is due Friday, December 4. All lab report deadlines are 11:59 p.m. "
            "Central Time on the due date.",
            "Rubric scores are assigned out of 50 points. TAs aim to return lab reports within ten days of the "
            "deadline. Rubric criteria are weighted as follows: research question and hypotheses 8 points, method "
            "10, analysis 12, results reporting 10, discussion 6, APA style and mechanics 4.",
        ]),
        ("Section 7. Late Work", [
            "7.1 Deadlines. Every assignment in this course has a published deadline in Canvas. Work is on time if "
            "it is submitted by its deadline, subject to the definitions in Section 14.",
            "7.2 Late penalty for lab reports. A lab report submitted after its deadline loses 10% of the points "
            "possible for that report for each day it is late. Each 24-hour period after the deadline, or any part "
            "of one, counts as one day. For a 50-point lab report the penalty is therefore 5 points per day. The "
            "penalty is subtracted from the rubric score and a score never goes below zero.",
            "7.3 Cut-off. Lab reports submitted more than five days late, that is, more than 120 hours after the "
            "deadline, are not accepted. They receive a score of 0 regardless of quality, although the TA may still "
            "return written feedback.",
            "7.4 Quizzes and exams. Online quizzes close at their deadline and cannot be taken late. The midterm "
            "exam is taken in class; make-up exams are arranged only under Section 12.",
            "7.5 Scope. The rules in this section are the default. Sections 9 (extensions), 10 (resubmissions), 11 "
            "(accommodations) and 12 (absences and emergencies) state when and how the default is modified, and "
            "Section 14 defines how submission times are determined.",
        ]),
        ("Section 8. Attendance and Participation", [
            "Attendance at lectures is expected but not recorded. Attendance at lab sections is recorded by the TA. "
            "A student who misses a lab section without an excused absence must complete the make-up exercise posted "
            "in Canvas before submitting the corresponding lab report, otherwise the report is not graded.",
            "Students are expected to come to lab having completed the assigned reading and the pre-lab worksheet. "
            "Lab time is collaborative: you will often collect data in small groups, and you are expected to share "
            "the workload fairly and treat your classmates' contributions with respect.",
            "If you must miss a lab section, tell your TA in advance when possible. Excused absences are those "
            "covered by Section 12, university-sanctioned activities documented in advance, and religious "
            "observances notified within the first two weeks of the term.",
        ]),
        ("Section 9. Extensions", [
            "9.1 How to request. A student who needs more time for a lab report must email the instructor, not a "
            "TA, at least 24 hours before the deadline, explaining the reason and proposing a new date. Requests "
            "made less than 24 hours before the deadline are considered only under Section 12.",
            "9.2 Effect of an approved extension. An extension exists only when the instructor approves it in "
            "writing. The approved date and time become the student's deadline for that assignment. If the work is "
            "submitted after the extended deadline, the late penalty in Section 7.2 and the cut-off in Section 7.3 "
            "are counted from the extended deadline, not from the original one.",
            "9.3 Who may grant extensions. Only the instructor may grant, promise or modify an extension. Teaching "
            "assistants are not authorized to do so. A statement by a teaching assistant that a student may have "
            "more time, however it is worded, is not an extension, and the original deadline continues to apply "
            "unless the instructor confirms an extension in writing.",
            "9.4 Retroactive requests. Requests made after a deadline has passed are not considered, except where "
            "Section 12 applies.",
            "9.5 Group work. Extensions are personal. When data were collected in a group, an extension for one "
            "member does not change the deadline for the others.",
        ]),
        ("Section 10. Revision and Resubmission of Lab Reports", [
            "10.1 Purpose. Writing improves with revision, so the course allows students to revise and resubmit a "
            "graded lab report after reading the feedback. Resubmissions are graded with the same rubric as the "
            "original by the TA of the student's section.",
            "10.2 Window. A resubmission must be uploaded to the same Canvas assignment within seven calendar days "
            "after grades for that assignment are released (Section 5), and no later than 11:59 p.m. Central Time on "
            "the seventh day. Resubmissions uploaded after the window closes are not graded and the original score "
            "stands.",
            "10.3 Cap. A resubmission is graded on its merits, but the score recorded for a resubmission may not "
            "exceed 85% of the points possible for that report. For a 50-point lab report the highest score a "
            "resubmission can earn is 42.5.",
            "10.4 Limit. Each student may use the resubmission option for one lab report per term. The option "
            "counts as used once a resubmission has been graded. Any further resubmission in the same term is not "
            "graded, even if it is uploaded within the window, and the original score for that report stands.",
            "10.5 Recorded score. After a resubmission is graded, the score recorded in Canvas is the higher of the "
            "original score and the resubmission score as capped under Section 10.3. A resubmission can therefore "
            "never lower a student's grade.",
            "10.6 Exclusions. Quizzes, the midterm exam and the final research paper cannot be resubmitted. Lab "
            "Report 4 cannot be resubmitted because its feedback is returned after the last day of classes.",
        ]),
        ("Section 11. Accessibility and Accommodations", [
            "11.1 Process. Students with disabilities who need accommodations should register with Student "
            "Accessibility Services (SAS). SAS sends the instructor an accommodation letter that lists the approved "
            "accommodations. The teaching team does not ask for, and students do not have to disclose, any medical "
            "or diagnostic information.",
            "11.2 Flexible deadlines. When an SAS letter lists flexible deadlines, each lab report deadline for that "
            "student is extended by 48 hours. The student does not need to request this for each report and does "
            "not need to notify the teaching team before using it.",
            "11.3 Work submitted after the flexible window. If a student with a flexible-deadline accommodation "
            "submits a lab report after the end of the 48-hour window, the late penalty in Section 7.2 and the "
            "cut-off in Section 7.3 apply, counted from the end of the 48-hour window.",
            "11.4 Effective date. Accommodations take effect on the date shown on the SAS letter and apply only to "
            "deadlines that fall after that date. They are not applied retroactively to work that was due before "
            "the letter was issued, including work that was submitted late before the letter was issued.",
            "11.5 Quizzes and exams. Extended time on quizzes and exams is administered by the SAS testing center "
            "and is not affected by the flexible-deadline provision, which applies to lab reports only.",
            "11.6 Confidentiality. Accommodation letters are shared only with the instructional team for this "
            "course and are kept confidential.",
        ]),
        ("Section 12. Illness, Emergencies and Absences", [
            "12.1 Short illness. Minor illnesses and routine appointments are handled through the normal late "
            "policy, which is designed to absorb a day or two of disruption without any paperwork.",
            "12.2 Verified absences. When the Dean of Students Office notifies the instructor that it has verified a "
            "student's absence for a medical or family emergency, the late penalties in Section 7 are waived for "
            "any lab report whose deadline falls within the verified absence period, provided the report is "
            "submitted no later than seven calendar days after the last day of that period. The Dean of Students "
            "notice is sufficient; students do not need to request the waiver separately.",
            "12.3 Missed exams. A student whose verified absence covers the midterm exam takes a make-up exam "
            "scheduled with the instructor within two weeks of returning.",
            "12.4 Longer absences. If an absence is long enough to make completing the course unrealistic, the "
            "instructor will discuss an incomplete or a late withdrawal with the student and their academic "
            "advisor.",
        ]),
        ("Section 13. Academic Integrity", [
            "All work submitted in this course must be your own. You may discuss study design and analysis with "
            "classmates during lab, but the text, tables and figures of each lab report must be written by you. "
            "Copying another student's report, reusing a report from a previous term, or submitting text produced "
            "by a generative AI tool as your own writing is a violation of the Lakeshore State Code of Academic "
            "Integrity.",
            "You may use reference managers, spell checkers and grammar tools. If you use a generative AI tool for "
            "any other purpose, for example to brainstorm or to check code, describe how you used it in a short "
            "note at the end of the report. Undisclosed use is treated as a violation.",
            "Suspected violations are reported to the Office of Student Conduct as the Code requires. The teaching "
            "team does not resolve integrity cases informally. Fabricating data, including inventing participants "
            "or altering values in a data set, is among the most serious violations in research and is always "
            "reported.",
        ]),
        ("Section 14. Definitions and Technical Matters", [
            "14.1 Central Time. All deadlines in this course are stated in U.S. Central Time (America/Chicago), "
            "whether daylight or standard time is in effect on the date in question.",
            "14.2 Submission time. The submission time of a lab report is the timestamp Canvas records for the "
            "attempt that is graded. When a student uploads more than one attempt before grading, the most recent "
            "attempt is the one graded, and its timestamp is the submission time used for every rule in this "
            "document. An earlier attempt does not count once a later one has been uploaded.",
            "14.3 Grace period. Because Canvas uploads can take a few minutes to complete, a submission whose time "
            "is no more than 15 minutes after a deadline is treated as on time. A submission later than that is late, "
            "and its lateness is measured from the deadline itself, not from the end of the grace period.",
            "14.4 Canvas outages. If Canvas is unavailable for more than 30 minutes during the six hours before a "
            "deadline, as confirmed by the university's IT status page, the instructor will move the deadline for "
            "the whole class and announce the new deadline in Canvas.",
            "14.5 Points possible. Points possible means the maximum rubric score for an assignment as shown in "
            "Canvas, before any penalty. Percentages in this document are percentages of points possible.",
            "14.6 Recording. Scores are recorded in Canvas as numbers, to the nearest half point. Penalties and caps "
            "under Sections 7, 10 and 11 are applied by the teaching team before the score is recorded.",
        ]),
        ("Section 15. Grade Questions and Corrections", [
            "Questions about a score should be raised with the TA who graded the work within seven days after the "
            "grade is released. If the question is not resolved, the student may ask the instructor to review the "
            "grade; the instructor's review may raise, lower or confirm the score.",
            "Clerical errors, for example a score entered for the wrong student or a penalty applied incorrectly, "
            "are corrected at any time during the term once they are noticed. The teaching team keeps a tracking "
            "sheet of rubric scores, penalties and recorded grades so that every recorded score can be explained.",
        ]),
        ("Section 16. Campus Resources and Expectations", [
            "Lakeshore State is committed to an inclusive learning environment. Discrimination and harassment, "
            "including sexual harassment and sexual violence, are prohibited. Faculty and teaching assistants are "
            "responsible employees and must report incidents they learn about to the Title IX office; confidential "
            "support is available through the Counseling Center and the Campus Advocacy Office.",
            "The Writing Center offers one-on-one consultations on lab reports at any stage of drafting. The "
            "Counseling Center offers same-day appointments, and the Basic Needs office helps with food and "
            "housing insecurity. If something outside the classroom is affecting your work, please reach out to "
            "the instructor or to the Dean of Students Office early; it is much easier to help before deadlines "
            "have passed.",
            "Classroom conduct: discussions in this course sometimes touch on sensitive topics such as mental "
            "health, discrimination and trauma. Treat your classmates' contributions with respect and keep personal "
            "information shared in lab sections confidential.",
        ]),
        ("Section 17. Research Participation Requirement", [
            "As part of learning how psychological research is done from the participant's side, every student "
            "completes four credits of research participation through the department's SONA system by the last day "
            "of classes. One credit corresponds to roughly thirty minutes of participation. Studies are reviewed by "
            "the Lakeshore State Institutional Review Board and you may withdraw from any study at any time without "
            "penalty.",
            "Students who prefer not to participate, or who are under 18, may complete the alternative assignment "
            "instead: a two-page summary of a recent empirical article from an approved list, worth one credit per "
            "summary. Participation credit is recorded by the SONA administrator and is not part of the gradebook "
            "for this course; missing credits are reported to the instructor and result in an Incomplete until "
            "they are completed.",
            "Research participation credits cannot be transferred between courses, and credits earned for another "
            "course in the same term do not count towards PSYC 3150. Questions about SONA should be sent to "
            "sona-admin@lakeshore.edu rather than to the teaching team.",
        ]),
        ("Section 18. Data Handling and Research Ethics in Labs", [
            "Several labs use data collected from Lakeshore State students, including the Campus Belonging Survey "
            "used in Lab Report 3. These data sets have been de-identified and are provided for teaching only. You "
            "may not attempt to re-identify participants, combine the data with other sources, or share the files "
            "outside the course. Delete your copies at the end of the term.",
            "When you collect your own data in lab, follow the protocol on the assignment page exactly. The class "
            "protocols have been approved by the IRB as minimal-risk teaching exercises on the condition that "
            "participants are classmates, that no identifying information is recorded, and that every participant "
            "receives the written debriefing provided. Deviating from a protocol, for example by recruiting "
            "friends outside the class or adding questions, requires prior written approval from the instructor.",
            "Data files must be stored in your Lakeshore OneDrive account, not on personal cloud services. If you "
            "lose a data file, ask your TA for the class copy; do not reconstruct values from memory. Report any "
            "accidental disclosure of data to the instructor immediately.",
        ]),
        ("Section 19. Tentative Schedule", [
            "Weeks 1-2: the science of psychology; claims, evidence and validity. Weeks 3-4: measurement, "
            "reliability and validity; observational methods (Lab Report 1). Weeks 5-6: experiments, random "
            "assignment and confounds (Lab Report 2). Week 7: review and midterm exam (Thursday, October 22). "
            "Weeks 8-9: surveys, sampling and scale construction (Lab Report 3). Week 10: quasi-experiments and "
            "small-N designs. Weeks 11-12: factorial designs and interactions (Lab Report 4). Week 13: Thanksgiving "
            "break. Weeks 14-15: replication, open science and the final research paper (due Friday, December 11).",
            "Quiz 1 closes September 18, Quiz 2 October 9, Quiz 3 October 30 and Quiz 4 November 13, each at 11:59 "
            "p.m. Central Time. The instructor may adjust the schedule; any change is announced in Canvas at least "
            "one week in advance.",
        ]),
        ("Section 20. Using jamovi in This Course", [
            "jamovi is a free, open-source statistics program built on R. It is installed on every machine in the "
            "Clark Hall computer lab and in the Main Library. Install the current release on your own laptop before "
            "the first lab section; the version used for grading is 2.6, and output from older versions may differ "
            "slightly in the formatting of tables.",
            "Each lab includes a short jamovi walkthrough on the assignment page. You will learn to import CSV files, "
            "set the measurement level of each variable, compute new variables, reverse-score items, check "
            "reliability with Cronbach's alpha and McDonald's omega, run descriptive statistics, independent and "
            "paired t tests, one-way ANOVA with post hoc comparisons, correlation and simple regression, and export "
            "APA-formatted tables.",
            "Save your analyses as .omv files, which store the data, the analyses and the output together. When a "
            "result in your report differs from the TA's reproduction, the .omv file is the quickest way to find out "
            "why. Common causes include forgetting to reverse-score items, filtering out cases without saying so in "
            "the method section, and treating an ordinal variable as continuous.",
            "Students who already know R or Python may use them instead, provided the report includes the same "
            "statistics and the code is available on request. The teaching team supports jamovi only; help with "
            "other software is at the discretion of your TA.",
        ]),
        ("Section 21. Writing Support and Feedback", [
            "Writing is assessed throughout the course, and you are encouraged to use the support available. The "
            "Writing Center offers forty-five minute appointments in person and online; bring the assignment page "
            "and the rubric. Consultants will not edit your report for you, but they will help you organize an "
            "argument, structure a results section and use APA citations correctly.",
            "TAs hold a writing workshop in the lab section before each report is due, where you can bring a draft "
            "introduction or method section for peer feedback. Feedback in the workshop is formative and does not "
            "affect your grade. Feedback on submitted reports is returned through Canvas with the rubric scores and "
            "comments in the margins of your PDF.",
            "Students who are multilingual writers may request an additional meeting with their TA to go over "
            "feedback on language use. Rubric scoring for APA style and mechanics focuses on errors that interfere "
            "with meaning rather than on accent or idiom.",
        ]),
        ("Appendix A. Lab Report Rubric Descriptors", [
            "Research question and hypotheses (8 points). Excellent (7-8): the question is clearly motivated by at "
            "least two cited sources, the hypotheses are directional where theory permits and are stated in terms "
            "of the operationalized variables. Proficient (5-6): the question is clear but the motivation relies on "
            "a single source or the hypotheses are stated in conceptual rather than operational terms. Developing "
            "(3-4): the question is vague or the hypotheses cannot be tested with the design used. Beginning (0-2): "
            "no identifiable research question.",
            "Method (10 points). Excellent (9-10): participants, materials, design and procedure are described in "
            "enough detail that a classmate could replicate the study; the design is named correctly; variables and "
            "their levels are identified. Proficient (6-8): minor omissions, such as the number of items in a scale "
            "or the order of conditions. Developing (3-5): the design is misidentified or key procedural details are "
            "missing. Beginning (0-2): the method section is missing or describes a different study.",
            "Analysis (12 points). Excellent (11-12): the analyses match the hypotheses and the design, assumptions "
            "are checked and reported, and effect sizes with confidence intervals accompany every test. Proficient "
            "(8-10): correct tests with incomplete assumption checks or missing effect sizes. Developing (4-7): an "
            "inappropriate test for the design, or results that cannot be reproduced from the data set. Beginning "
            "(0-3): no inferential analysis.",
            "Results reporting (10 points). Excellent (9-10): results are reported in APA format with test "
            "statistics, degrees of freedom, exact p values and effect sizes; tables and figures are labeled, "
            "referenced in the text and do not duplicate one another. Proficient (6-8): minor formatting errors. "
            "Developing (3-5): results are described without statistics or tables are unlabeled. Beginning (0-2): "
            "results are missing or contradict the output.",
            "Discussion (6 points). Excellent (6): the findings are interpreted in relation to the hypotheses and "
            "the cited literature, at least two specific limitations are discussed with their likely effect on the "
            "conclusions, and a concrete next study is proposed. Proficient (4-5): limitations are generic. "
            "Developing (2-3): the discussion restates the results. Beginning (0-1): no discussion.",
            "APA style and mechanics (4 points). Title page, running head where required, headings, in-text "
            "citations and the reference list follow APA 7th edition; the writing is clear and free of distracting "
            "errors. Deduct one point for each category of recurring error, to a minimum of zero.",
        ]),
        ("Appendix B. Submission Checklist", [
            "Before you upload a lab report, check that: the file is a single PDF that opens without a password; "
            "your name appears on the title page and nowhere else in the body of the report; the abstract is no "
            "longer than 150 words; every table and figure is numbered and referred to in the text; every in-text "
            "citation appears in the reference list and vice versa; the data set and the jamovi output you relied on "
            "are the ones posted for this lab; and you have included the generative AI note required by Section 13 "
            "if it applies to you.",
            "After uploading, open the submission in Canvas and confirm that the correct file is attached. If you "
            "notice a mistake, you may upload a corrected file to the same assignment; read Section 14.2 first, "
            "because the timing of the corrected upload matters.",
            "Keep the jamovi file (.omv) for each lab until final grades are posted. A TA may ask to see it when a "
            "result cannot be reproduced from the posted data, and an unexplained discrepancy between your output "
            "and your report will be treated as a possible integrity issue under Section 13.",
        ]),
        ("Appendix C. Frequently Asked Questions", [
            "Can I submit a lab report early? Yes. Canvas accepts submissions as soon as the assignment opens. Early "
            "submission earns no bonus, but it protects you from last-minute technical problems.",
            "My lab partner and I collected data together. Do we submit one report? No. Each student writes and "
            "submits their own report; see Section 6 and Section 13.",
            "Is there a minimum length? No. Most strong reports are eight to twelve pages including references, "
            "tables and figures, but the rubric rewards clarity rather than length.",
            "Can I use a template from the Writing Center? Yes, the Writing Center's APA student-paper template is "
            "recommended. Delete the template's example text before you submit.",
            "Where do I see my feedback? Rubric scores and comments appear on the assignment's submission details "
            "page in Canvas once grades for that assignment are released.",
            "Who do I contact about this course? Content questions go to your TA; deadlines, exceptions and grade "
            "reviews go to the instructor. The full rules for those requests are in Sections 9 through 12 and 15.",
        ]),
    ]


# ---------------------------------------------------------------- canvas
def cuser(uid, first, last, email, role, bio=""):
    name = f"{first} {last}"
    return {"id": uid, "name": name, "short_name": first, "sortable_name": f"{last}, {first}", "email": email,
            "avatar_url": avatar(name), "role": role, "pronouns": None, "bio": bio}


SYLLABUS_HTML = (
    "<h2>PSYC 3150 - Research Methods in Psychology (Fall 2026)</h2>"
    "<p>Dr. Helen Okafor - Clark Hall 214 - office hours Tue 1:00-3:00 pm. TAs: Jordan Ellis (lab 01), Kevin Tran (lab 02).</p>"
    "<h3>Grading at a glance</h3><ul><li>Lab reports (4 x 50 pts): 40%</li><li>Quizzes (4 x 20 pts): 15%</li>"
    "<li>Midterm exam: 20%</li><li>Final research paper: 25%</li></ul>"
    "<h3>Late work, extensions and resubmissions (summary)</h3>"
    "<p>Late lab reports lose 10% per day. Extensions must be requested from Dr. Okafor in advance. One lab report "
    "may be revised and resubmitted within a week of grades being posted. Accommodations are arranged through "
    "Student Accessibility Services.</p>"
    f"<p><strong>This is a summary only.</strong> The full <a href=\"{file_url(POLICY_PDF)}\">PSYC 3150 Course "
    "Policies, Fall 2026 (PDF)</a> is the authoritative version and is what the teaching team applies.</p>"
)


def build_canvas():
    rng = random.Random(3150)
    jordan = cuser(2, "Jordan", "Ellis", JORDAN_EMAIL, "ta", "PhD student, Cognitive Psychology")
    users = [cuser(1, "Helen", "Okafor", PROF_EMAIL, "teacher", "Associate Professor of Psychology"), jordan,
             cuser(3, "Kevin", "Tran", KEVIN_EMAIL, "ta", "PhD student, Social Psychology")]
    for key, uid, first, last, sis, sec in STUDENTS:
        users.append(cuser(uid, first, last, semail(key), "student"))
    grad = [(201, "Raymond", "Iqbal", "teacher"), (202, "Hye-jin", "Song", "student"), (203, "Mateo", "Ruiz", "student"),
            (204, "Abigail", "Foster", "student")]
    for uid, first, last, role in grad:
        users.append(cuser(uid, first, last, f"{first[0].lower()}{last.lower()}@{DOMAIN}", role))
    current = {**jordan, "last_login": "2026-11-17T22:10:00Z"}

    courses = [
        {"id": 31, "name": "Research Methods in Psychology", "course_code": "PSYC 3150", "term": "Fall 2026",
         "workflow_state": "available", "start_at": "2026-08-24T05:00:00Z", "end_at": "2026-12-18T06:00:00Z",
         "color": "#8E3B46", "default_view": "syllabus", "syllabus_body": SYLLABUS_HTML, "total_students": 24, "image_url": None},
        {"id": 72, "name": "Advanced Statistical Methods II", "course_code": "PSYC 7200", "term": "Fall 2026",
         "workflow_state": "available", "start_at": "2026-08-24T05:00:00Z", "end_at": "2026-12-18T06:00:00Z",
         "color": "#2D6A4F", "default_view": "modules",
         "syllabus_body": "<h2>PSYC 7200</h2><p>Multilevel and structural equation models. Weekly problem sets in R.</p>",
         "total_students": 11, "image_url": None},
        {"id": 10, "name": "Introduction to Psychology", "course_code": "PSYC 1010", "term": "Spring 2026",
         "workflow_state": "completed", "start_at": "2026-01-12T06:00:00Z", "end_at": "2026-05-08T05:00:00Z",
         "color": "#5F6368", "default_view": "modules", "syllabus_body": "<p>Spring 2026 section 004.</p>",
         "total_students": 180, "image_url": None},
    ]
    enrollments, eid = [], 1

    def enroll(uid, cid, typ, sec=1, created="2026-08-20T15:00:00Z"):
        nonlocal eid
        enrollments.append({"id": eid, "user_id": uid, "course_id": cid, "type": typ, "enrollment_state": "active",
                            "course_section_id": sec, "created_at": created})
        eid += 1

    enroll(1, 31, "TeacherEnrollment")
    enroll(2, 31, "TaEnrollment", 1)
    enroll(3, 31, "TaEnrollment", 2)
    for key, uid, *_rest, sec in STUDENTS:
        enroll(uid, 31, "StudentEnrollment", sec, "2026-08-22T18:00:00Z")
    enroll(201, 72, "TeacherEnrollment", 7)
    for uid in (2, 202, 203, 204):
        enroll(uid, 72, "StudentEnrollment", 7)
    enroll(2, 10, "TaEnrollment", 4, "2026-01-05T15:00:00Z")

    groups = [
        {"id": 311, "course_id": 31, "name": "Lab Reports", "weight": 40, "position": 1},
        {"id": 312, "course_id": 31, "name": "Quizzes", "weight": 15, "position": 2},
        {"id": 313, "course_id": 31, "name": "Midterm Exam", "weight": 20, "position": 3},
        {"id": 314, "course_id": 31, "name": "Final Research Paper", "weight": 25, "position": 4},
        {"id": 721, "course_id": 72, "name": "Problem Sets", "weight": 60, "position": 1},
        {"id": 722, "course_id": 72, "name": "Project", "weight": 40, "position": 2},
    ]

    def asg(aid, cid, gid, name, desc, due, pts, types, pos, published=True, needs=0):
        return {"id": aid, "course_id": cid, "assignment_group_id": gid, "name": name, "description": desc,
                "due_at": due, "points_possible": pts, "grading_type": "points", "submission_types": types,
                "published": published, "position": pos, "needs_grading_count": needs,
                "allowed_extensions": ["pdf"] if "online_upload" in types else [],
                "workflow_state": "published" if published else "unpublished"}

    lab_desc = ("<p>Write up this lab as an APA-style empirical report (title page through references) and upload one "
                "PDF. Rubric: research question 8, method 10, analysis 12, results 10, discussion 6, APA style 4.</p>"
                "<p>Late work, extensions, accommodations and resubmissions follow the Course Policies PDF linked on "
                "the Syllabus page.</p>")
    assignments = [
        asg(3101, 31, 311, "Lab Report 1: Observational Coding", lab_desc, "2026-09-26T04:59:00Z", 50, ["online_upload"], 1),
        asg(3102, 31, 311, "Lab Report 2: Experimental Design", lab_desc, LAB2_DUE, 50, ["online_upload"], 2),
        asg(3103, 31, 311, "Lab Report 3: Survey Methods", lab_desc +
            "<p>Data set: the Campus Belonging Survey (n = 412). Report Cronbach's alpha for each subscale.</p>",
            LAB3_DUE, 50, ["online_upload"], 3, needs=len(TODO_LAB3)),
        asg(3104, 31, 311, "Lab Report 4: Factorial Designs", lab_desc, "2026-12-05T05:59:00Z", 50, ["online_upload"], 4),
        asg(3111, 31, 312, "Quiz 1: Claims and Validity", "<p>20 questions, 30 minutes.</p>", "2026-09-19T04:59:00Z", 20, ["online_quiz"], 1),
        asg(3112, 31, 312, "Quiz 2: Measurement", "<p>20 questions, 30 minutes.</p>", "2026-10-10T04:59:00Z", 20, ["online_quiz"], 2),
        asg(3113, 31, 312, "Quiz 3: Experiments", "<p>20 questions, 30 minutes.</p>", "2026-10-31T04:59:00Z", 20, ["online_quiz"], 3),
        asg(3114, 31, 312, "Quiz 4: Surveys and Sampling", "<p>20 questions, 30 minutes.</p>", "2026-11-14T05:59:00Z", 20, ["online_quiz"], 4),
        asg(3121, 31, 313, "Midterm Exam", "<p>In class, Clark Hall 101.</p>", "2026-10-22T19:00:00Z", 100, ["on_paper"], 1),
        asg(3131, 31, 314, "Final Research Paper", "<p>Details to follow.</p>", "2026-12-12T05:59:00Z", 100, ["online_upload"], 1, published=False),
        asg(7201, 72, 721, "PS 7: Random Slopes", "<p>R markdown.</p>", "2026-11-12T05:59:00Z", 30, ["online_upload"], 1),
        asg(7202, 72, 721, "PS 8: Latent Variables", "<p>R markdown.</p>", "2026-11-19T05:59:00Z", 30, ["online_upload"], 2),
        asg(7210, 72, 722, "Project Proposal", "<p>Two pages.</p>", "2026-11-26T05:59:00Z", 20, ["online_upload"], 1),
    ]

    subs, sid = [], 1

    def sub(aid, uid, score, submitted, late=False, attempt=1, state=None, graded_at=None):
        nonlocal sid
        subs.append({"id": sid, "assignment_id": aid, "user_id": uid, "score": score,
                     "grade": None if score is None else num(score), "submitted_at": submitted,
                     "graded_at": None if score is None else (graded_at or (submitted[:10] + "T18:00:00Z")),
                     "workflow_state": state or ("graded" if score is not None else "submitted"),
                     "submission_type": "online_upload", "late": late, "missing": False, "excused": False,
                     "attempt": attempt, "body": None})
        sid += 1

    lab1_scores, lab2_attempt1 = {}, {}
    for key, uid, *_ in STUDENTS:
        base = rng.randint(31, 47)
        lab1_scores[key] = 42.5 if key == "shah" else base
        sub(3101, uid, lab1_scores[key], f"2026-09-2{rng.randint(4, 5)}T{rng.randint(14, 23):02d}:{rng.randint(0, 59):02d}:00Z",
            attempt=2 if key in ("shah", "wright", "zhao") else 1)
    for key, uid, *_ in STUDENTS:
        orig = LAB2_RESUB[key][0] if key in LAB2_RESUB else rng.randint(30, 48)
        t1 = f"2026-10-16T{rng.randint(13, 23):02d}:{rng.randint(0, 59):02d}:00Z"
        lab2_attempt1[key] = t1
        if key in LAB2_RESUB:
            sub(3102, uid, orig, LAB2_RESUB[key][2], attempt=2, state="submitted", graded_at="2026-10-30T20:40:00Z")
        else:
            sub(3102, uid, orig, t1, graded_at="2026-10-30T20:40:00Z")
    for aid, due in ((3111, "2026-09-18"), (3112, "2026-10-09"), (3113, "2026-10-30"), (3114, "2026-11-13")):
        for key, uid, *_ in STUDENTS:
            sub(aid, uid, rng.randint(12, 20), f"{due}T{rng.randint(14, 23):02d}:{rng.randint(0, 59):02d}:00Z")
    for key, uid, *_ in STUDENTS:
        sub(3121, uid, rng.randint(64, 97), "2026-10-22T19:00:00Z")
    for key, uid, *_ in STUDENTS:
        rubric, attempts = LAB3[key]
        latest = attempts[-1]
        is_late = z(latest) > z(LAB3_DUE)  # Canvas flags against the base due date (no overrides set)
        sub(3103, uid, rubric if key in KEVIN_DONE else None, latest, late=is_late, attempt=len(attempts),
            graded_at="2026-11-16T23:20:00Z")
    for aid in (7201,):
        for uid in (2, 202, 203, 204):
            sub(aid, uid, rng.randint(22, 30), "2026-11-11T23:00:00Z")
    for uid in (202, 203):
        sub(7202, uid, None, "2026-11-17T20:00:00Z")

    modules = [
        {"id": 3101, "course_id": 31, "name": "Weeks 1-4: Claims, Measurement, Observation", "position": 1, "published": True, "items_count": 3, "state": "completed"},
        {"id": 3102, "course_id": 31, "name": "Weeks 5-7: Experiments", "position": 2, "published": True, "items_count": 3, "state": "completed"},
        {"id": 3103, "course_id": 31, "name": "Weeks 8-9: Surveys and Sampling", "position": 3, "published": True, "items_count": 3, "state": "started"},
        {"id": 3104, "course_id": 31, "name": "Weeks 11-12: Factorial Designs", "position": 4, "published": True, "items_count": 1, "state": "unlocked"},
        {"id": 7201, "course_id": 72, "name": "Unit 4: Multilevel Models", "position": 1, "published": True, "items_count": 1, "state": "started"},
    ]
    module_items = [
        {"id": 1, "module_id": 3101, "title": "Lab Report 1: Observational Coding", "type": "Assignment", "content_id": 3101, "position": 1, "indent": 0, "published": True},
        {"id": 2, "module_id": 3101, "title": "Quiz 1: Claims and Validity", "type": "Assignment", "content_id": 3111, "position": 2, "indent": 0, "published": True},
        {"id": 3, "module_id": 3101, "title": "Quiz 2: Measurement", "type": "Assignment", "content_id": 3112, "position": 3, "indent": 0, "published": True},
        {"id": 4, "module_id": 3102, "title": "Lab Report 2: Experimental Design", "type": "Assignment", "content_id": 3102, "position": 1, "indent": 0, "published": True},
        {"id": 5, "module_id": 3102, "title": "Quiz 3: Experiments", "type": "Assignment", "content_id": 3113, "position": 2, "indent": 0, "published": True},
        {"id": 6, "module_id": 3102, "title": "Midterm Exam", "type": "Assignment", "content_id": 3121, "position": 3, "indent": 0, "published": True},
        {"id": 7, "module_id": 3103, "title": "Lab Report 3: Survey Methods", "type": "Assignment", "content_id": 3103, "position": 1, "indent": 0, "published": True},
        {"id": 8, "module_id": 3103, "title": "Quiz 4: Surveys and Sampling", "type": "Assignment", "content_id": 3114, "position": 2, "indent": 0, "published": True},
        {"id": 9, "module_id": 3103, "title": "Campus Belonging Survey codebook", "type": "Page", "content_id": 3, "position": 3, "indent": 1, "published": True},
        {"id": 10, "module_id": 3104, "title": "Lab Report 4: Factorial Designs", "type": "Assignment", "content_id": 3104, "position": 1, "indent": 0, "published": True},
        {"id": 11, "module_id": 7201, "title": "PS 7: Random Slopes", "type": "Assignment", "content_id": 7201, "position": 1, "indent": 0, "published": True},
    ]
    announcements = [
        {"id": 1, "course_id": 31, "title": "Welcome to PSYC 3150", "message": "<p>Welcome! Please read the Course Policies PDF linked on the Syllabus page before our first lab.</p>",
         "author_id": 1, "posted_at": "2026-08-24T14:00:00Z", "read_state": "read", "published": True},
        {"id": 2, "course_id": 31, "title": "Lab Report 1 grades posted", "message": "<p>Lab Report 1 grades and rubric feedback are now visible in Canvas.</p>",
         "author_id": 1, "posted_at": "2026-10-02T20:30:00Z", "read_state": "read", "published": True},
        {"id": 3, "course_id": 31, "title": "Lab Report 2 grades are released",
         "message": "<p>Grades and feedback for Lab Report 2 are now released for everyone. If you want to use your "
                    "resubmission on this report, see Section 10 of the Course Policies for the window and the rules.</p>",
         "author_id": 1, "posted_at": LAB2_RELEASED, "read_state": "read", "published": True},
        {"id": 4, "course_id": 31, "title": "Midterm review session", "message": "<p>Review session Tuesday Oct 20, 6 pm, Clark 101.</p>",
         "author_id": 1, "posted_at": "2026-10-15T16:00:00Z", "read_state": "read", "published": True},
        {"id": 5, "course_id": 31, "title": "Lab Report 4 data set posted", "message": "<p>The factorial data set for Lab Report 4 is in Files &gt; Lab Data.</p>",
         "author_id": 1, "posted_at": "2026-11-16T15:00:00Z", "read_state": "unread", "published": True},
        {"id": 6, "course_id": 72, "title": "PS 8 clarification", "message": "<p>For question 3 use the robust ML estimator.</p>",
         "author_id": 201, "posted_at": "2026-11-16T18:00:00Z", "read_state": "unread", "published": True},
    ]
    pages = [
        {"id": 1, "course_id": 31, "title": "Course Policies (full PDF)", "url": "course-policies",
         "body": f"<p>The binding course policies for Fall 2026 are in <a href=\"{file_url(POLICY_PDF)}\">{POLICY_PDF}</a>.</p>",
         "published": True, "front_page": False, "created_at": "2026-08-20T16:00:00Z", "updated_at": "2026-08-20T16:00:00Z",
         "editing_roles": "teachers", "last_edited_by": 1},
        {"id": 2, "course_id": 31, "title": "Lab Section Expectations", "url": "lab-section-expectations",
         "body": "<p>Come to lab having done the pre-lab worksheet. Bring a laptop with jamovi installed.</p>",
         "published": True, "front_page": False, "created_at": "2026-08-20T16:10:00Z", "updated_at": "2026-08-20T16:10:00Z",
         "editing_roles": "teachers", "last_edited_by": 1},
        {"id": 3, "course_id": 31, "title": "Campus Belonging Survey codebook", "url": "belonging-codebook",
         "body": "<p>Items B1-B12 (belonging), S1-S8 (support). Reverse-score B4, B9, S3.</p>",
         "published": True, "front_page": False, "created_at": "2026-10-26T16:00:00Z", "updated_at": "2026-10-26T16:00:00Z",
         "editing_roles": "teachers", "last_edited_by": 1},
    ]
    folders = [
        {"id": 31, "course_id": 31, "name": "course files", "parent_folder_id": None, "position": 1, "files_count": 2, "folders_count": 2},
        {"id": 32, "course_id": 31, "name": "Readings", "parent_folder_id": 31, "position": 1, "files_count": 2, "folders_count": 0},
        {"id": 33, "course_id": 31, "name": "Lab Data", "parent_folder_id": 31, "position": 2, "files_count": 3, "folders_count": 0},
    ]

    def cfile(fid, name, ctype, size, folder, created, url):
        return {"id": fid, "course_id": 31, "display_name": name, "filename": name, "content_type": ctype, "size": size,
                "folder_id": folder, "created_at": created, "updated_at": created, "url": url}

    files = [
        cfile(1, POLICY_PDF, "application/pdf", 61000, 31, "2026-08-20T16:00:00Z", file_url(POLICY_PDF)),
        cfile(2, "Lab_Report_Rubric.pdf", "application/pdf", 88000, 31, "2026-08-20T16:05:00Z", "#"),
        cfile(3, "Morling_ch5_measurement.pdf", "application/pdf", 1420000, 32, "2026-09-07T13:00:00Z", "#"),
        cfile(4, "Dillman_survey_design.pdf", "application/pdf", 990000, 32, "2026-10-26T13:00:00Z", "#"),
        cfile(5, "observation_coding.csv", "text/csv", 48000, 33, "2026-09-14T13:00:00Z", "#"),
        cfile(6, "belonging_survey.csv", "text/csv", 96000, 33, "2026-10-26T13:00:00Z", "#"),
        cfile(7, "factorial_lab4.csv", "text/csv", 51000, 33, "2026-11-16T15:00:00Z", "#"),
    ]
    calendar = [
        {"id": 1, "title": "Lab 01 (Jordan)", "description": "Clark 012", "start_at": "2026-11-18T20:00:00Z", "end_at": "2026-11-18T21:50:00Z",
         "all_day": False, "location_name": "Clark Hall 012", "context_code": "course_31", "context_name": "PSYC 3150", "workflow_state": "active"},
        {"id": 2, "title": "TA grade check with Dr. Okafor", "description": "Lab 3 + Lab 2 resubmissions posted", "start_at": "2026-11-19T21:00:00Z",
         "end_at": "2026-11-19T21:30:00Z", "all_day": False, "location_name": "Clark Hall 214", "context_code": "course_31",
         "context_name": "PSYC 3150", "workflow_state": "active"},
        {"id": 3, "title": "PSYC 7200 seminar", "description": "", "start_at": "2026-11-19T15:00:00Z", "end_at": "2026-11-19T17:30:00Z",
         "all_day": False, "location_name": "Clark Hall 330", "context_code": "course_72", "context_name": "PSYC 7200", "workflow_state": "active"},
    ]
    conversations = [
        {"id": 1, "subject": "Lab 4 groups", "workflow_state": "read", "last_message": "Can Owen join our group for lab 4?",
         "last_message_at": "2026-11-16T19:00:00Z", "message_count": 1, "starred": False, "private": True,
         "participants": [{"id": 2, "name": "Jordan Ellis"}, {"id": 111, "name": "Chloe Martin"}], "context_name": "PSYC 3150", "context_id": 31},
    ]
    conv_messages = [
        {"id": 1, "conversation_id": 1, "author_id": 111, "body": "Can Owen join our group for lab 4?", "created_at": "2026-11-16T19:00:00Z",
         "generated": False, "attachments": []},
    ]
    todo = [{"id": 1, "type": "grading", "assignment_id": 3103, "course_id": 31, "title": "Grade Lab Report 3: Survey Methods",
             "needs_grading_count": len(TODO_LAB3), "due_at": LAB3_DUE, "points_possible": 50}]
    return {
        "currentUser": current, "users": users, "courses": courses, "enrollments": enrollments,
        "assignmentGroups": groups, "assignments": assignments, "submissions": subs, "modules": modules,
        "moduleItems": module_items, "announcements": announcements, "announcementReplies": [],
        "discussionTopics": [], "discussionEntries": [], "conversations": conversations,
        "conversationMessages": conv_messages, "calendarEvents": calendar, "pages": pages, "files": files,
        "folders": folders, "todoItems": todo, "dashboardView": "cards", "activeCourseNav": {},
    }, lab2_attempt1


# ---------------------------------------------------------------- gmail
def p(*paras):
    return "".join(f"<p>{x}</p>" for x in paras)


def email(eid, name, sender, subject, body, ts, *, to=None, cc=None, read=True, thread=None, category="primary", folder="inbox"):
    return {"id": eid, "threadId": thread or f"t_{eid}", "from": {"name": name, "email": sender, "avatar": avatar(name)},
            "to": to or [{"name": "Jordan Ellis", "email": JORDAN_EMAIL}], "cc": cc or [], "bcc": [],
            "subject": subject, "body": body, "snippet": "", "timestamp": ts, "read": read, "starred": False,
            "important": False, "labels": [], "category": category, "folder": folder, "attachments": []}


PROF = ("Helen Okafor", PROF_EMAIL)
KEVIN = ("Kevin Tran", KEVIN_EMAIL)
TAS = [{"name": "Jordan Ellis", "email": JORDAN_EMAIL}, {"name": "Kevin Tran", "email": KEVIN_EMAIL}]


def sas_letter(key, issued_long):
    return ("<p>---------- Forwarded message ----------<br>From: Student Accessibility Services &lt;sas@lakeshore.edu&gt;<br>"
            "To: Helen Okafor</p>"
            f"<p><b>Accommodation Letter - Fall 2026</b><br>Student: {full(key)} ({S[key][4]})<br>Course: PSYC 3150 Research Methods in Psychology<br>"
            f"Date issued: {issued_long}</p>"
            "<p>The student named above is registered with Student Accessibility Services and is approved for the "
            "following accommodations in this course:</p>"
            "<p>1. Flexible deadlines for assignments, as provided for in the course syllabus.<br>"
            "2. Extended time (1.5x) on quizzes and exams, administered by the SAS Testing Center.<br>"
            "3. Permission to record lectures for personal study.</p>"
            "<p>Please contact SAS if you have questions about implementing these accommodations. This letter is "
            "confidential.</p><p>Mara Delgado<br>Accessibility Specialist, Student Accessibility Services</p>")


def build_gmail():
    E = []
    E.append(email("g01", *PROF, "Lab 3 + Lab 2 resubmissions before Thursday",
                   p("Hi Jordan,",
                     "Kevin is at SPSP through Friday, so could you finish posting Lab Report 3 and the Lab Report 2 "
                     "resubmissions before our grade check on Thursday? He told me he entered the section 02 reports "
                     "that were on time before he left; everything else on Lab 3 and all of the resubmissions still "
                     "need to go into Canvas.",
                     "I've had two grade appeals already this term, so please go strictly by the Course Policies PDF "
                     "rather than the syllabus summary, and keep the tracker in sync so every score can be explained. "
                     "Extensions I approved, SAS letters and the Dean's notices are all in your inbox.",
                     "Thanks!<br>Helen"),
                   "2026-11-18T00:40:00Z", to=TAS, read=False))
    E.append(email("g02", *PROF, "Lab 3 extension - Tomás Herrera",
                   p("Jordan, Kevin -", "Tomás Herrera wrote to me yesterday (well before the deadline) about a family "
                     "wedding out of state. I've approved an extension for Lab Report 3 to Sunday, November 8 at 11:59 pm.", "Helen"),
                   "2026-11-04T15:20:00Z", to=TAS))
    E.append(email("g03", *PROF, "Lab 3 extension - Aisha",
                   p("Hi both,", "Approved a Lab Report 3 extension for Aisha Bello to Monday, November 9 at 11:59 pm. "
                     "She emailed me Tuesday about a family emergency.", "Helen"),
                   "2026-11-05T15:12:00Z", to=TAS, thread="t_aisha"))
    E.append(email("g04", *PROF, "Re: Lab 3 extension - Aisha",
                   p("Correction, sorry - wrong Aisha! The extension to Monday 11/9 at 11:59 pm is for <b>Aisha Rahman</b> "
                     "(section 02), not Aisha Bello. Aisha Bello has not asked for anything, so her Lab 3 deadline is "
                     "unchanged.", "Helen"),
                   "2026-11-05T17:31:00Z", to=TAS, thread="t_aisha"))
    E.append(email("g05", "Ben Fischer", semail("fischer"), "Lab 3 - can I have the weekend?",
                   p("Hi Jordan and Kevin,", "My laptop died this afternoon and I lost the last part of my discussion "
                     "section. Is there any way I could have the weekend to finish Lab 3?", "Thanks,<br>Ben (section 01)"),
                   "2026-11-07T00:05:00Z", to=TAS, thread="t_ben"))
    E.append(email("g06", *KEVIN, "Re: Lab 3 - can I have the weekend?",
                   p("Hey Ben, no worries - take the weekend, just get it in by Sunday night.", "Kevin"),
                   "2026-11-07T01:20:00Z", to=[{"name": "Ben Fischer", "email": semail("fischer")}],
                   cc=[{"name": "Jordan Ellis", "email": JORDAN_EMAIL}], thread="t_ben"))
    E.append(email("g07", *PROF, "Fwd: SAS Accommodation Letter - Grace Okonkwo",
                   p("For your records.") + sas_letter("okonkwo", "September 14, 2026"), "2026-09-14T19:02:00Z", to=TAS))
    E.append(email("g08", *PROF, "Fwd: SAS Accommodation Letter - Liam Novak",
                   p("FYI.") + sas_letter("novak", "September 21, 2026"), "2026-09-21T21:45:00Z", to=TAS))
    E.append(email("g09", *PROF, "Fwd: SAS Accommodation Letter - Sofia Brandt",
                   p("New letter for Sofia, FYI for grading.") + sas_letter("brandt", "November 10, 2026"),
                   "2026-11-10T22:15:00Z", to=TAS))
    E.append(email("g10", *PROF, "Fwd: Absence notification - Owen Park",
                   p("Forwarding for Lab 3.",
                     "---------- Forwarded message ----------<br>From: Dean of Students Office &lt;deanofstudents@lakeshore.edu&gt;",
                     "Dear Instructor,",
                     "This is to notify you that the Dean of Students Office has verified an absence for Owen Park "
                     f"({S['park'][4]}) due to a medical emergency. Verified absence period: Wednesday, November 4, 2026 "
                     "through Sunday, November 8, 2026.",
                     "This notification does not by itself excuse the student from academic work. Please apply your "
                     "course policies and work with the student on any missed work.",
                     "Office of the Dean of Students"),
                   "2026-11-09T16:30:00Z", to=TAS))
    E.append(email("g11", "Diego Alvarez", semail("alvarez"), "Lab 3 - resubmitted",
                   p("Hi Jordan,", "I realized I uploaded the wrong draft of Lab 3 yesterday afternoon (the one without "
                     "the reliability table). I uploaded the right version just now, can you grade that one please?", "Diego"),
                   "2026-11-07T19:26:00Z"))
    E.append(email("g12", "Marcus Lee", semail("lee"), "lab 3 upload",
                   p("Hey Jordan, Canvas was crawling last night and my upload went through a few minutes after "
                     "midnight. Sorry about that!", "Marcus"),
                   "2026-11-07T14:02:00Z"))
    E.append(email("g13", "Ethan Moore", semail("moore"), "Lab 3 (very late, sorry)",
                   p("Hi Jordan,", "I know this is a week late but I finally submitted Lab 3 this morning. Anything you "
                     "can do would be appreciated.", "Ethan"),
                   "2026-11-13T15:20:00Z"))
    E.append(email("g14", "Kofi Mensah", semail("mensah"), "Lab 2 resubmission",
                   p("Hi Kevin and Jordan, I resubmitted Lab 2 today with the revised results section. Hope it isn't "
                     "too late!", "Kofi"),
                   "2026-11-09T15:10:00Z", to=TAS))
    E.append(email("g15", "Priya Shah", semail("shah"), "Resubmitted Lab 2!",
                   p("Hi Kevin, I resubmitted Lab 2 with the fixes you suggested in lab. Thank you!", "Priya"),
                   "2026-11-03T17:05:00Z", to=TAS))
    E.append(email("g16", *KEVIN, "Lab 3 / resubs status",
                   p("Jordan - I put in the section 02 Lab 3 reports that were on time (7 of them, marked Y in the "
                     "tracker) and ran out of time for the rest. Rubric scores for all of Lab 3 and the six Lab 2 "
                     "resubmissions are in the tracker; I graded every resubmission that came in, so check them "
                     "against the policy before posting. The Canvas submission export is the CSV I sent you.",
                     "Off to the airport, back Saturday.", "Kevin"),
                   "2026-11-17T03:40:00Z"))
    # noise
    E.append(email("n01", "Psychology Department", f"psych-dept@{DOMAIN}", "Colloquium Friday: Dr. Ana Whitfield on memory reconsolidation",
                   p("Join us Friday at 3:30 pm in Clark 101. Refreshments at 3:15."), "2026-11-16T14:00:00Z", category="updates"))
    E.append(email("n02", "Raymond Iqbal", f"riqbal@{DOMAIN}", "PSYC 7200 - PS 8 office hours moved",
                   p("Office hours this week are Thursday 9-10 instead of Wednesday."), "2026-11-16T18:10:00Z"))
    E.append(email("n03", "Canvas", "notifications@instructure.com", "Lab Report 4 data set posted - PSYC 3150",
                   p("Helen Okafor posted an announcement: Lab Report 4 data set posted."), "2026-11-16T15:01:00Z", category="updates"))
    E.append(email("n04", "Graduate Student Association", f"gsa@{DOMAIN}", "Travel grant deadline Dec 1",
                   p("Spring conference travel grants are due December 1."), "2026-11-12T16:00:00Z", category="promotions"))
    E.append(email("n05", "Chloe Martin", semail("martin"), "Lab 4 question",
                   p("Hi Jordan, for Lab 4 do we need to report simple effects if the interaction isn't significant?"),
                   "2026-11-17T20:30:00Z", read=False))
    E.append(email("n06", "Research Compliance", f"irb@{DOMAIN}", "Reminder: CITI refresher due",
                   p("Your CITI human subjects refresher expires on December 15, 2026."), "2026-11-10T13:00:00Z", category="updates"))
    E.append(email("n07", "Samir Haddad", semail("haddad"), "Lab 4 extension?",
                   p("Hi Jordan, I have three exams the week of Dec 1, would it be possible to get an extension on Lab 4?"),
                   "2026-11-17T23:10:00Z", read=False))
    E.append(email("n08", "Jordan Ellis", JORDAN_EMAIL, "Re: Lab 4 extension?",
                   p("Hi Samir, extensions have to come from Dr. Okafor - please email her at least 24 hours before the deadline."),
                   "2026-11-18T01:00:00Z", to=[{"name": "Samir Haddad", "email": semail("haddad")}], folder="sent", thread="t_n07"))
    E[-2]["threadId"] = "t_n07"
    E.append(email("n09", "Lakeshore Libraries", f"library@{DOMAIN}", "Your interlibrary loan is ready",
                   p("Dillman, Smyth & Christian (2014) is ready for pickup at the Main Library desk."), "2026-11-13T17:00:00Z", category="updates"))
    E.append(email("n10", "Hye-jin Song", f"hsong@{DOMAIN}", "stats study group?",
                   p("Want to work through PS 8 together Wednesday night?"), "2026-11-17T02:00:00Z"))
    E.append(email("n11", *PROF, "Lab 2 grades released",
                   p("Lab 2 grades are out to students as of this afternoon - resubmission window starts now."),
                   "2026-10-30T21:15:00Z", to=TAS))
    E.append(email("n12", "Kevin Tran", KEVIN_EMAIL, "Re: Lab 1 resubmission - Priya",
                   p("Graded Priya's Lab 1 resubmission, logged it in the tracker."), "2026-10-09T20:00:00Z", to=TAS))
    for e in E:
        e["snippet"] = e["body"].replace("<p>", "").replace("</p>", " ").replace("<br>", " ").replace("<b>", "").replace("</b>", "")[:110]
    E.sort(key=lambda e: e["timestamp"], reverse=True)
    return {
        "user": {"userId": "u1", "username": "Jordan Ellis", "email": JORDAN_EMAIL, "avatar": avatar("Jordan Ellis")},
        "emails": E,
        "labels": [{"id": "l1", "name": "PSYC 3150", "color": "#8E3B46"}, {"id": "l2", "name": "PSYC 7200", "color": "#2D6A4F"}],
        "drafts": [],
        "settings": {"signature": "--\nJordan Ellis\nTeaching Assistant, PSYC 3150", "undoSend": 5},
    }


# ---------------------------------------------------------------- google sheets
def _isnum(v):
    try:
        float(v)
        return True
    except ValueError:
        return False


def cell(v, bold=False, bg=None):
    v = str(v)
    c = {"value": v, "formula": v, "computed": v if (v == "" or not _isnum(v)) else float(v)}
    if bold or bg:
        c["style"] = {k: val for k, val in (("bold", bold or None), ("bg", bg)) if val}
    return c


def col(i):
    return chr(65 + i)


def table(header, rows):
    data = {}
    for j, h in enumerate(header):
        data[f"{col(j)}1"] = cell(h, bold=True, bg="#E8EAED")
    for i, r in enumerate(rows, 2):
        for j, h in enumerate(header):
            if r.get(h, "") != "":
                data[f"{col(j)}{i}"] = cell(r[h])
    return data


LAB3_HEADER = ["Student", "SIS ID", "Section", "Grader", "Rubric (/50)", "Days late", "Final", "In Canvas", "Notes"]
LAB2R_HEADER = ["Student", "SIS ID", "Original", "Resubmission rubric", "Final", "In Canvas", "Notes"]
LAB3_NOTES = {
    "alvarez": "graded attempt 2 (student asked, see email)",
    "lee": "",
    "haddad": "rubric revised 11/16 after regrade question",
    "petrova": "",
    "moore": "rubric done anyway",
}
LAB2R_NOTES = {"shah": "rubric done, not posted", "mensah": "rubric done, not posted", "santos": ""}


def lab3_rows():
    rows = []
    order = sorted(STUDENTS, key=lambda s: (s[5], s[3], s[2]))
    for key, uid, first, last, sis, sec in order:
        r = {"Student": f"{first} {last}", "SIS ID": sis, "Section": str(sec), "Grader": "JE" if sec == 1 else "KT",
             "Rubric (/50)": str(LAB3[key][0]), "Notes": LAB3_NOTES.get(key, "")}
        if key in KEVIN_DONE:
            r.update({"Days late": "0", "Final": str(LAB3[key][0]), "In Canvas": "Y", "Notes": "entered 11/16 KT"})
        rows.append((key, r))
    return rows


def lab2r_rows():
    rows = []
    for key in ["cho", "lee", "shah", "santos", "mensah", "doyle"]:
        o, rs, _ = LAB2_RESUB[key]
        rows.append((key, {"Student": full(key), "SIS ID": S[key][4], "Original": str(o), "Resubmission rubric": str(rs),
                           "Notes": LAB2R_NOTES.get(key, "")}))
    return rows


TRACKER_NOTES = [
    "PSYC 3150 Fall 2026 - TA grading tracker (Jordan Ellis / Kevin Tran)",
    "Rubric scores are final once entered here; penalties/caps are applied per the Course Policies PDF before posting.",
    "Days late = late days actually counted against the student (0 if none). Final = score that is posted in Canvas.",
    "In Canvas = Y once the Final score is entered in the Canvas gradebook.",
    "Resubmissions Used = graded resubmissions this term (one per student per term).",
    "11/16 KT: entered the on-time section 02 Lab 3 rows (marked Y). Did not get to the rest.",
]


def build_sheets():
    rng = random.Random(21)
    lab2_rows = []
    for key, uid, first, last, sis, sec in sorted(STUDENTS, key=lambda s: (s[5], s[3])):
        o = LAB2_RESUB[key][0] if key in LAB2_RESUB else None
        lab2_rows.append({"Student": f"{first} {last}", "SIS ID": sis, "Section": str(sec), "Score": str(o if o is not None else rng.randint(30, 48)),
                          "In Canvas": "Y"})
    sheets = [
        {"id": "sheet_lab3", "name": "Lab 3", "rowCount": 100, "colCount": 26, "frozenRows": 1, "frozenCols": 1,
         "tabColor": "#8E3B46", "isHidden": False,
         "columnWidths": {"0": 150, "1": 100, "2": 70, "3": 65, "4": 95, "5": 80, "6": 70, "7": 80, "8": 280},
         "data": table(LAB3_HEADER, [r for _, r in lab3_rows()])},
        {"id": "sheet_lab2r", "name": "Lab 2 Resubmissions", "rowCount": 100, "colCount": 26, "frozenRows": 1, "frozenCols": 1,
         "tabColor": "#E37400", "isHidden": False,
         "columnWidths": {"0": 150, "1": 100, "2": 80, "3": 150, "4": 70, "5": 80, "6": 220},
         "data": table(LAB2R_HEADER, [r for _, r in lab2r_rows()])},
        {"id": "sheet_used", "name": "Resubmissions Used", "rowCount": 100, "colCount": 26, "frozenRows": 1, "frozenCols": 0,
         "tabColor": None, "isHidden": False, "columnWidths": {"0": 150, "1": 100, "2": 160, "3": 100, "4": 50},
         "data": table(["Student", "SIS ID", "Assignment", "Graded", "TA"],
                       [{"Student": full(k), "SIS ID": S[k][4], "Assignment": "Lab Report 1", "Graded": d, "TA": ta}
                        for k, d, ta in RESUB_USED_LAB1])},
        {"id": "sheet_lab2", "name": "Lab 2", "rowCount": 100, "colCount": 26, "frozenRows": 1, "frozenCols": 1,
         "tabColor": None, "isHidden": False, "columnWidths": {"0": 150, "1": 100},
         "data": table(["Student", "SIS ID", "Section", "Score", "In Canvas"], lab2_rows)},
        {"id": "sheet_notes", "name": "Notes", "rowCount": 100, "colCount": 26, "frozenRows": 0, "frozenCols": 0,
         "tabColor": None, "isHidden": False, "columnWidths": {"0": 720},
         "data": {f"A{i}": cell(t, bold=(i == 1)) for i, t in enumerate(TRACKER_NOTES, 1)}},
    ]
    return {"id": "workbook_psyc3150", "title": "PSYC 3150 Fall 2026 - TA Grading Tracker", "sheets": sheets,
            "activeSheetId": "sheet_lab3", "selectedCell": "A1", "selectionRange": None, "clipboard": None,
            "isDragging": False, "undoStack": [], "redoStack": [], "namedRanges": [], "conditionalFormats": [],
            "charts": [], "showGridlines": True, "showFormulas": False, "zoom": 100}


def ui_set(sheet, ref, value):
    v = str(value)
    existing = sheet["data"].get(ref, {"value": "", "formula": ""})
    sheet["data"][ref] = {**existing, "value": v, "formula": v,
                          "computed": (v if v == "" or not _isnum(v) else float(v))}


def sheet_by_id(state, sid):
    return next(s for s in state["sheets"] if s["id"] == sid)


# ---------------------------------------------------------------- export CSV
def export_rows(lab2_attempt1):
    rows = []
    for key, uid, first, last, sis, sec in STUDENTS:
        rows.append([f"{first} {last}", sis, f"PSYC 3150 - 0{sec}", "Lab Report 2: Experimental Design", 1, lab2_attempt1[key]])
        if key in LAB2_RESUB:
            rows.append([f"{first} {last}", sis, f"PSYC 3150 - 0{sec}", "Lab Report 2: Experimental Design", 2, LAB2_RESUB[key][2]])
        for i, ts in enumerate(LAB3[key][1], 1):
            rows.append([f"{first} {last}", sis, f"PSYC 3150 - 0{sec}", "Lab Report 3: Survey Methods", i, ts])
    rows.sort(key=lambda r: (r[3], r[0].split()[-1], r[0], r[4]))
    return [["student_name", "sis_user_id", "section", "assignment", "attempt", "submitted_at_utc"]] + rows


# ---------------------------------------------------------------- golden / variants
def outcomes(ignore=(), overrides=None):
    lab3 = {k: lab3_truth(k, ignore=ignore) for k in TODO_LAB3}
    lab2 = {k: lab2_truth(k, ignore=ignore) for k in LAB2_RESUB}
    for (tab, k), v in (overrides or {}).items():
        (lab3 if tab == "lab3" else lab2)[k] = v
    return lab3, lab2


def apply_run(seed, lab3, lab2):
    canvas, sheets, gmail = (copy.deepcopy(seed[k]) for k in ("canvas_lms", "google_sheets", "gmail"))
    for s in canvas["submissions"]:
        key = next((k for k in S if S[k][1] == s["user_id"]), None)
        if s["assignment_id"] == 3103 and key in lab3:
            score = float(lab3[key][1])
            score = int(score) if score == int(score) else score
            s.update({"score": score, "grade": num(score), "workflow_state": "graded", "graded_at": GRADED_AT})
        if s["assignment_id"] == 3102 and key in lab2:
            score = float(lab2[key])
            if score != float(s["score"]):
                score = int(score) if score == int(score) else score
                s.update({"score": score, "grade": num(score), "workflow_state": "graded", "graded_at": GRADED_AT})
    t3 = sheet_by_id(sheets, "sheet_lab3")
    for i, (key, _) in enumerate(lab3_rows(), 2):
        if key in lab3:
            days, final = lab3[key]
            ui_set(t3, f"F{i}", str(days))
            ui_set(t3, f"G{i}", num(final))
            ui_set(t3, f"H{i}", "Y")
    t2 = sheet_by_id(sheets, "sheet_lab2r")
    for i, (key, _) in enumerate(lab2r_rows(), 2):
        if key in lab2:
            ui_set(t2, f"E{i}", num(lab2[key]))
            ui_set(t2, f"F{i}", "Y")
    return {"canvas_lms": canvas, "google_sheets": sheets, "gmail": gmail}


def entries_csv(lab3, lab2):
    rows = [["sis_id", "assignment", "final_score"]]
    for key, _ in lab3_rows():
        if key in lab3:
            rows.append([S[key][4], "lab3", num(lab3[key][1])])
    for key, _ in lab2r_rows():
        rows.append([S[key][4], "lab2_resub", num(lab2[key])])
    return rows


NAIVE_IGNORE = ("grace", "latest_attempt", "acc_window", "retroactive", "medical", "cutoff", "cap85", "term_cap",
                "higher_of", "window")


def naive_outcomes():
    """Syllabus summary + first email of each thread + UTC dates read as local; obeys Kevin's 'take the weekend'."""
    lab3, lab2 = outcomes(ignore=NAIVE_IGNORE)
    # TA promise honoured (deadline Sun Nov 8, 11:59 pm CST)
    lab3["fischer"] = (0, LAB3["fischer"][0])
    # first Aisha email believed: extension for Bello, none for Rahman
    lab3["bello"] = (0, LAB3["bello"][0])
    d = math.ceil((z(LAB3["rahman"][1][-1]) - z(LAB3_DUE)).total_seconds() / 86400)
    lab3["rahman"] = (d, LAB3["rahman"][0] - 5 * d)
    # UTC calendar date read as the local date: Lena's 10:48 pm CST upload looks like Nov 7
    lab3["vogel"] = (1, LAB3["vogel"][0] - 5)
    return lab3, lab2


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def main(out: Path):
    canvas, lab2_attempt1 = build_canvas()
    seed = {"canvas_lms": canvas, "gmail": build_gmail(), "google_sheets": build_sheets()}
    for site, state in seed.items():
        write_json(out / "seed" / f"{site}.json", state)
    from reportlab import rl_config
    rl_config.invariant = 1  # byte-identical PDF across runs (no creation timestamp / random id)
    long_pdf(out / "seed" / "files" / "canvas_lms" / POLICY_PDF,
             "PSYC 3150 Research Methods in Psychology - Course Policies, Fall 2026", policy_sections())
    write_csv(out / "input" / "submissions_export.csv", export_rows(lab2_attempt1))

    lab3, lab2 = outcomes()
    assert set(lab3) == set(EXPECT_LAB3) and all(
        lab3[k][0] == EXPECT_LAB3[k][0] and float(lab3[k][1]) == float(EXPECT_LAB3[k][1]) for k in EXPECT_LAB3), lab3
    assert all(float(lab2[k]) == float(EXPECT_LAB2[k]) for k in EXPECT_LAB2), lab2
    golden = apply_run(seed, lab3, lab2)
    for site, state in golden.items():
        write_json(out / "golden" / f"{site}.json", state)
    write_csv(out / "golden_output" / "grade_entries.csv", entries_csv(lab3, lab2))

    n3, n2 = naive_outcomes()
    slips = {
        "slip_ta_extension": outcomes(overrides={("lab3", "fischer"): (0, LAB3["fischer"][0])}),
        "slip_accommodation_window": outcomes(overrides={("lab3", "novak"): (0, LAB3["novak"][0])}),
        "slip_term_cap": outcomes(overrides={("lab2", "shah"): 42.5}),
    }
    variants = {"golden": (golden, entries_csv(lab3, lab2)), "nop": (seed, None),
                "naive": (apply_run(seed, n3, n2), entries_csv(n3, n2))}
    for name, (s3, s2) in slips.items():
        variants[name] = (apply_run(seed, s3, s2), entries_csv(s3, s2))
    for name, (states, rows) in variants.items():
        for site, state in states.items():
            write_json(out / "variants" / name / "state" / site / "current.json", state)
            write_json(out / "variants" / name / "state" / site / "initial.json", seed[site])
        if rows:
            write_csv(out / "variants" / name / "output" / "grade_entries.csv", rows)

    lab3_tab = {S[k][4]: {"row": i, "student": full(k)} for i, (k, _) in enumerate(lab3_rows(), 2)}
    lab2_tab = {S[k][4]: {"row": i, "student": full(k)} for i, (k, _) in enumerate(lab2r_rows(), 2)}
    write_json(out / "expected.json", {
        "clock": CLOCK, "timezone": "America/Chicago",
        "canvas": {"course_id": 31, "lab3_assignment_id": 3103, "lab2_assignment_id": 3102},
        "students": {S[k][4]: {"name": full(k), "user_id": S[k][1], "section": S[k][5]} for k in S},
        "lab3_todo": {S[k][4]: {"days_late": lab3[k][0], "final": float(lab3[k][1]), "sheet_row": lab3_tab[S[k][4]]["row"]}
                      for k in TODO_LAB3},
        "lab3_kevin_done": {S[k][4]: {"final": LAB3[k][0], "sheet_row": lab3_tab[S[k][4]]["row"]} for k in KEVIN_DONE},
        "lab2_resub": {S[k][4]: {"original": LAB2_RESUB[k][0], "final": float(lab2[k]),
                                 "sheet_row": lab2_tab[S[k][4]]["row"]} for k in LAB2_RESUB},
        "sheets": {"lab3_sheet_id": "sheet_lab3", "lab2r_sheet_id": "sheet_lab2r",
                   "lab3_cols": {"days_late": "F", "final": "G", "in_canvas": "H"},
                   "lab2r_cols": {"final": "E", "in_canvas": "F"}},
        "traps": {
            "grace": S["lee"][4], "latest_attempt": S["alvarez"][4], "ta_extension_void": S["fischer"][4],
            "accommodation_inside_window": S["okonkwo"][4], "accommodation_after_window": S["novak"][4],
            "accommodation_not_retroactive": S["brandt"][4], "dean_waiver": S["park"][4], "cutoff_zero": S["moore"][4],
            "utc_boundary": S["vogel"][4], "instructor_extension": S["herrera"][4],
            "aisha_corrected_extension": S["rahman"][4], "aisha_no_extension": S["bello"][4],
            "resub_cap85": S["cho"][4], "resub_one_per_term": S["shah"][4], "resub_higher_of": S["santos"][4],
            "resub_window_closed": S["mensah"][4],
            "plain": [S[k][4] for k in ("martin", "turner", "haddad", "petrova", "cho")],
            "plain_resub": [S[k][4] for k in ("lee", "doyle")],
        },
    })


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
