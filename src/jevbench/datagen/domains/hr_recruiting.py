"""HR and recruiting: a hiring or staffing item reaches a company's HR team.

Only job-related facts are used; no protected characteristic appears in any fact or rule.
"""

from __future__ import annotations

from jevbench.datagen.domains._rules import fact, kind_is, said, test
from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known

FACTS = (
    Fact("stage", "cat", "what HR is asked to handle: a new job application (application), feedback from a "
         "four-person interview panel (interview_feedback), a candidate answering a job offer with a higher salary "
         "request (offer_counter), or an employee asking to move to another team (internal_transfer)",
         values=("application", "interview_feedback", "offer_counter", "internal_transfer"), always=True,
         topic="what HR is asked to handle",
         labels={"application": "a new job application",
                 "interview_feedback": "feedback from a four-person interview panel",
                 "offer_counter": "a candidate asks for a higher salary than the offer",
                 "internal_transfer": "an employee asks to move to another team"}),
    Fact("years_experience", "int", "how many years of relevant experience the person has", lo=0, hi=30,
         subject="years of relevant experience"),
    Fact("has_skill", "bool", "whether the person has the skill the job requires"),
    Fact("referred", "bool", "whether an employee referred the candidate", implied_ok=True),
    Fact("recommend", "int", "how many of the four interviewers recommend hiring", lo=0, hi=4,
         subject="interviewers who recommend hiring"),
    Fact("concern", "bool", "whether any interviewer reports a concern about honesty or conduct"),
    Fact("asked_k", "int", "the salary the candidate asks for, in thousands of dollars a year", lo=30, hi=300,
         subject="thousand dollars asked"),
    Fact("budget_k", "int", "the most the hiring budget allows, in thousands of dollars a year", lo=30, hi=300,
         subject="thousand dollars of budget"),
    Fact("rival_offer", "bool", "whether the candidate says they have another offer", speech_act=True),
    Fact("notice_weeks", "int", "how many weeks of notice the person must give before starting", lo=0, hi=12,
         subject="weeks of notice"),
    Fact("manager_supports", "bool", "whether the employee's current manager supports the move"),
    Fact("months_in_role", "int", "how many months the employee has been in their current role", lo=1, hi=60,
         subject="months in the current role"),
)


def _base(rng, **kw):
    f = {"years_experience": rng.choice((rng.randint(0, 3), rng.randint(4, 7), rng.randint(8, 30))),
         "has_skill": None, "referred": None, "recommend": None, "concern": None, "asked_k": None,
         "budget_k": None, "rival_offer": None, "notice_weeks": rng.choice((0, rng.randint(1, 4), rng.randint(5, 12))),
         "manager_supports": None, "months_in_role": None}
    f.update(kw)
    return f


def _offer(rng):
    budget = rng.randint(50, 250)
    asked = budget + rng.choice((-rng.randint(1, 10), rng.randint(1, 40)))
    return _base(rng, stage="offer_counter", budget_k=budget, asked_k=max(30, min(300, asked)),
                 rival_offer=rng.random() < 0.5)


ARCHETYPES = (
    Archetype("application", "a candidate applies for an open job",
              lambda rng: _base(rng, stage="application", has_skill=rng.random() < 0.6,
                                referred=rng.random() < 0.3)),
    Archetype("interview_feedback", "a four-person panel reports on a candidate's interview",
              lambda rng: _base(rng, stage="interview_feedback", notice_weeks=None, recommend=rng.randint(0, 4),
                                concern=rng.random() < 0.25)),
    Archetype("offer_counter", "a candidate answers a job offer by asking for a higher salary", _offer),
    Archetype("internal_transfer", "an employee asks to move to another team",
              lambda rng: _base(rng, stage="internal_transfer", has_skill=rng.random() < 0.7,
                                manager_supports=rng.random() < 0.6,
                                months_in_role=rng.choice((rng.randint(1, 11), rng.randint(12, 60))))),
)


def _over_budget(f, m):
    asked, budget = known(f, m, "asked_k"), known(f, m, "budget_k")
    return UNKNOWN if UNKNOWN in (asked, budget) else asked > budget


def _decision(f, m):
    stage = f["stage"]
    if stage == "application":
        skill = known(f, m, "has_skill")
        return UNKNOWN if skill == UNKNOWN else ("proceed" if skill else "decline")
    if stage == "interview_feedback":
        if known(f, m, "concern") is True:
            return "decline"
        votes, concern = known(f, m, "recommend"), known(f, m, "concern")
        if UNKNOWN in (votes, concern):
            return UNKNOWN
        return "proceed" if votes >= 3 else "hold" if votes == 2 else "decline"
    if stage == "offer_counter":
        over = _over_budget(f, m)
        if over == UNKNOWN:
            return UNKNOWN
        return "escalate" if over and said(f, m, "rival_offer") else "hold" if over else "proceed"
    months = known(f, m, "months_in_role")
    if months != UNKNOWN and months < 12:
        return "decline"
    backs = known(f, m, "manager_supports")
    if UNKNOWN in (months, backs):
        return UNKNOWN
    return "proceed" if backs else "escalate"


def _strength(f, m):
    stage = f["stage"]
    if stage == "interview_feedback":
        votes, concern = known(f, m, "recommend"), known(f, m, "concern")
        if concern is True:
            return 0
        return UNKNOWN if UNKNOWN in (votes, concern) else (0, 0, 1, 2, 3)[votes]
    if stage == "offer_counter":
        over = _over_budget(f, m)
        return UNKNOWN if over == UNKNOWN else (3 if not over else 2 if said(f, m, "rival_offer") else 1)
    senior, skill = known(f, m, "years_experience"), known(f, m, "has_skill")
    third = known(f, m, "referred") if stage == "application" else test("months_in_role", lambda n: n >= 12)(f, m)
    if UNKNOWN in (senior, skill, third):
        return UNKNOWN
    return int(senior >= 8) + int(skill) + int(third)


QUESTIONS = (
    Question("skill_match", "noul", "Does the person have the skill the job requires?", fact("has_skill"),
             ("has_skill",), applies=kind_is("stage", "application", "internal_transfer")),
    Question("senior", "noul", "Does the person have 8 or more years of relevant experience?",
             test("years_experience", lambda n: n >= 8), ("years_experience",)),
    Question("long_notice", "noul", "Must the person give more than 4 weeks of notice?",
             test("notice_weeks", lambda n: n > 4), ("notice_weeks",),
             applies=kind_is("stage", "application", "offer_counter", "internal_transfer")),
    Question("can_start_now", "noul", "Can the person start without a notice period?",
             test("notice_weeks", lambda n: n == 0), ("notice_weeks",),
             applies=kind_is("stage", "application", "offer_counter", "internal_transfer")),
    Question("some_support", "noul", "Does at least one interviewer recommend hiring?",
             test("recommend", lambda n: n >= 1), ("recommend",), applies=kind_is("stage", "interview_feedback")),
    Question("referred", "noul", "Was the candidate referred by an employee?", fact("referred"), ("referred",),
             applies=kind_is("stage", "application")),
    Question("panel_majority", "noul", "Do at least three of the four interviewers recommend hiring?",
             test("recommend", lambda n: n >= 3), ("recommend",), applies=kind_is("stage", "interview_feedback")),
    Question("panel_unanimous", "noul", "Do all four interviewers recommend hiring?",
             test("recommend", lambda n: n == 4), ("recommend",), applies=kind_is("stage", "interview_feedback")),
    Question("concern_raised", "noul", "Did any interviewer report a concern about honesty or conduct?",
             fact("concern"), ("concern",), applies=kind_is("stage", "interview_feedback")),
    Question("over_budget", "noul", "Is the requested salary above the budget?", _over_budget,
             ("asked_k", "budget_k"), applies=kind_is("stage", "offer_counter")),
    Question("other_offer", "noul", "Does the candidate say they have another offer?",
             lambda f, m: said(f, m, "rival_offer"), ("rival_offer",), applies=kind_is("stage", "offer_counter")),
    Question("manager_backs", "noul", "Does the employee's current manager support the move?",
             fact("manager_supports"), ("manager_supports",), applies=kind_is("stage", "internal_transfer")),
    Question("year_in_role", "noul", "Has the employee been in their current role for at least 12 months?",
             test("months_in_role", lambda n: n >= 12), ("months_in_role",),
             applies=kind_is("stage", "internal_transfer")),
    Question("item_type", "choice", "What is HR asked to handle?", lambda f, m: f["stage"], ("stage",),
             criteria={"application": "A new job application",
                       "interview_feedback": "Feedback from an interview panel",
                       "offer_counter": "A candidate asking for more than the offer",
                       "internal_transfer": "An employee asking to change teams"},
             hierarchy={"candidates": ["application", "interview_feedback"],
                        "decisions_on_terms": ["offer_counter", "internal_transfer"]}),
    Question("decision", "choice", "What should HR do?", _decision,
             ("stage", "has_skill", "recommend", "concern", "asked_k", "budget_k", "rival_offer", "months_in_role",
              "manager_supports"),
             criteria={"proceed": "Move forward: the required skill, a panel majority, a request within budget, "
                                  "or a supported transfer after a year in the role",
                       "hold": "Pause: a split panel, or a request above budget with no other offer",
                       "decline": "Say no: the required skill is missing, a conduct concern or a weak panel, or "
                                  "less than a year in the role",
                       "escalate": "Ask a senior manager to decide: above budget with another offer, or a "
                                   "transfer the current manager does not support"},
             hierarchy={"moves_forward": ["proceed", "escalate"], "does_not_move": ["hold", "decline"]}),
    Question("case_strength", "score", "How strong is the case for moving forward?", _strength,
             ("stage", "years_experience", "has_skill", "referred", "months_in_role", "recommend", "concern",
              "asked_k", "budget_k", "rival_offer"),
             criteria=["Weak", "Mixed", "Good", "Strong"]),
)

DOMAIN = Domain(
    name="hr_recruiting", title="HR and recruiting",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("applicant tracking system note", "email to the HR team", "hiring manager message", "HR case summary"),
)
