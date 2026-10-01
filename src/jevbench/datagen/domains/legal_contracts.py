"""Legal and contracts: a contract matter reaches a company's in-house legal team."""

from __future__ import annotations

from jevbench.datagen.domains._rules import fact, kind_is, said, test
from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known

LAWS = ("New York", "California", "England", "Singapore")

FACTS = (
    Fact("matter", "cat", "what legal is asked to handle: reviewing a confidentiality agreement (nda_review), "
         "reviewing a new contract with a supplier (vendor_contract), an existing contract coming up for renewal "
         "(renewal), or a claim that the other side broke a contract (breach_claim)",
         values=("nda_review", "vendor_contract", "renewal", "breach_claim"), always=True,
         topic="what legal is asked to handle",
         labels={"nda_review": "review a confidentiality agreement (NDA)",
                 "vendor_contract": "review a new contract with a supplier",
                 "renewal": "an existing contract is coming up for renewal",
                 "breach_claim": "the other side may have broken a contract"}),
    Fact("value_k", "int", "the money at stake, in thousands of dollars", lo=1, hi=5000,
         subject="thousand dollars at stake"),
    Fact("term_years", "int", "how many years the agreement lasts", lo=1, hi=10, subject="years of term"),
    Fact("mutual", "bool", "whether the confidentiality agreement binds both sides"),
    Fact("own_template", "bool", "whether the contract uses the company's own standard template", implied_ok=True),
    Fact("uncapped", "bool", "whether the contract leaves the company's liability unlimited"),
    Fact("personal_data", "bool", "whether the supplier will handle personal data", implied_ok=True),
    Fact("auto_renews", "bool", "whether the contract renews automatically unless notice is given"),
    Fact("days_to_notice", "int", "how many days are left before the notice deadline", lo=0, hi=120,
         subject="days until the notice deadline"),
    Fact("wants_exit", "bool", "whether the business team says it wants to end the contract", speech_act=True),
    Fact("admits", "bool", "whether the other side admits the breach", speech_act=True),
    Fact("notice_sent", "bool", "whether a formal notice of breach has already been sent"),
    Fact("days_since_breach", "int", "how many days ago the breach happened", lo=0, hi=720,
         subject="days since the breach"),
    Fact("governing_law", "cat", "which law governs the contract", values=LAWS),
)


def _base(rng, **kw):
    f = {k: None for k in ("term_years", "mutual", "own_template", "uncapped", "personal_data", "auto_renews",
                           "days_to_notice", "wants_exit", "admits", "notice_sent", "days_since_breach",
                           "governing_law")}
    f["value_k"] = rng.choice((rng.randint(1, 99), rng.randint(100, 499), rng.randint(500, 5000)))
    f.update(kw)
    return f


ARCHETYPES = (
    Archetype("nda_review", "a business team sends a confidentiality agreement (NDA) for review",
              lambda rng: _base(rng, matter="nda_review", value_k=None, term_years=rng.randint(1, 7),
                                mutual=rng.random() < 0.6, own_template=rng.random() < 0.5,
                                governing_law=rng.choice(LAWS))),
    Archetype("vendor_contract", "a business team sends a new supplier contract for review",
              lambda rng: _base(rng, matter="vendor_contract", term_years=rng.randint(1, 10),
                                own_template=rng.random() < 0.4, uncapped=rng.random() < 0.3,
                                personal_data=rng.random() < 0.5, auto_renews=rng.random() < 0.5,
                                governing_law=rng.choice(LAWS))),
    Archetype("renewal", "an existing contract is coming up for renewal",
              lambda rng: _base(rng, matter="renewal", auto_renews=rng.random() < 0.6,
                                days_to_notice=rng.choice((rng.randint(0, 7), rng.randint(8, 30), rng.randint(31, 120))),
                                wants_exit=rng.random() < 0.5)),
    Archetype("breach_claim", "a business team says the other side broke a contract",
              lambda rng: _base(rng, matter="breach_claim", admits=rng.random() < 0.4, notice_sent=rng.random() < 0.5,
                                days_since_breach=rng.choice((rng.randint(0, 365), rng.randint(366, 720))))),
)


def _action(f, m):
    kind = f["matter"]
    if kind == "nda_review":
        mutual, own = known(f, m, "mutual"), known(f, m, "own_template")
        if False in (mutual, own):
            return "negotiate"
        return UNKNOWN if UNKNOWN in (mutual, own) else "approve"
    if kind == "vendor_contract":
        uncapped = known(f, m, "uncapped")
        if uncapped is True:
            return "escalate"
        own = known(f, m, "own_template")
        if UNKNOWN in (uncapped, own):
            return UNKNOWN
        return "approve" if own else "negotiate"
    if kind == "renewal":
        if said(f, m, "wants_exit"):
            return "send_notice"
        auto = known(f, m, "auto_renews")
        return UNKNOWN if auto == UNKNOWN else ("approve" if auto else "negotiate")
    if said(f, m, "admits"):
        return "negotiate"
    sent = known(f, m, "notice_sent")
    return UNKNOWN if sent == UNKNOWN else ("escalate" if sent else "send_notice")


def _exposure(f, m):
    kind = f["matter"]
    if kind == "nda_review":
        mutual, own = known(f, m, "mutual"), known(f, m, "own_template")
        return UNKNOWN if UNKNOWN in (mutual, own) else int(not mutual) + int(not own)
    if kind == "vendor_contract":
        uncapped, data = known(f, m, "uncapped"), known(f, m, "personal_data")
        return UNKNOWN if UNKNOWN in (uncapped, data) else min(3, 2 * uncapped + data)
    value = known(f, m, "value_k")
    if value == UNKNOWN:
        return UNKNOWN
    if kind == "renewal":
        days, auto = known(f, m, "days_to_notice"), known(f, m, "auto_renews")
        if UNKNOWN in (days, auto):
            return UNKNOWN
        return int(value >= 500) + int(auto and days <= 30)
    return 1 + int(value >= 500) + int(not said(f, m, "admits"))


QUESTIONS = (
    Question("mutual_nda", "noul", "Does the confidentiality agreement bind both sides?", fact("mutual"), ("mutual",),
             applies=kind_is("matter", "nda_review")),
    Question("our_template", "noul", "Does the contract use the company's own standard template?",
             fact("own_template"), ("own_template",), applies=kind_is("matter", "nda_review", "vendor_contract")),
    Question("long_term", "noul", "Does the agreement last more than 3 years?", test("term_years", lambda n: n > 3),
             ("term_years",), applies=kind_is("matter", "nda_review", "vendor_contract")),
    Question("us_law", "noul", "Is the contract governed by a US state's law?",
             test("governing_law", lambda v: v in ("New York", "California")), ("governing_law",),
             applies=kind_is("matter", "nda_review", "vendor_contract")),
    Question("unlimited_liability", "noul", "Does the contract leave the company's liability unlimited?",
             fact("uncapped"), ("uncapped",), applies=kind_is("matter", "vendor_contract")),
    Question("handles_personal_data", "noul", "Will the supplier handle personal data?", fact("personal_data"),
             ("personal_data",), applies=kind_is("matter", "vendor_contract")),
    Question("renews_automatically", "noul", "Does the contract renew automatically unless notice is given?",
             fact("auto_renews"), ("auto_renews",), applies=kind_is("matter", "vendor_contract", "renewal")),
    Question("deadline_close", "noul", "Is the notice deadline 30 days away or less?",
             test("days_to_notice", lambda d: d <= 30), ("days_to_notice",), applies=kind_is("matter", "renewal")),
    Question("deadline_this_week", "noul", "Is the notice deadline 7 days away or less?",
             test("days_to_notice", lambda d: d <= 7), ("days_to_notice",), applies=kind_is("matter", "renewal")),
    Question("business_wants_out", "noul", "Does the business team say it wants to end the contract?",
             lambda f, m: said(f, m, "wants_exit"), ("wants_exit",), applies=kind_is("matter", "renewal")),
    Question("breach_admitted", "noul", "Does the other side admit the breach?", lambda f, m: said(f, m, "admits"),
             ("admits",), applies=kind_is("matter", "breach_claim")),
    Question("notice_already_sent", "noul", "Has a formal notice of breach already been sent?", fact("notice_sent"),
             ("notice_sent",), applies=kind_is("matter", "breach_claim")),
    Question("recent_breach", "noul", "Did the breach happen within the last year?",
             test("days_since_breach", lambda d: d <= 365), ("days_since_breach",),
             applies=kind_is("matter", "breach_claim")),
    Question("old_breach", "noul", "Did the breach happen more than 6 months ago?",
             test("days_since_breach", lambda d: d > 180), ("days_since_breach",),
             applies=kind_is("matter", "breach_claim")),
    Question("high_stakes", "noul", "Is $500,000 or more at stake?", test("value_k", lambda v: v >= 500),
             ("value_k",), applies=kind_is("matter", "vendor_contract", "renewal", "breach_claim")),
    Question("matter_type", "choice", "What is legal asked to handle?", lambda f, m: f["matter"], ("matter",),
             criteria={"nda_review": "Review a confidentiality agreement", "vendor_contract": "Review a supplier contract",
                       "renewal": "A contract coming up for renewal", "breach_claim": "A possible breach of contract"},
             hierarchy={"new_agreements": ["nda_review", "vendor_contract"],
                        "existing_agreements": ["renewal", "breach_claim"]}),
    Question("action", "choice", "What should legal do?", _action,
             ("matter", "mutual", "own_template", "uncapped", "wants_exit", "auto_renews", "admits", "notice_sent"),
             criteria={"approve": "Sign off as it is: a mutual NDA or supplier contract on our template, or a "
                                  "renewal that happens automatically",
                       "negotiate": "Negotiate changes or a settlement: off-template or one-sided terms, a renewal "
                                    "that needs new terms, or a breach the other side admits",
                       "send_notice": "Send a formal notice: to end a contract, or of a breach",
                       "escalate": "Refer to the general counsel: unlimited liability, or a breach still denied "
                                   "after notice"},
             hierarchy={"routine": ["approve", "negotiate"], "formal_steps": ["send_notice", "escalate"]}),
    Question("law", "choice", "Which law governs the contract?", fact("governing_law"), ("governing_law",),
             criteria={"New York": "New York law", "California": "California law", "England": "English law",
                       "Singapore": "Singapore law"},
             hierarchy={"united_states": ["New York", "California"], "elsewhere": ["England", "Singapore"]},
             applies=kind_is("matter", "nda_review", "vendor_contract")),
    Question("exposure", "score", "How much legal or financial exposure does this matter carry?", _exposure,
             ("matter", "mutual", "own_template", "uncapped", "personal_data", "value_k", "days_to_notice",
              "auto_renews", "admits"),
             criteria=["Minimal", "Some", "Significant", "Severe"]),
)

DOMAIN = Domain(
    name="legal_contracts", title="Legal and contracts",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("legal intake form", "email to the legal team", "contract review request", "legal team chat message"),
)
