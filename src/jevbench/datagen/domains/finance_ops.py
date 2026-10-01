"""Finance operations: a payment, invoice or expense item reaches a company's finance team."""

from __future__ import annotations

from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known, mentioned

CATEGORIES = ("travel", "meals", "software", "equipment")
CHANNELS = ("email", "phone call", "supplier portal")

FACTS = (
    Fact("request", "cat", "what the finance team is asked to handle: a supplier invoice waiting for approval "
         "(invoice_approval), an employee's expense claim (expense_claim), a supplier asking to change the bank "
         "account it is paid into (bank_detail_change), or two payments to the same supplier flagged in a payment "
         "run (possible_duplicate)",
         values=("invoice_approval", "expense_claim", "bank_detail_change", "possible_duplicate"), always=True,
         topic="what the finance team is asked to handle",
         labels={"invoice_approval": "a supplier invoice is waiting for approval",
                 "expense_claim": "an employee submits an expense claim",
                 "bank_detail_change": "a supplier asks to change the bank account it is paid into",
                 "possible_duplicate": "the payment run flags two payments to the same supplier"}),
    Fact("amount", "int", "the amount of money involved, in US dollars", lo=10, hi=250000, subject="dollars"),
    Fact("matches_po", "bool", "whether the invoice matches its purchase order"),
    Fact("goods_received", "bool", "whether the goods or services on the invoice have been received",
         implied_ok=True),
    Fact("new_vendor", "bool", "whether this is the first invoice from this supplier", implied_ok=True),
    Fact("has_receipt", "bool", "whether the expense claim has a receipt attached"),
    Fact("days_since_expense", "int", "how many days after the expense the claim was submitted", lo=0, hi=120,
         subject="days between the expense and the claim"),
    Fact("category", "cat", "what the expense was for", values=CATEGORIES, implied_ok=True),
    Fact("callback_verified", "bool", "whether someone confirmed the bank change by calling the supplier on a phone "
         "number already on file"),
    Fact("channel", "cat", "how the bank change request arrived", values=CHANNELS, implied_ok=True),
    Fact("pressure", "bool", "whether the requester insists it is urgent or asks to skip the usual checks",
         speech_act=True),
    Fact("same_invoice_number", "bool", "whether the two flagged payments carry the same invoice number"),
    Fact("days_apart", "int", "how many days apart the two flagged payments are scheduled", lo=0, hi=60,
         subject="days between the two payments"),
    Fact("due_in_days", "int", "in how many days the payment is due", lo=0, hi=60,
         subject="days until the payment is due"),
)


def _base(rng, **kw):
    f = {"matches_po": None, "goods_received": None, "new_vendor": None, "has_receipt": None, "days_since_expense": None,
         "category": None,
         "callback_verified": None, "channel": None, "pressure": rng.random() < 0.2, "same_invoice_number": None,
         "days_apart": None, "due_in_days": rng.choice((rng.randint(0, 2), rng.randint(3, 7), rng.randint(8, 60)))}
    f.update(kw)
    return f


def _large(rng):
    return rng.choice((rng.randint(200, 9999), rng.randint(10000, 250000)))


ARCHETYPES = (
    Archetype("invoice_approval", "a supplier invoice is waiting for approval",
              lambda rng: _base(rng, request="invoice_approval", amount=_large(rng), matches_po=rng.random() < 0.6,
                                goods_received=rng.random() < 0.7, new_vendor=rng.random() < 0.3)),
    Archetype("expense_claim", "an employee submits an expense claim",
              lambda rng: _base(rng, request="expense_claim", due_in_days=None,
                                amount=rng.choice((rng.randint(10, 999), rng.randint(1000, 5000))),
                                has_receipt=rng.random() < 0.6, category=rng.choice(CATEGORIES),
                                days_since_expense=rng.choice((rng.randint(0, 30), rng.randint(31, 120))))),
    Archetype("bank_detail_change", "a supplier asks to change the bank account it is paid into",
              lambda rng: _base(rng, request="bank_detail_change", amount=_large(rng),
                                callback_verified=rng.random() < 0.5, channel=rng.choice(CHANNELS),
                                pressure=rng.random() < 0.5)),
    Archetype("possible_duplicate", "the payment run flags two payments to the same supplier",
              lambda rng: _base(rng, request="possible_duplicate", amount=_large(rng),
                                same_invoice_number=rng.random() < 0.5,
                                days_apart=rng.choice((rng.randint(0, 7), rng.randint(8, 60))))),
)


def _said(f, m, name):
    return bool(mentioned(m, name) and f.get(name))


def _cmp(name, op):
    return lambda f, m: (lambda v: UNKNOWN if v == UNKNOWN else op(v))(known(f, m, name))


def _action(f, m):
    kind = f["request"]
    if kind == "invoice_approval":
        po, got = known(f, m, "matches_po"), known(f, m, "goods_received")
        if False in (po, got):
            return "hold"
        return UNKNOWN if UNKNOWN in (po, got) else "approve"
    if kind == "expense_claim":
        receipt = known(f, m, "has_receipt")
        if receipt == UNKNOWN:
            return UNKNOWN
        if not receipt:
            return "reject"
        amount = known(f, m, "amount")
        return UNKNOWN if amount == UNKNOWN else ("approve" if amount <= 1000 else "hold")
    if kind == "bank_detail_change":
        verified = known(f, m, "callback_verified")
        if verified == UNKNOWN:
            return UNKNOWN
        if verified:
            return "approve"
        return "escalate" if _said(f, m, "pressure") else "hold"
    same = known(f, m, "same_invoice_number")
    return UNKNOWN if same == UNKNOWN else ("reject" if same else "approve")


def _risk(f, m):
    kind = f["request"]
    if kind == "bank_detail_change":
        verified = known(f, m, "callback_verified")
        if verified == UNKNOWN:
            return UNKNOWN
        return 0 if verified else (3 if _said(f, m, "pressure") else 2)
    if kind == "expense_claim":
        receipt = known(f, m, "has_receipt")
        return UNKNOWN if receipt == UNKNOWN else int(not receipt)
    if kind == "possible_duplicate":
        same = known(f, m, "same_invoice_number")
        return UNKNOWN if same == UNKNOWN else 2 * same
    new, amount = known(f, m, "new_vendor"), known(f, m, "amount")
    if UNKNOWN in (new, amount):
        return UNKNOWN
    return int(new) + int(amount > 10000)


def _time_pressure(f, m):
    days = known(f, m, "due_in_days")
    if days == UNKNOWN:
        return UNKNOWN
    return 3 if days <= 2 else 2 if days <= 7 else 1 if days <= 30 else 0


QUESTIONS = (
    Question("po_match", "noul", "Does the invoice match its purchase order?",
             lambda f, m: known(f, m, "matches_po"), ("matches_po",),
             applies=lambda f: f["request"] == "invoice_approval"),
    Question("goods_received", "noul", "Have the goods or services on the invoice been received?",
             lambda f, m: known(f, m, "goods_received"), ("goods_received",),
             applies=lambda f: f["request"] == "invoice_approval"),
    Question("first_invoice", "noul", "Is this the first invoice from this supplier?",
             lambda f, m: known(f, m, "new_vendor"), ("new_vendor",),
             applies=lambda f: f["request"] == "invoice_approval"),
    Question("receipt_attached", "noul", "Does the expense claim have a receipt attached?",
             lambda f, m: known(f, m, "has_receipt"), ("has_receipt",),
             applies=lambda f: f["request"] == "expense_claim"),
    Question("needs_manager", "noul", "Is the expense claim over $1,000?", _cmp("amount", lambda a: a > 1000),
             ("amount",), applies=lambda f: f["request"] == "expense_claim"),
    Question("late_claim", "noul", "Was the claim submitted more than 30 days after the expense?",
             _cmp("days_since_expense", lambda d: d > 30), ("days_since_expense",),
             applies=lambda f: f["request"] == "expense_claim"),
    Question("travel_expense", "noul", "Is this a travel expense?", _cmp("category", lambda c: c == "travel"),
             ("category",), applies=lambda f: f["request"] == "expense_claim"),
    Question("change_verified", "noul", "Was the bank change confirmed by calling the supplier on a number already "
             "on file?", lambda f, m: known(f, m, "callback_verified"), ("callback_verified",),
             applies=lambda f: f["request"] == "bank_detail_change"),
    Question("came_by_email", "noul", "Did the bank change request arrive by email?",
             _cmp("channel", lambda c: c == "email"), ("channel",),
             applies=lambda f: f["request"] == "bank_detail_change"),
    Question("pressured", "noul", "Does the requester insist it is urgent or ask to skip the usual checks?",
             lambda f, m: _said(f, m, "pressure"), ("pressure",)),
    Question("same_invoice", "noul", "Do the two flagged payments carry the same invoice number?",
             lambda f, m: known(f, m, "same_invoice_number"), ("same_invoice_number",),
             applies=lambda f: f["request"] == "possible_duplicate"),
    Question("close_together", "noul", "Are the two flagged payments scheduled within a week of each other?",
             _cmp("days_apart", lambda d: d <= 7), ("days_apart",),
             applies=lambda f: f["request"] == "possible_duplicate"),
    Question("large_amount", "noul", "Is more than $10,000 involved?", _cmp("amount", lambda a: a > 10000),
             ("amount",)),
    Question("due_this_week", "noul", "Is the payment due within 7 days?", _cmp("due_in_days", lambda d: d <= 7),
             ("due_in_days",), applies=lambda f: f["request"] != "expense_claim"),
    Question("request_type", "choice", "What is the finance team asked to handle?",
             lambda f, m: f["request"], ("request",),
             criteria={"invoice_approval": "Approve a supplier invoice",
                       "expense_claim": "Reimburse an employee's expenses",
                       "bank_detail_change": "Change the bank account a supplier is paid into",
                       "possible_duplicate": "Check two payments to the same supplier"},
             hierarchy={"supplier_requests": ["invoice_approval", "bank_detail_change"],
                        "internal_checks": ["expense_claim", "possible_duplicate"]}),
    Question("action", "choice", "What should the finance team do?", _action,
             ("request", "matches_po", "goods_received", "has_receipt", "amount", "callback_verified", "pressure",
              "same_invoice_number"),
             criteria={"approve": "Approve or release it as it is",
                       "hold": "Hold it until a missing document or check is done; expense claims over $1,000 "
                               "need a manager's review",
                       "reject": "Refuse it: an expense without a receipt, or a payment that repeats an invoice "
                                 "already paid",
                       "escalate": "Send it to the fraud team: an unverified bank change with pressure to hurry"},
             hierarchy={"goes_ahead": ["approve", "hold"], "stopped": ["reject", "escalate"]}),
    Question("expense_type", "choice", "What was the expense for?", lambda f, m: known(f, m, "category"),
             ("category",),
             criteria={"travel": "Flights, trains, hotels or taxis", "meals": "Food and drink",
                       "software": "Software licences or subscriptions", "equipment": "Hardware or office equipment"},
             hierarchy={"travel_and_meals": ["travel", "meals"], "purchases": ["software", "equipment"]},
             applies=lambda f: f["request"] == "expense_claim"),
    Question("risk", "score", "How much financial risk does this item carry?", _risk,
             ("request", "callback_verified", "pressure", "has_receipt", "same_invoice_number", "new_vendor",
              "amount"),
             criteria=["None", "Low", "Elevated", "High"]),
    Question("time_pressure", "score", "How pressing is the payment date?", _time_pressure, ("due_in_days",),
             criteria=["More than a month away", "Within a month", "Within a week", "Within two days"],
             applies=lambda f: f["request"] != "expense_claim"),
)

DOMAIN = Domain(
    name="finance_ops", title="Finance operations",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("accounts payable ticket", "email to the finance team", "ERP exception report", "finance team chat message"),
)
