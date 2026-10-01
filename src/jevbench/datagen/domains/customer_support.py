"""Customer support: a customer writes to a software vendor's support team."""

from __future__ import annotations

from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known, mentioned

PRODUCTS = ("data export", "dashboard", "API", "mobile app", "billing portal")
TONES = ("calm", "frustrated", "angry")
PLANS = ("free", "pro", "business", "enterprise")
# shown through the writing, never named: an emotion word ("frustrating") reads as that tone
TONE_LABELS = {"calm": "polite and neutral: no complaint about the company; do not name any feeling",
               "frustrated": "clearly unhappy but civil: complaints about how long or how often, no insults and "
                             "no capitals; do not name the feeling",
               "angry": "hostile: insults or accusations of incompetence or dishonesty, and at least one "
                        "sentence in capital letters; do not name the feeling"}

FACTS = (
    Fact("issue", "cat", "what the customer is writing about: a feature that is failing (outage), a charge they "
         "dispute (billing_dispute), a how-to question (how_to), or wanting to cancel (cancellation)",
         values=("outage", "billing_dispute", "how_to", "cancellation"), always=True,
         topic="what the customer is writing about",
         labels={"outage": "a product feature has stopped working for them",
                 "billing_dispute": "they dispute a charge on their invoice",
                 "how_to": "they ask how to do something with the product; nothing is broken",
                 "cancellation": "they want to cancel their subscription"}),
    Fact("product_area", "cat", "which part of the product the message is about", values=PRODUCTS),
    Fact("failure_count", "int", "how many times the failing operation has failed", lo=1, hi=9,
         subject="failed attempts"),
    Fact("affected_users", "int", "how many of the customer's users are affected", lo=1, hi=500,
         subject="affected users"),
    Fact("workaround", "bool", "whether the customer has a temporary workaround that works", implied_ok=True),
    Fact("changed_config", "bool", "whether the customer changed their own settings or configuration shortly "
         "before the problem started"),
    Fact("disputed_amount", "int", "the amount of the disputed charge, in US dollars", lo=20, hi=3000,
         subject="dollars in dispute"),
    Fact("refund_requested", "bool", "whether the customer asks for a refund", speech_act=True),
    Fact("deadline", "cat", "the deadline the customer gives for a resolution",
         values=("today", "this week", "next month"), implied_ok=True, speech_act=True),
    Fact("tone", "cat", "the customer's emotional tone", values=TONES, implied_ok=True, never_absent=True,
         labels=TONE_LABELS),
    Fact("plan", "cat", "the customer's subscription plan", values=PLANS),
    Fact("seats", "int", "how many user seats the customer's account has", lo=1, hi=500, subject="user seats"),
    Fact("threatens_cancel", "bool", "whether the customer says they may cancel their subscription or switch to another "
         "provider", speech_act=True,
         absent_note="no threat, warning or hint of cancelling, leaving, switching, reconsidering the relationship "
                     "or taking further action"),
    Fact("mentions_competitor", "bool", "whether the customer mentions a competing product", speech_act=True,
         absent_note="no other product, vendor or alternative, not even a comparison"),
)


def _common(rng, **kw):
    # no deadline is a deadline the customer does not give: the value is then not mentioned
    f = {"product_area": rng.choice(PRODUCTS[:4]), "failure_count": None, "affected_users": None,
         "workaround": None, "changed_config": None, "disputed_amount": None,
         "refund_requested": rng.random() < 0.15, "deadline": rng.choice(("today", "this week", "next month")),
         "tone": rng.choice(TONES), "plan": rng.choice(PLANS), "seats": rng.choice((rng.randint(1, 9),
                                                                                      rng.randint(10, 99),
                                                                                      rng.randint(100, 500))),
         "threatens_cancel": rng.random() < 0.2, "mentions_competitor": rng.random() < 0.15}
    f.update(kw)
    return f


def _users(rng):
    return rng.choice((rng.randint(1, 9), rng.randint(10, 49), rng.randint(50, 500)))


def _outage(rng):
    f = _common(rng, issue="outage", failure_count=rng.randint(1, 9), workaround=rng.random() < 0.5,
                changed_config=rng.random() < 0.4)
    f["affected_users"] = min(_users(rng), f["seats"])  # users of the account: never more than its seats
    return f


ARCHETYPES = (
    Archetype("outage", "a product feature has stopped working for the customer",
              lambda rng: _outage(rng)),
    Archetype("billing_dispute", "the customer disputes a charge on their invoice",
              lambda rng: _common(rng, issue="billing_dispute", product_area=None,
                                  disputed_amount=rng.choice((rng.randint(20, 199), rng.randint(200, 999),
                                                              rng.randint(1000, 3000))),
                                  refund_requested=rng.random() < 0.7)),
    Archetype("how_to", "the customer asks how to do something with the product",
              lambda rng: _common(rng, issue="how_to", tone=rng.choice(("calm", "calm", "frustrated")),
                                  refund_requested=rng.random() < 0.05, threatens_cancel=rng.random() < 0.05,
                                  mentions_competitor=rng.random() < 0.25)),
    Archetype("cancellation", "the customer wants to cancel their subscription",
              lambda rng: _common(rng, issue="cancellation", threatens_cancel=True, product_area=None,
                                  refund_requested=rng.random() < 0.4, mentions_competitor=rng.random() < 0.5)),
)


def _said(f, m, name):
    """'Does the customer say X?': absent means no."""
    return bool(mentioned(m, name) and f.get(name))


def _urgency(f, m):
    if f["issue"] == "outage":
        users, workaround = known(f, m, "affected_users"), known(f, m, "workaround")
        if UNKNOWN in (users, workaround):
            return UNKNOWN
        return "critical" if users >= 50 and not workaround else "high"
    deadline = f["deadline"] if mentioned(m, "deadline") else None   # not given = no deadline
    if deadline in ("today", "this week"):
        return "high"
    if f["issue"] in ("billing_dispute", "cancellation"):
        return "medium"
    return "low"


def _churn(f, m):
    if f["issue"] == "cancellation":
        return 3
    if _said(f, m, "threatens_cancel") or _said(f, m, "mentions_competitor"):
        return 2
    tone = known(f, m, "tone")
    if tone == UNKNOWN:
        return UNKNOWN
    return 1 if tone in ("frustrated", "angry") else 0


QUESTIONS = (
    Question("feature_failing", "noul", "Is a product feature currently failing for this customer?",
             lambda f, m: f["issue"] == "outage", ("issue",)),
    Question("deadline_given", "noul", "Does the customer give a deadline for a resolution?",
             lambda f, m: mentioned(m, "deadline"), ("deadline",)),
    Question("refund_asked", "noul", "Does the customer ask for a refund?",
             lambda f, m: _said(f, m, "refund_requested"), ("refund_requested",)),
    Question("config_changed", "noul", "Did the customer change their own configuration shortly before the "
             "problem started?", lambda f, m: known(f, m, "changed_config"), ("changed_config",),
             applies=lambda f: f["issue"] == "outage"),
    Question("workaround_works", "noul", "Does the customer have a temporary workaround that works?",
             lambda f, m: known(f, m, "workaround"), ("workaround",), applies=lambda f: f["issue"] == "outage"),
    Question("may_leave", "noul", "Does the customer say they may cancel or leave?",
             lambda f, m: _said(f, m, "threatens_cancel"), ("threatens_cancel",)),
    Question("competitor_named", "noul", "Does the customer mention a competing product?",
             lambda f, m: _said(f, m, "mentions_competitor"), ("mentions_competitor",)),
    Question("large_account", "noul", "Does the account have more than 50 user seats?",
             lambda f, m: (lambda n: UNKNOWN if n == UNKNOWN else n > 50)(known(f, m, "seats")), ("seats",)),
    Question("enterprise_plan", "noul", "Is the customer on the enterprise plan?",
             lambda f, m: (lambda p: UNKNOWN if p == UNKNOWN else p == "enterprise")(known(f, m, "plan")), ("plan",)),
    Question("customer_upset", "noul", "Does the customer sound unhappy with the company?",
             lambda f, m: (lambda t: UNKNOWN if t == UNKNOWN else t != "calm")(known(f, m, "tone")), ("tone",)),
    Question("primary_team", "choice", "Which team should own this request?",
             lambda f, m: {"outage": "engineering", "billing_dispute": "billing", "how_to": "success",
                           "cancellation": "retention"}[f["issue"]], ("issue",),
             criteria={"engineering": "Fixes broken product functionality",
                       "billing": "Handles charges, invoices and refunds",
                       "success": "Answers how-to questions and helps with setup",
                       "retention": "Handles cancellations and tries to keep the customer"},
             hierarchy={"product_teams": ["engineering", "success"], "account_teams": ["billing", "retention"]}),
    Question("urgency", "choice", "How urgent is this request?", _urgency,
             ("issue", "affected_users", "workaround", "deadline"),
             criteria={"low": "Can wait more than a week",
                       "medium": "Should be handled within a few days",
                       "high": "Blocks work or has a deadline within the week",
                       "critical": "Many users are blocked right now with no workaround"},
             hierarchy={"routine": ["low", "medium"], "pressing": ["high", "critical"]}),
    Question("plan_tier", "choice", "Which subscription plan is the customer on?",
             lambda f, m: known(f, m, "plan"), ("plan",),
             criteria={"free": "The free plan", "pro": "The paid pro plan", "business": "The business plan",
                       "enterprise": "The enterprise plan"},
             hierarchy={"self_serve": ["free", "pro"], "sales_led": ["business", "enterprise"]}),
    Question("churn_risk", "score", "How likely is this customer to leave?", _churn,
             ("issue", "threatens_cancel", "mentions_competitor", "tone"),
             criteria=["No sign of leaving", "Some dissatisfaction", "Considering leaving",
                       "Has decided to cancel"]),
)

DOMAIN = Domain(
    name="customer_support", title="Customer support",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("customer email", "live chat transcript", "support ticket form", "short mobile message"),
)
