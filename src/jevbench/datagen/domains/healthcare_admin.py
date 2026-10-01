"""Healthcare administration: a non-clinical request reaches a clinic's front office.

Scheduling, insurance, records and billing only; no fact or rule is a clinical judgement.
"""

from __future__ import annotations

from jevbench.datagen.domains._rules import fact, kind_is, said, test
from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known

REQUESTERS = ("patient", "family member", "another clinic", "law firm")

FACTS = (
    Fact("request", "cat", "what the front office is asked to handle: booking an appointment "
         "(appointment_request), an insurance claim the insurer turned down (claim_denied), a request for copies "
         "of medical records (records_request), or a question about a bill (billing_question)",
         values=("appointment_request", "claim_denied", "records_request", "billing_question"), always=True,
         topic="what the front office is asked to handle",
         labels={"appointment_request": "someone wants to book an appointment",
                 "claim_denied": "the insurer turned down an insurance claim",
                 "records_request": "someone asks for copies of medical records",
                 "billing_question": "a patient asks about a bill"}),
    Fact("days_until_needed", "int", "within how many days the patient needs the appointment", lo=0, hi=60,
         subject="days until the appointment is needed"),
    Fact("new_patient", "bool", "whether the patient has never been seen at the clinic before", implied_ok=True),
    Fact("referral", "bool", "whether a referral from the patient's doctor is on file"),
    Fact("insured", "bool", "whether the patient has health insurance", implied_ok=True),
    Fact("amount", "int", "the amount of money involved, in US dollars", lo=20, hi=20000, subject="dollars"),
    Fact("prior_auth", "bool", "whether prior authorization from the insurer was obtained before the visit"),
    Fact("missing_info", "bool", "whether the denial says information was missing from the claim"),
    Fact("days_since_denial", "int", "how many days ago the claim was denied", lo=0, hi=180,
         subject="days since the denial"),
    Fact("requester", "cat", "who is asking for the records", values=REQUESTERS),
    Fact("identity_verified", "bool", "whether the requester's identity has been verified"),
    Fact("signed_consent", "bool", "whether a consent form signed by the patient is attached"),
    Fact("days_since_request", "int", "how many days ago the records were requested", lo=0, hi=30,
         subject="days since the request"),
    Fact("months_overdue", "int", "how many months the bill is overdue", lo=0, hi=12, subject="months overdue"),
    Fact("wants_plan", "bool", "whether the patient asks to pay in instalments", speech_act=True),
)


def _base(rng, **kw):
    f = {k: None for k in ("days_until_needed", "new_patient", "referral", "insured", "amount", "prior_auth",
                           "missing_info", "days_since_denial", "requester", "identity_verified", "signed_consent",
                           "days_since_request", "months_overdue", "wants_plan")}
    f.update(kw)
    return f


def _money(rng):
    return rng.choice((rng.randint(20, 999), rng.randint(1000, 20000)))


ARCHETYPES = (
    Archetype("appointment_request", "someone calls to book an appointment at a specialist clinic",
              lambda rng: _base(rng, request="appointment_request",
                                days_until_needed=rng.choice((rng.randint(0, 2), rng.randint(3, 7),
                                                              rng.randint(8, 60))),
                                new_patient=rng.random() < 0.5, referral=rng.random() < 0.5,
                                insured=rng.random() < 0.7)),
    Archetype("claim_denied", "the insurer has turned down a claim for a visit",
              lambda rng: _base(rng, request="claim_denied", amount=_money(rng), prior_auth=rng.random() < 0.5,
                                missing_info=rng.random() < 0.5,
                                days_since_denial=rng.choice((rng.randint(0, 30), rng.randint(31, 90),
                                                              rng.randint(91, 180))))),
    Archetype("records_request", "someone asks for copies of a patient's medical records",
              lambda rng: _base(rng, request="records_request", requester=rng.choice(REQUESTERS),
                                identity_verified=rng.random() < 0.6, signed_consent=rng.random() < 0.5,
                                days_since_request=rng.randint(0, 30))),
    Archetype("billing_question", "a patient asks about a bill",
              lambda rng: _base(rng, request="billing_question", amount=_money(rng), insured=rng.random() < 0.6,
                                months_overdue=rng.choice((0, rng.randint(1, 2), rng.randint(3, 12))),
                                wants_plan=rng.random() < 0.5)),
)


def _action(f, m):
    kind = f["request"]
    if kind == "appointment_request":
        new, ref = known(f, m, "new_patient"), known(f, m, "referral")
        if new is False or ref is True:
            return "proceed"
        return UNKNOWN if UNKNOWN in (new, ref) else "ask_for_documents"
    if kind == "claim_denied":
        days = known(f, m, "days_since_denial")
        if days == UNKNOWN:
            return UNKNOWN
        if days > 90:
            return "refuse"
        missing = known(f, m, "missing_info")
        if missing == UNKNOWN:
            return UNKNOWN
        return "ask_for_documents" if missing else "escalate"
    if kind == "records_request":
        who = known(f, m, "requester")
        if who == UNKNOWN:
            return UNKNOWN
        check = known(f, m, "identity_verified" if who == "patient" else "signed_consent")
        if check == UNKNOWN:
            return UNKNOWN
        return "proceed" if check else ("ask_for_documents" if who == "patient" else "refuse")
    overdue = known(f, m, "months_overdue")
    if overdue == UNKNOWN:
        return UNKNOWN
    return "escalate" if overdue >= 3 and not said(f, m, "wants_plan") else "proceed"


def _priority(f, m):
    kind = f["request"]
    if kind == "appointment_request":
        d = known(f, m, "days_until_needed")
        return UNKNOWN if d == UNKNOWN else (3 if d <= 2 else 2 if d <= 7 else 1 if d <= 30 else 0)
    if kind == "claim_denied":
        d = known(f, m, "days_since_denial")  # appeals close 90 days after the denial
        return UNKNOWN if d == UNKNOWN else (0 if d > 90 else 3 if d > 60 else 2 if d > 30 else 1)
    if kind == "records_request":
        d = known(f, m, "days_since_request")  # records are due within 30 days of the request
        return UNKNOWN if d == UNKNOWN else (3 if d >= 25 else 2 if d >= 14 else 1)
    d = known(f, m, "months_overdue")
    return UNKNOWN if d == UNKNOWN else (3 if d >= 6 else 2 if d >= 3 else 1 if d >= 1 else 0)


QUESTIONS = (
    Question("needed_soon", "noul", "Does the patient need the appointment within 2 days?",
             test("days_until_needed", lambda d: d <= 2), ("days_until_needed",),
             applies=kind_is("request", "appointment_request")),
    Question("needed_this_week", "noul", "Does the patient need the appointment within 7 days?",
             test("days_until_needed", lambda d: d <= 7), ("days_until_needed",),
             applies=kind_is("request", "appointment_request")),
    Question("new_patient", "noul", "Is this a new patient?", fact("new_patient"), ("new_patient",),
             applies=kind_is("request", "appointment_request")),
    Question("referral_on_file", "noul", "Is a referral from the patient's doctor on file?", fact("referral"),
             ("referral",), applies=kind_is("request", "appointment_request")),
    Question("has_insurance", "noul", "Does the patient have health insurance?", fact("insured"), ("insured",),
             applies=kind_is("request", "appointment_request", "billing_question")),
    Question("large_amount", "noul", "Is more than $1,000 involved?", test("amount", lambda a: a > 1000), ("amount",),
             applies=kind_is("request", "claim_denied", "billing_question")),
    Question("authorized", "noul", "Was prior authorization obtained before the visit?", fact("prior_auth"),
             ("prior_auth",), applies=kind_is("request", "claim_denied")),
    Question("info_missing", "noul", "Does the denial say information was missing from the claim?",
             fact("missing_info"), ("missing_info",), applies=kind_is("request", "claim_denied")),
    Question("can_appeal", "noul", "Was the claim denied 90 days ago or less?",
             test("days_since_denial", lambda d: d <= 90), ("days_since_denial",),
             applies=kind_is("request", "claim_denied")),
    Question("recent_denial", "noul", "Was the claim denied within the last 30 days?",
             test("days_since_denial", lambda d: d <= 30), ("days_since_denial",),
             applies=kind_is("request", "claim_denied")),
    Question("identity_checked", "noul", "Has the requester's identity been verified?", fact("identity_verified"),
             ("identity_verified",), applies=kind_is("request", "records_request")),
    Question("consent_attached", "noul", "Is a consent form signed by the patient attached?",
             fact("signed_consent"), ("signed_consent",), applies=kind_is("request", "records_request")),
    Question("third_party", "noul", "Is someone other than the patient or their family asking?",
             test("requester", lambda r: r in ("another clinic", "law firm")), ("requester",),
             applies=kind_is("request", "records_request")),
    Question("request_aging", "noul", "Were the records requested two weeks ago or more?",
             test("days_since_request", lambda d: d >= 14), ("days_since_request",),
             applies=kind_is("request", "records_request")),
    Question("overdue", "noul", "Is the bill 3 or more months overdue?", test("months_overdue", lambda n: n >= 3),
             ("months_overdue",), applies=kind_is("request", "billing_question")),
    Question("any_overdue", "noul", "Is the bill overdue at all?", test("months_overdue", lambda n: n >= 1),
             ("months_overdue",), applies=kind_is("request", "billing_question")),
    Question("instalments_asked", "noul", "Does the patient ask to pay in instalments?",
             lambda f, m: said(f, m, "wants_plan"), ("wants_plan",), applies=kind_is("request", "billing_question")),
    Question("request_type", "choice", "What is the front office asked to handle?", lambda f, m: f["request"],
             ("request",),
             criteria={"appointment_request": "Book an appointment", "claim_denied": "A denied insurance claim",
                       "records_request": "Copies of medical records", "billing_question": "A question about a bill"},
             hierarchy={"patient_services": ["appointment_request", "records_request"],
                        "money": ["claim_denied", "billing_question"]}),
    Question("action", "choice", "What should the front office do?", _action,
             ("request", "new_patient", "referral", "days_since_denial", "missing_info", "requester",
              "identity_verified", "signed_consent", "months_overdue", "wants_plan"),
             criteria={"proceed": "Go ahead: book it, release the records, or set up the payment as asked",
                       "ask_for_documents": "Ask for what is missing: a referral for a new patient, the missing "
                                            "claim information, or the patient's proof of identity",
                       "refuse": "Say no: the 90-day appeal window has closed, or a third party has no signed "
                                 "consent",
                       "escalate": "Pass it to a supervisor: appeal a claim with nothing missing, or review a "
                                   "bill 3 or more months overdue with no payment plan"},
             hierarchy={"front_desk_can_act": ["proceed", "ask_for_documents"], "no_or_supervisor": ["refuse", "escalate"]}),
    Question("requester_type", "choice", "Who is asking for the records?", fact("requester"), ("requester",),
             criteria={"patient": "The patient", "family member": "A family member",
                       "another clinic": "Another clinic", "law firm": "A law firm"},
             hierarchy={"patient_side": ["patient", "family member"], "third_party": ["another clinic", "law firm"]},
             applies=kind_is("request", "records_request")),
    Question("priority", "score", "How time-sensitive is this request?", _priority,
             ("request", "days_until_needed", "days_since_denial", "days_since_request", "months_overdue"),
             criteria=["Not time-sensitive", "Normal", "Soon", "Urgent"]),
)

DOMAIN = Domain(
    name="healthcare_admin", title="Healthcare administration",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("front desk call note", "patient portal message", "billing office email", "insurance correspondence summary"),
)
