"""IT incidents: a ticket reaches a company's IT service desk."""

from __future__ import annotations

from jevbench.datagen.domains._rules import fact, kind_is, test
from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known

SYSTEMS = ("email", "VPN", "payroll system", "internal wiki")
LEVELS = ("read-only", "editor", "administrator")

FACTS = (
    Fact("kind", "cat", "what the ticket is about: a service that has stopped working (outage), a service that "
         "works but is very slow (performance), someone asking for access to a system (access_request), or a "
         "broken laptop or phone (hardware)",
         values=("outage", "performance", "access_request", "hardware"), always=True,
         topic="what the ticket is about",
         labels={"outage": "a service has stopped working",
                 "performance": "a service works but is very slow",
                 "access_request": "an employee asks for access to a system",
                 "hardware": "an employee's laptop or phone is broken"}),
    Fact("system", "cat", "which system the ticket concerns", values=SYSTEMS),
    Fact("users_affected", "int", "how many employees are affected", lo=1, hi=2000, subject="affected employees"),
    Fact("minutes_down", "int", "for how many minutes the problem has lasted so far", lo=1, hi=600,
         subject="minutes of disruption"),
    Fact("recent_change", "bool", "whether a change was deployed to the system shortly before the problem started"),
    Fact("rollback_ready", "bool", "whether that change can be rolled back quickly", implied_ok=True),
    Fact("workaround", "bool", "whether affected people have a workaround that works", implied_ok=True),
    Fact("manager_approved", "bool", "whether the requester's manager has approved the access"),
    Fact("access_level", "cat", "what level of access is requested", values=LEVELS),
    Fact("deadline_hours", "int", "in how many hours the requester needs it done", lo=1, hi=120,
         subject="hours until the requester needs it"),
    Fact("device_age_years", "int", "how many years old the broken device is", lo=0, hi=8,
         subject="years since the device was bought"),
    Fact("under_warranty", "bool", "whether the broken device is still under warranty"),
    Fact("backed_up", "bool", "whether the data on the device is backed up", implied_ok=True),
)


def _base(rng, **kw):
    f = {"system": rng.choice(SYSTEMS), "users_affected": None, "minutes_down": None, "recent_change": None,
         "rollback_ready": None, "workaround": None, "manager_approved": None, "access_level": None,
         "deadline_hours": None, "device_age_years": None, "under_warranty": None, "backed_up": None}
    f.update(kw)
    return f


def _service(kind):
    def sample(rng):
        change = rng.random() < 0.5
        return _base(rng, kind=kind, users_affected=rng.choice((rng.randint(1, 20), rng.randint(21, 100),
                                                                 rng.randint(101, 2000))),
                     minutes_down=rng.choice((rng.randint(1, 60), rng.randint(61, 600))),
                     recent_change=change, rollback_ready=(rng.random() < 0.6) if change else None,
                     workaround=rng.random() < 0.4)
    return sample


def _hardware(rng):
    age = rng.randint(0, 8)
    return _base(rng, kind="hardware", system=None, users_affected=1, device_age_years=age,
                 under_warranty=age <= 3 and rng.random() < 0.8, backed_up=rng.random() < 0.6,
                 workaround=rng.random() < 0.4, deadline_hours=rng.choice((rng.randint(1, 24), rng.randint(25, 120))))


ARCHETYPES = (
    Archetype("outage", "a service has stopped working for employees", _service("outage")),
    Archetype("performance", "a service works but is very slow", _service("performance")),
    Archetype("access_request", "an employee asks for access to a system",
              lambda rng: _base(rng, kind="access_request", users_affected=1,
                                manager_approved=rng.random() < 0.6, access_level=rng.choice(LEVELS),
                                deadline_hours=rng.choice((rng.randint(1, 24), rng.randint(25, 120))))),
    Archetype("hardware", "an employee's laptop or phone is broken", _hardware),
)

SERVICE = kind_is("kind", "outage", "performance")


def _action(f, m):
    kind = f["kind"]
    if kind in ("outage", "performance"):
        change = known(f, m, "recent_change")
        if change is False:
            return "escalate"
        if change == UNKNOWN:
            return UNKNOWN
        ready = known(f, m, "rollback_ready")
        return UNKNOWN if ready == UNKNOWN else ("roll_back" if ready else "escalate")
    if kind == "access_request":
        ok = known(f, m, "manager_approved")
        return UNKNOWN if ok == UNKNOWN else ("fulfil" if ok else "wait_for_approval")
    warranty = known(f, m, "under_warranty")
    return UNKNOWN if warranty == UNKNOWN else ("fulfil" if warranty else "wait_for_approval")


def _priority(f, m):
    kind = f["kind"]
    if kind in ("outage", "performance"):
        users, wa = known(f, m, "users_affected"), known(f, m, "workaround")
        if UNKNOWN in (users, wa):
            return UNKNOWN
        p = 1 + (users > 100) + (not wa)
        return p if kind == "outage" else p - 1
    hours = known(f, m, "deadline_hours")
    if hours == UNKNOWN:
        return UNKNOWN
    if kind == "hardware":
        wa = known(f, m, "workaround")
        if wa == UNKNOWN:
            return UNKNOWN
        return 1 + (hours <= 24 and not wa)
    return 2 if hours <= 24 else 1 if hours <= 48 else 0


QUESTIONS = (
    Question("recent_change", "noul", "Was a change deployed shortly before the problem started?",
             fact("recent_change"), ("recent_change",), applies=SERVICE),
    Question("rollback_possible", "noul", "Can the recent change be rolled back quickly?", fact("rollback_ready"),
             ("rollback_ready",), applies=lambda f: SERVICE(f) and f["recent_change"]),
    Question("workaround_exists", "noul", "Do the affected people have a workaround that works?",
             fact("workaround"), ("workaround",), applies=kind_is("kind", "outage", "performance", "hardware")),
    Question("many_users", "noul", "Are more than 100 employees affected?", test("users_affected", lambda n: n > 100),
             ("users_affected",), applies=SERVICE),
    Question("long_disruption", "noul", "Has the problem lasted more than an hour?",
             test("minutes_down", lambda n: n > 60), ("minutes_down",), applies=SERVICE),
    Question("approved", "noul", "Has the requester's manager approved the access?", fact("manager_approved"),
             ("manager_approved",), applies=kind_is("kind", "access_request")),
    Question("admin_rights", "noul", "Is administrator access requested?",
             test("access_level", lambda v: v == "administrator"), ("access_level",),
             applies=kind_is("kind", "access_request")),
    Question("payroll_involved", "noul", "Does the ticket concern the payroll system?",
             test("system", lambda v: v == "payroll system"), ("system",),
             applies=kind_is("kind", "outage", "performance", "access_request")),
    Question("needed_today", "noul", "Is it needed within 24 hours?", test("deadline_hours", lambda n: n <= 24),
             ("deadline_hours",), applies=kind_is("kind", "access_request", "hardware")),
    Question("warranty", "noul", "Is the broken device still under warranty?", fact("under_warranty"),
             ("under_warranty",), applies=kind_is("kind", "hardware")),
    Question("old_device", "noul", "Is the device more than 4 years old?", test("device_age_years", lambda n: n > 4),
             ("device_age_years",), applies=kind_is("kind", "hardware")),
    Question("data_safe", "noul", "Is the data on the device backed up?", fact("backed_up"), ("backed_up",),
             applies=kind_is("kind", "hardware")),
    Question("ticket_type", "choice", "What kind of ticket is this?", lambda f, m: f["kind"], ("kind",),
             criteria={"outage": "A service has stopped working", "performance": "A service is very slow",
                       "access_request": "Someone needs access to a system",
                       "hardware": "A laptop or phone is broken"},
             hierarchy={"service_problems": ["outage", "performance"], "user_requests": ["access_request", "hardware"]}),
    Question("action", "choice", "What should the service desk do next?", _action,
             ("kind", "recent_change", "rollback_ready", "manager_approved", "under_warranty"),
             criteria={"roll_back": "Roll back the recent change that caused the problem",
                       "escalate": "Send it to the engineering team: no change to roll back, or it cannot be "
                                   "rolled back quickly",
                       "fulfil": "Do it now: grant the approved access, or replace the device under warranty",
                       "wait_for_approval": "Wait for a manager's approval of the access, or of buying a "
                                            "device that is out of warranty"},
             hierarchy={"engineering_work": ["roll_back", "escalate"],
                        "service_desk_work": ["fulfil", "wait_for_approval"]}),
    Question("affected_system", "choice", "Which system does the ticket concern?", fact("system"), ("system",),
             criteria={"email": "Email", "VPN": "The VPN", "payroll system": "The payroll system",
                       "internal wiki": "The internal wiki"},
             hierarchy={"connectivity": ["email", "VPN"], "business_apps": ["payroll system", "internal wiki"]},
             applies=kind_is("kind", "outage", "performance", "access_request")),
    Question("priority", "score", "What priority should this ticket get?", _priority,
             ("kind", "users_affected", "workaround", "deadline_hours"),
             criteria=["Low", "Normal", "High", "Critical"]),
)

DOMAIN = Domain(
    name="it_incidents", title="IT incidents",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("service desk ticket", "email to IT support", "on-call chat message", "monitoring alert with notes"),
)
