"""E-commerce returns: a customer contacts an online shop about an order."""

from __future__ import annotations

from jevbench.datagen.domains._rules import fact, kind_is, test
from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known

CATEGORIES = ("electronics", "clothing", "home goods", "groceries")
WANTS = ("refund", "replacement", "store credit")

FACTS = (
    Fact("reason", "cat", "why the customer contacts the shop: the item arrived broken (damaged_item), a different "
         "item was sent (wrong_item), the customer no longer wants it (changed_mind), or the parcel never arrived "
         "(not_delivered)",
         values=("damaged_item", "wrong_item", "changed_mind", "not_delivered"), always=True,
         topic="why the customer contacts the shop",
         labels={"damaged_item": "the item arrived broken", "wrong_item": "a different item was sent",
                 "changed_mind": "the customer no longer wants the item", "not_delivered": "the parcel never arrived"}),
    Fact("order_value", "int", "the value of the order, in US dollars", lo=5, hi=3000, subject="dollars"),
    Fact("days_since_delivery", "int", "how many days ago the order was delivered", lo=0, hi=90,
         subject="days since delivery"),
    Fact("days_late", "int", "how many days past the promised delivery date it is", lo=1, hi=30,
         subject="days past the promised date"),
    Fact("photo", "bool", "whether the customer sent a photo of the damage"),
    Fact("opened", "bool", "whether the customer has opened or used the item", implied_ok=True),
    Fact("tracking_delivered", "bool", "whether the carrier's tracking says the parcel was delivered"),
    Fact("category", "cat", "what kind of product was ordered", values=CATEGORIES, implied_ok=True),
    Fact("wants", "cat", "what the customer asks for", values=WANTS),
    Fact("member", "bool", "whether the customer is a member of the shop's loyalty programme", implied_ok=True),
    Fact("prior_returns", "int", "how many earlier returns the customer has made this year", lo=0, hi=12,
         subject="earlier returns this year"),
)


def _base(rng, **kw):
    f = {"order_value": rng.choice((rng.randint(5, 99), rng.randint(100, 499), rng.randint(500, 3000))),
         "days_since_delivery": rng.choice((rng.randint(0, 30), rng.randint(31, 90))), "days_late": None,
         "photo": None, "opened": None, "tracking_delivered": None, "category": rng.choice(CATEGORIES),
         "wants": rng.choice(WANTS), "member": rng.random() < 0.4,
         "prior_returns": rng.choice((0, rng.randint(1, 3), rng.randint(4, 12)))}
    f.update(kw)
    return f


ARCHETYPES = (
    Archetype("damaged_item", "the customer's item arrived broken",
              lambda rng: _base(rng, reason="damaged_item", photo=rng.random() < 0.6,
                                days_since_delivery=rng.randint(0, 20))),
    Archetype("wrong_item", "the shop sent the customer a different item",
              lambda rng: _base(rng, reason="wrong_item", days_since_delivery=rng.randint(0, 20),
                                category=rng.choice(CATEGORIES[:3]))),
    Archetype("changed_mind", "the customer wants to return an item they no longer want",
              lambda rng: _base(rng, reason="changed_mind", opened=rng.random() < 0.5,
                                category=rng.choice(CATEGORIES[:3]), wants=rng.choice(("refund", "store credit")))),
    Archetype("not_delivered", "the customer's parcel has not arrived",
              lambda rng: _base(rng, reason="not_delivered", days_since_delivery=None,
                                days_late=rng.choice((rng.randint(1, 3), rng.randint(4, 30))),
                                tracking_delivered=rng.random() < 0.4, wants=rng.choice(("refund", "replacement")))),
)


def _decision(f, m):
    reason = f["reason"]
    if reason == "wrong_item":
        return "replace"
    if reason == "damaged_item":
        photo = known(f, m, "photo")
        return UNKNOWN if photo == UNKNOWN else ("replace" if photo else "investigate")
    if reason == "not_delivered":
        tracked = known(f, m, "tracking_delivered")
        return UNKNOWN if tracked == UNKNOWN else ("investigate" if tracked else "refund")
    days, opened = known(f, m, "days_since_delivery"), known(f, m, "opened")
    if opened is True or (days != UNKNOWN and days > 30):
        return "deny"
    return UNKNOWN if UNKNOWN in (days, opened) else "refund"


def _fraud(f, m):
    returns, value = known(f, m, "prior_returns"), known(f, m, "order_value")
    decision = _decision(f, m)
    if UNKNOWN in (returns, value, decision):
        return UNKNOWN
    return (returns > 3) + (value > 500) + (decision == "investigate")


QUESTIONS = (
    Question("within_30_days", "noul", "Was the order delivered within the last 30 days?",
             test("days_since_delivery", lambda d: d <= 30), ("days_since_delivery",),
             applies=kind_is("reason", "damaged_item", "wrong_item", "changed_mind")),
    Question("photo_sent", "noul", "Did the customer send a photo of the damage?", fact("photo"), ("photo",),
             applies=kind_is("reason", "damaged_item")),
    Question("item_opened", "noul", "Has the customer opened or used the item?", fact("opened"), ("opened",),
             applies=kind_is("reason", "changed_mind")),
    Question("tracking_says_delivered", "noul", "Does the carrier's tracking say the parcel was delivered?",
             fact("tracking_delivered"), ("tracking_delivered",), applies=kind_is("reason", "not_delivered")),
    Question("very_late", "noul", "Is the parcel more than 3 days late?", test("days_late", lambda d: d > 3),
             ("days_late",), applies=kind_is("reason", "not_delivered")),
    Question("high_value", "noul", "Is the order worth more than $500?", test("order_value", lambda v: v > 500),
             ("order_value",)),
    Question("frequent_returner", "noul", "Has the customer made more than 3 returns this year?",
             test("prior_returns", lambda n: n > 3), ("prior_returns",)),
    Question("loyalty_member", "noul", "Is the customer a loyalty programme member?", fact("member"), ("member",)),
    Question("wants_money_back", "noul", "Does the customer ask for their money back?",
             test("wants", lambda w: w == "refund"), ("wants",)),
    Question("reason", "choice", "Why is the customer contacting the shop?", lambda f, m: f["reason"], ("reason",),
             criteria={"damaged_item": "The item arrived broken", "wrong_item": "A different item was sent",
                       "changed_mind": "The customer no longer wants it", "not_delivered": "The parcel never arrived"},
             hierarchy={"shop_or_carrier_error": ["damaged_item", "wrong_item"],
                        "no_item_in_hand": ["changed_mind", "not_delivered"]}),
    Question("decision", "choice", "What should the shop do?", _decision,
             ("reason", "photo", "tracking_delivered", "days_since_delivery", "opened"),
             criteria={"refund": "Refund the customer: an unopened return within 30 days, or a parcel that "
                                 "tracking agrees never arrived",
                       "replace": "Send a replacement: the wrong item was sent, or it arrived broken and the "
                                  "customer sent a photo",
                       "deny": "Refuse the return: the item was opened, or it was delivered more than 30 days ago",
                       "investigate": "Open an investigation: damage without a photo, or tracking says delivered "
                                      "but the customer says it was not"},
             hierarchy={"customer_is_made_whole": ["refund", "replace"], "no_payout_now": ["deny", "investigate"]}),
    Question("product_category", "choice", "What kind of product was ordered?", fact("category"), ("category",),
             criteria={"electronics": "Electronics", "clothing": "Clothing", "home goods": "Home goods",
                       "groceries": "Groceries"},
             hierarchy={"durable": ["electronics", "home goods"], "everyday": ["clothing", "groceries"]}),
    Question("fraud_risk", "score", "How much fraud risk does this request carry?", _fraud,
             ("prior_returns", "order_value", "reason", "photo", "tracking_delivered", "days_since_delivery",
              "opened"),
             criteria=["None", "Low", "Elevated", "High"]),
)

DOMAIN = Domain(
    name="ecommerce_returns", title="E-commerce returns",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("customer email to the shop", "return request form", "live chat transcript", "order support ticket"),
)
