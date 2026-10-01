"""Education and grading: a coursework or grading case reaches a course office."""

from __future__ import annotations

from jevbench.datagen.domains._rules import fact, kind_is, said, test
from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known

ASSESSMENTS = ("weekly quiz", "essay", "lab report", "final exam")

FACTS = (
    Fact("case", "cat", "what the course office is asked to handle: work handed in after the deadline "
         "(late_submission), a student disputing a mark (grade_appeal), a similarity check flagging a submission "
         "(plagiarism_flag), or a student asking for more time (extension_request)",
         values=("late_submission", "grade_appeal", "plagiarism_flag", "extension_request"), always=True,
         topic="what the course office is asked to handle",
         labels={"late_submission": "work was handed in after the deadline",
                 "grade_appeal": "a student disputes a mark",
                 "plagiarism_flag": "a similarity check flagged a submission",
                 "extension_request": "a student asks for more time"}),
    Fact("assessment", "cat", "what kind of assessment it is", values=ASSESSMENTS, implied_ok=True),
    Fact("days_late", "int", "how many days late the work was handed in", lo=1, hi=14, subject="days late"),
    Fact("documented", "bool", "whether the student provides a documented reason, such as a medical note"),
    Fact("mark", "int", "the mark the work received, out of 100", lo=0, hi=100, subject="marks out of 100"),
    Fact("points_disputed", "int", "how many marks the student disputes", lo=1, hi=30, subject="marks in dispute"),
    Fact("cites_rubric", "bool", "whether the student points to a specific marking criterion that was misapplied",
         speech_act=True),
    Fact("similarity", "int", "the percentage of the text that matches other sources", lo=5, hi=95,
         subject="percent similarity"),
    Fact("cited", "bool", "whether the matching passages are quoted and cited"),
    Fact("prior_case", "bool", "whether the student has an earlier academic misconduct case"),
    Fact("days_to_deadline", "int", "how many days are left before the deadline", lo=0, hi=21,
         subject="days until the deadline"),
    Fact("extensions_before", "int", "how many extensions the student already had this term", lo=0, hi=3,
         subject="earlier extensions this term"),
)


def _base(rng, **kw):
    f = {k: None for k in ("days_late", "documented", "mark", "points_disputed", "cites_rubric", "similarity",
                           "cited", "prior_case", "days_to_deadline", "extensions_before")}
    f["assessment"] = rng.choice(ASSESSMENTS[1:3])
    f.update(kw)
    return f


ARCHETYPES = (
    Archetype("late_submission", "a student handed in work after the deadline",
              lambda rng: _base(rng, case="late_submission",
                                days_late=rng.choice((rng.randint(1, 3), rng.randint(4, 7), rng.randint(8, 14))),
                                documented=rng.random() < 0.4, mark=rng.randint(20, 95))),
    Archetype("grade_appeal", "a student disputes the mark they received",
              lambda rng: _base(rng, case="grade_appeal", assessment=rng.choice(ASSESSMENTS), mark=rng.randint(20, 90),
                                points_disputed=rng.choice((rng.randint(1, 5), rng.randint(6, 10), rng.randint(11, 30))),
                                cites_rubric=rng.random() < 0.5)),
    Archetype("plagiarism_flag", "the similarity checker flags a student's submission",
              lambda rng: _base(rng, case="plagiarism_flag", similarity=rng.choice((rng.randint(5, 30),
                                                                                  rng.randint(31, 95))),
                                cited=rng.random() < 0.4, prior_case=rng.random() < 0.25)),
    Archetype("extension_request", "a student asks for more time on an assignment",
              lambda rng: _base(rng, case="extension_request", documented=rng.random() < 0.5,
                                days_to_deadline=rng.choice((rng.randint(0, 2), rng.randint(3, 21))),
                                extensions_before=rng.choice((0, 0, 1, rng.randint(2, 3))))),
)


def _action(f, m):
    kind = f["case"]
    if kind == "late_submission":
        doc = known(f, m, "documented")
        if doc is True:
            return "accept"
        late = known(f, m, "days_late")
        if UNKNOWN in (doc, late):
            return UNKNOWN
        return "refuse" if late > 7 else "penalise"
    if kind == "grade_appeal":
        return "review" if said(f, m, "cites_rubric") else "refuse"
    if kind == "plagiarism_flag":
        cited = known(f, m, "cited")
        if cited is True:
            return "accept"
        sim = known(f, m, "similarity")
        if UNKNOWN in (cited, sim):
            return UNKNOWN
        return "review" if sim > 30 else "penalise"
    before = known(f, m, "extensions_before")
    if before != UNKNOWN and before >= 2:
        return "refuse"
    doc = known(f, m, "documented")
    if UNKNOWN in (before, doc):
        return UNKNOWN
    return "accept" if doc else "refuse"


def _stakes(f, m):
    kind = f["case"]
    if kind == "late_submission":
        doc, late = known(f, m, "documented"), known(f, m, "days_late")
        if doc is True:
            return 0
        return UNKNOWN if UNKNOWN in (doc, late) else (3 if late > 7 else 2 if late > 3 else 1)
    if kind == "grade_appeal":
        pts = known(f, m, "points_disputed")
        return UNKNOWN if pts == UNKNOWN else (3 if pts > 20 else 2 if pts > 10 else 1 if pts > 5 else 0)
    if kind == "plagiarism_flag":
        cited = known(f, m, "cited")
        if cited is True:
            return 0
        sim, prior = known(f, m, "similarity"), known(f, m, "prior_case")
        return UNKNOWN if UNKNOWN in (cited, sim, prior) else 1 + int(sim > 30) + int(prior)
    doc, close = known(f, m, "documented"), known(f, m, "days_to_deadline")
    if doc is True:
        return 0
    return UNKNOWN if UNKNOWN in (doc, close) else (2 if close <= 2 else 1)


QUESTIONS = (
    Question("over_a_week_late", "noul", "Was the work handed in more than 7 days late?",
             test("days_late", lambda d: d > 7), ("days_late",), applies=kind_is("case", "late_submission")),
    Question("documented_reason", "noul", "Does the student provide a documented reason?", fact("documented"),
             ("documented",), applies=kind_is("case", "late_submission", "extension_request")),
    Question("passing_mark", "noul", "Did the work receive 50 marks or more?", test("mark", lambda n: n >= 50),
             ("mark",), applies=kind_is("case", "late_submission", "grade_appeal")),
    Question("big_dispute", "noul", "Does the student dispute more than 10 marks?",
             test("points_disputed", lambda n: n > 10), ("points_disputed",), applies=kind_is("case", "grade_appeal")),
    Question("rubric_cited", "noul", "Does the student point to a specific marking criterion that was misapplied?",
             lambda f, m: said(f, m, "cites_rubric"), ("cites_rubric",), applies=kind_is("case", "grade_appeal")),
    Question("high_similarity", "noul", "Does more than 30% of the text match other sources?",
             test("similarity", lambda n: n > 30), ("similarity",), applies=kind_is("case", "plagiarism_flag")),
    Question("properly_cited", "noul", "Are the matching passages quoted and cited?", fact("cited"), ("cited",),
             applies=kind_is("case", "plagiarism_flag")),
    Question("earlier_case", "noul", "Does the student have an earlier academic misconduct case?",
             fact("prior_case"), ("prior_case",), applies=kind_is("case", "plagiarism_flag")),
    Question("deadline_imminent", "noul", "Is the deadline 2 days away or less?",
             test("days_to_deadline", lambda d: d <= 2), ("days_to_deadline",),
             applies=kind_is("case", "extension_request")),
    Question("had_extension", "noul", "Has the student already had an extension this term?",
             test("extensions_before", lambda n: n > 0), ("extensions_before",),
             applies=kind_is("case", "extension_request")),
    Question("is_essay", "noul", "Is the assessment an essay?", test("assessment", lambda a: a == "essay"),
             ("assessment",)),
    Question("case_type", "choice", "What is the course office asked to handle?", lambda f, m: f["case"], ("case",),
             criteria={"late_submission": "Work handed in late", "grade_appeal": "A disputed mark",
                       "plagiarism_flag": "A flagged similarity match", "extension_request": "A request for more time"},
             hierarchy={"deadlines": ["late_submission", "extension_request"],
                        "marks_and_integrity": ["grade_appeal", "plagiarism_flag"]}),
    Question("action", "choice", "What should the course office do?", _action,
             ("case", "documented", "days_late", "cites_rubric", "cited", "similarity", "extensions_before"),
             criteria={"accept": "Accept it: a documented reason (fewer than two earlier extensions), or matches "
                                 "that are properly cited",
                       "review": "Send it for review: an appeal that names a misapplied criterion, or an uncited "
                                 "match above 30%",
                       "penalise": "Apply a penalty: work up to 7 days late without a reason, or a small uncited "
                                   "match",
                       "refuse": "Refuse: work more than 7 days late without a reason, an appeal with no specific "
                                 "criterion, or an extension without a reason or after two earlier ones"},
             hierarchy={"student_favoured": ["accept", "review"], "student_disfavoured": ["penalise", "refuse"]}),
    Question("assessment_type", "choice", "What kind of assessment is it?", fact("assessment"), ("assessment",),
             criteria={"weekly quiz": "A weekly quiz", "essay": "An essay", "lab report": "A lab report",
                       "final exam": "The final exam"},
             hierarchy={"coursework": ["essay", "lab report"], "tests": ["weekly quiz", "final exam"]}),
    Question("stakes", "score", "How much is at stake for the student's mark?", _stakes,
             ("case", "documented", "days_late", "points_disputed", "cited", "similarity", "prior_case",
              "days_to_deadline"),
             criteria=["Nothing", "A little", "A lot", "A great deal"]),
)

DOMAIN = Domain(
    name="education_grading", title="Education and grading",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("student email to the course office", "learning platform case note", "marker's note",
            "course office chat message"),
)
