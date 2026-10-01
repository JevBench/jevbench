"""Logistics: a shipment exception reaches a freight company's operations desk."""

from __future__ import annotations

from jevbench.datagen.domains._rules import fact, kind_is, test
from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known

MODES = ("road", "rail", "air", "sea")

FACTS = (
    Fact("exception", "cat", "what went wrong with the shipment: it is running late (delayed), goods were damaged "
         "on the way (damaged), customs is holding it (customs_hold), or it could not be delivered to the address "
         "(address_issue)",
         values=("delayed", "damaged", "customs_hold", "address_issue"), always=True,
         topic="what went wrong with the shipment",
         labels={"delayed": "the shipment is running late", "damaged": "goods were damaged on the way",
                 "customs_hold": "customs is holding the shipment",
                 "address_issue": "the shipment could not be delivered to the address"}),
    Fact("mode", "cat", "how the shipment travels", values=MODES, implied_ok=True),
    Fact("units", "int", "how many units are in the shipment", lo=1, hi=5000, subject="units in the shipment"),
    Fact("days_late", "int", "how many days late the shipment is", lo=0, hi=30, subject="days of delay"),
    Fact("refrigerated", "bool", "whether the goods must be kept refrigerated"),
    Fact("insured", "bool", "whether the shipment is insured", implied_ok=True),
    Fact("damaged_pct", "int", "what percentage of the units were damaged", lo=1, hi=100,
         subject="percent of units damaged"),
    Fact("docs_missing", "bool", "whether paperwork customs needs is missing"),
    Fact("duties_paid", "bool", "whether the import duties have been paid"),
    Fact("attempts", "int", "how many delivery attempts have been made", lo=1, hi=3, subject="delivery attempts"),
    Fact("recipient_reached", "bool", "whether the recipient has been reached by phone or email"),
    Fact("key_account", "bool", "whether the customer is one of the company's key accounts", implied_ok=True),
)


def _base(rng, **kw):
    f = {"mode": rng.choice(MODES), "units": rng.choice((rng.randint(1, 99), rng.randint(100, 999),
                                                         rng.randint(1000, 5000))),
         "days_late": None, "refrigerated": None, "insured": None, "damaged_pct": None, "docs_missing": None,
         "duties_paid": None, "attempts": None, "recipient_reached": None, "key_account": rng.random() < 0.3}
    f.update(kw)
    return f


def _late(rng):
    return rng.choice((rng.randint(0, 3), rng.randint(4, 7), rng.randint(8, 30)))


ARCHETYPES = (
    Archetype("delayed", "a shipment is running behind schedule",
              lambda rng: _base(rng, exception="delayed", days_late=max(1, _late(rng)),
                                refrigerated=rng.random() < 0.3)),
    Archetype("damaged", "goods in a shipment were damaged on the way",
              lambda rng: _base(rng, exception="damaged", refrigerated=rng.random() < 0.3,
                                insured=rng.random() < 0.5,
                                damaged_pct=rng.choice((rng.randint(1, 50), rng.randint(51, 100))))),
    Archetype("customs_hold", "customs is holding a shipment at the border",
              lambda rng: _base(rng, exception="customs_hold", mode=rng.choice(("road", "air", "sea")),
                                days_late=_late(rng), docs_missing=rng.random() < 0.5,
                                duties_paid=rng.random() < 0.5)),
    Archetype("address_issue", "a shipment could not be delivered to the address",
              lambda rng: _base(rng, exception="address_issue", mode="road", attempts=rng.randint(1, 3),
                                recipient_reached=rng.random() < 0.5)),
)


def _action(f, m):
    kind = f["exception"]
    if kind == "delayed":
        cold, late = known(f, m, "refrigerated"), known(f, m, "days_late")
        if cold is False or (late != UNKNOWN and late <= 3):
            return "wait"
        return UNKNOWN if UNKNOWN in (cold, late) else "reship"
    if kind == "damaged":
        insured = known(f, m, "insured")
        if insured is True:
            return "file_claim"
        pct = known(f, m, "damaged_pct")
        if UNKNOWN in (insured, pct):
            return UNKNOWN
        return "reship" if pct > 50 else "contact_recipient"
    if kind == "customs_hold":
        docs, duties = known(f, m, "docs_missing"), known(f, m, "duties_paid")
        if docs is True or duties is False:
            return "contact_recipient"
        return UNKNOWN if UNKNOWN in (docs, duties) else "wait"
    reached = known(f, m, "recipient_reached")
    return UNKNOWN if reached == UNKNOWN else ("wait" if reached else "contact_recipient")


def _severity(f, m):
    kind = f["exception"]
    if kind == "address_issue":
        n = known(f, m, "attempts")
        return UNKNOWN if n == UNKNOWN else (2 if n >= 3 else 1)
    if kind == "customs_hold":
        late = known(f, m, "days_late")
        return UNKNOWN if late == UNKNOWN else 1 + int(late > 7)
    cold = known(f, m, "refrigerated")
    if kind == "delayed":
        late = known(f, m, "days_late")
        if UNKNOWN in (cold, late):
            return UNKNOWN
        return min(3, (2 if late > 7 else 1 if late > 3 else 0) + int(cold))
    pct = known(f, m, "damaged_pct")
    return UNKNOWN if UNKNOWN in (cold, pct) else (2 if pct > 50 else 1) + int(cold)


QUESTIONS = (
    Question("over_three_days", "noul", "Is the shipment more than 3 days late?", test("days_late", lambda d: d > 3),
             ("days_late",), applies=kind_is("exception", "delayed", "customs_hold")),
    Question("cold_chain", "noul", "Must the goods be kept refrigerated?", fact("refrigerated"), ("refrigerated",),
             applies=kind_is("exception", "delayed", "damaged")),
    Question("insured", "noul", "Is the shipment insured?", fact("insured"), ("insured",),
             applies=kind_is("exception", "damaged")),
    Question("mostly_damaged", "noul", "Were more than half of the units damaged?",
             test("damaged_pct", lambda p: p > 50), ("damaged_pct",), applies=kind_is("exception", "damaged")),
    Question("paperwork_missing", "noul", "Is paperwork that customs needs missing?", fact("docs_missing"),
             ("docs_missing",), applies=kind_is("exception", "customs_hold")),
    Question("duties_settled", "noul", "Have the import duties been paid?", fact("duties_paid"), ("duties_paid",),
             applies=kind_is("exception", "customs_hold")),
    Question("recipient_contacted", "noul", "Has the recipient been reached?", fact("recipient_reached"),
             ("recipient_reached",), applies=kind_is("exception", "address_issue")),
    Question("repeated_attempts", "noul", "Has delivery been attempted more than once?",
             test("attempts", lambda n: n > 1), ("attempts",), applies=kind_is("exception", "address_issue")),
    Question("large_shipment", "noul", "Does the shipment have more than 1,000 units?",
             test("units", lambda n: n > 1000), ("units",)),
    Question("key_account", "noul", "Is the customer a key account?", fact("key_account"), ("key_account",)),
    Question("exception_type", "choice", "What went wrong with the shipment?", lambda f, m: f["exception"],
             ("exception",),
             criteria={"delayed": "It is running late", "damaged": "Goods were damaged on the way",
                       "customs_hold": "Customs is holding it", "address_issue": "It could not be delivered"},
             hierarchy={"in_transit": ["delayed", "damaged"], "at_destination": ["customs_hold", "address_issue"]}),
    Question("action", "choice", "What should the operations desk do?", _action,
             ("exception", "refrigerated", "days_late", "insured", "damaged_pct", "docs_missing", "duties_paid",
              "recipient_reached"),
             criteria={"wait": "Let it continue: a short or non-refrigerated delay, customs cleared, or a new "
                               "delivery agreed with the recipient",
                       "contact_recipient": "Contact the recipient: for missing paperwork or duties, a new delivery "
                                            "time, or to accept minor uninsured damage",
                       "reship": "Send the goods again: refrigerated goods more than 3 days late, or most of an "
                                 "uninsured shipment damaged",
                       "file_claim": "File an insurance claim for the damage"},
             hierarchy={"no_new_cost": ["wait", "contact_recipient"], "costly": ["reship", "file_claim"]}),
    Question("transport_mode", "choice", "How does the shipment travel?", fact("mode"), ("mode",),
             criteria={"road": "By truck", "rail": "By train", "air": "By air", "sea": "By sea"},
             hierarchy={"overland": ["road", "rail"], "long_haul": ["air", "sea"]}),
    Question("severity", "score", "How serious is this exception?", _severity,
             ("exception", "attempts", "days_late", "refrigerated", "damaged_pct"),
             criteria=["Minor", "Moderate", "Serious", "Critical"]),
)

DOMAIN = Domain(
    name="logistics", title="Logistics",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("shipment exception report", "driver or agent note", "email from the customer", "operations chat message"),
)
