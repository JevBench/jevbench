"""Content moderation: a reported post reaches a platform's moderation queue.

The state describes the report and the post; it never reproduces abusive content itself.
"""

from __future__ import annotations

from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known, mentioned

AUDIENCES = ("public post", "private group", "direct message")

FACTS = (
    Fact("violation", "cat", "what the reported post actually is: unsolicited promotion or scam links (spam), "
         "abuse aimed at a specific person (harassment), a false claim presented as fact (misinformation), or a "
         "post that breaks no rule (no_violation)",
         values=("spam", "harassment", "misinformation", "no_violation"), always=True,
         topic="what the reported post actually is",
         labels={"spam": "unsolicited promotion or scam links",
                 "harassment": "abuse aimed at a specific person, described, not quoted",
                 "misinformation": "a false claim presented as fact",
                 "no_violation": "the post breaks no rule; the reporter disagrees with it"}),
    Fact("reports", "int", "how many users reported the post", lo=1, hi=300, subject="user reports"),
    Fact("views", "int", "how many times the post has been viewed", lo=5, hi=900000, subject="views"),
    Fact("prior_strikes", "int", "how many earlier rule violations the posting account has on record", lo=0, hi=6,
         subject="earlier violations"),
    Fact("account_age_days", "int", "how many days ago the posting account was created", lo=1, hi=4000,
         subject="days since the account was created"),
    Fact("has_link", "bool", "whether the post contains a link to another website"),
    Fact("names_person", "bool", "whether the post names or tags a specific person"),
    Fact("cites_source", "bool", "whether the post cites a source for its claim"),
    Fact("auto_hidden", "bool", "whether the platform's filter has already hidden the post automatically"),
    Fact("audience", "cat", "where the post was shared", values=AUDIENCES, implied_ok=True),
    Fact("poster_disputes", "bool", "whether the poster says the report is wrong or the post was misunderstood",
         speech_act=True),
)


def _base(rng, **kw):
    f = {"reports": rng.choice((rng.randint(1, 3), rng.randint(4, 30), rng.randint(31, 300))),
         "views": rng.choice((rng.randint(5, 999), rng.randint(1000, 49999), rng.randint(50000, 900000))),
         "prior_strikes": rng.choice((0, 0, 1, rng.randint(2, 6))),
         "account_age_days": rng.choice((rng.randint(1, 29), rng.randint(30, 4000))),
         "has_link": None, "names_person": None, "cites_source": None,
         "auto_hidden": rng.random() < 0.2, "audience": rng.choice(AUDIENCES),
         "poster_disputes": rng.random() < 0.3}
    f.update(kw)
    return f


ARCHETYPES = (
    Archetype("spam", "users report a post that promotes something or links to a scam",
              lambda rng: _base(rng, violation="spam", has_link=rng.random() < 0.8,
                                audience=rng.choice(("public post", "direct message")))),
    Archetype("harassment", "users report a post that attacks a specific person",
              lambda rng: _base(rng, violation="harassment", names_person=rng.random() < 0.7)),
    Archetype("misinformation", "users report a post that presents a false claim as fact",
              lambda rng: _base(rng, violation="misinformation", cites_source=rng.random() < 0.4,
                                has_link=rng.random() < 0.5, audience=rng.choice(("public post", "private group")))),
    Archetype("no_violation", "users report a post that they disagree with but that breaks no rule",
              lambda rng: _base(rng, violation="no_violation", prior_strikes=rng.choice((0, 0, 1)),
                                auto_hidden=rng.random() < 0.1, poster_disputes=rng.random() < 0.5)),
)


def _gt(name, n):
    return lambda f, m: (lambda v: UNKNOWN if v == UNKNOWN else v > n)(known(f, m, name))


def _action(f, m):
    kind = f["violation"]
    if kind == "no_violation":
        return "keep"
    if kind == "misinformation":
        src = known(f, m, "cites_source")
        if src == UNKNOWN:
            return UNKNOWN
        if src:
            return "label"
    strikes = known(f, m, "prior_strikes")
    if strikes == UNKNOWN:
        return UNKNOWN
    if strikes >= 2:
        return "suspend"
    if kind == "spam":
        age, link = known(f, m, "account_age_days"), known(f, m, "has_link")
        if (age != UNKNOWN and age >= 30) or link is False:
            return "remove"
        if UNKNOWN in (age, link):
            return UNKNOWN
        return "suspend"
    return "remove"


def _severity(f, m):
    base = {"no_violation": 0, "spam": 1, "misinformation": 2, "harassment": 2}[f["violation"]]
    if base == 0:
        return 0
    views = known(f, m, "views")
    return UNKNOWN if views == UNKNOWN else base + (views > 10000)


def _priority(f, m):
    hidden = known(f, m, "auto_hidden")
    if hidden == UNKNOWN:
        return UNKNOWN
    if hidden:
        return 0
    sev, reports = _severity(f, m), known(f, m, "reports")
    if UNKNOWN in (sev, reports):
        return UNKNOWN
    return min(3, 1 + (reports > 10) + (sev >= 2))


QUESTIONS = (
    Question("breaks_rule", "noul", "Does the reported post break a platform rule?",
             lambda f, m: f["violation"] != "no_violation", ("violation",)),
    Question("link_present", "noul", "Does the post contain a link to another website?",
             lambda f, m: known(f, m, "has_link"), ("has_link",),
             applies=lambda f: f["violation"] in ("spam", "misinformation")),
    Question("person_named", "noul", "Does the post name or tag a specific person?",
             lambda f, m: known(f, m, "names_person"), ("names_person",),
             applies=lambda f: f["violation"] == "harassment"),
    Question("source_cited", "noul", "Does the post cite a source for its claim?",
             lambda f, m: known(f, m, "cites_source"), ("cites_source",),
             applies=lambda f: f["violation"] == "misinformation"),
    Question("repeat_offender", "noul", "Does the account have any earlier violations on record?",
             _gt("prior_strikes", 0), ("prior_strikes",)),
    Question("new_account", "noul", "Was the account created less than 30 days ago?",
             lambda f, m: (lambda a: UNKNOWN if a == UNKNOWN else a < 30)(known(f, m, "account_age_days")),
             ("account_age_days",)),
    Question("widely_seen", "noul", "Has the post been viewed more than 10,000 times?", _gt("views", 10000),
             ("views",)),
    Question("many_reports", "noul", "Was the post reported by more than 10 users?", _gt("reports", 10),
             ("reports",)),
    Question("already_hidden", "noul", "Has the post already been hidden automatically?",
             lambda f, m: known(f, m, "auto_hidden"), ("auto_hidden",)),
    Question("poster_objects", "noul", "Does the poster say the report is wrong?",
             lambda f, m: bool(mentioned(m, "poster_disputes") and f["poster_disputes"]), ("poster_disputes",)),
    Question("public_audience", "noul", "Was the post shared publicly?",
             lambda f, m: (lambda a: UNKNOWN if a == UNKNOWN else a == "public post")(known(f, m, "audience")),
             ("audience",)),
    Question("violation_type", "choice", "What kind of problem does the post have?",
             lambda f, m: f["violation"], ("violation",),
             criteria={"spam": "Unsolicited promotion or scam links",
                       "harassment": "Abuse aimed at a specific person",
                       "misinformation": "A false claim presented as fact",
                       "no_violation": "Breaks no rule"},
             hierarchy={"harm_to_people": ["harassment", "misinformation"], "low_harm": ["spam", "no_violation"]}),
    Question("action", "choice", "What should the moderator do?", _action,
             ("violation", "cites_source", "prior_strikes", "account_age_days", "has_link"),
             criteria={"keep": "Leave the post up; it breaks no rule",
                       "label": "Leave it up with a warning label; the claim is false but cites a source",
                       "remove": "Take the post down",
                       "suspend": "Take the post down and suspend the account: two or more earlier violations, "
                                  "or a new account posting spam links"},
             hierarchy={"stays_up": ["keep", "label"], "comes_down": ["remove", "suspend"]}),
    Question("severity", "score", "How harmful is this post?", _severity, ("violation", "views"),
             criteria=["Harmless", "Minor", "Moderate", "Serious"]),
    Question("priority", "score", "How soon should a moderator review this?", _priority,
             ("auto_hidden", "violation", "views", "reports"),
             criteria=["No rush: already hidden", "Normal queue", "Soon", "Immediately"]),
)

DOMAIN = Domain(
    name="content_moderation", title="Content moderation",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("moderation queue entry", "user report form", "moderator handoff note", "trust and safety chat message"),
)
