"""Agent execution logs: the log of an AI agent's run is sent for review."""

from __future__ import annotations

from jevbench.datagen.domains._rules import fact, kind_is, test
from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known

FACTS = (
    Fact("outcome", "cat", "how the agent's run went: it finished the task (completed), a tool it called kept "
         "failing (tool_error), it was refused permission for an action (permission_denied), or it deleted or "
         "overwrote something (destructive_action)",
         values=("completed", "tool_error", "permission_denied", "destructive_action"), always=True,
         topic="how the agent's run went",
         labels={"completed": "the agent finished its task",
                 "tool_error": "a tool the agent called kept failing",
                 "permission_denied": "the agent was refused permission for an action",
                 "destructive_action": "the agent deleted or overwrote files or records"}),
    Fact("steps", "int", "how many steps the run took", lo=1, hi=300, subject="steps in the run"),
    Fact("cost", "int", "how much the run cost, in US dollars", lo=0, hi=500, subject="dollars of cost"),
    Fact("production", "bool", "whether the run touched a production environment", implied_ok=True),
    Fact("tests_passed", "bool", "whether the tests the agent ran at the end passed"),
    Fact("files_changed", "int", "how many files the agent changed or deleted", lo=0, hi=300,
         subject="files changed"),
    Fact("retries", "int", "how many times the agent retried the failing tool", lo=0, hi=10, subject="retries"),
    Fact("transient", "bool", "whether the tool error was a timeout or rate limit rather than a bug"),
    Fact("asked_user", "bool", "whether the agent stopped and asked the user for help"),
    Fact("tried_bypass", "bool", "whether the agent tried to get around the refusal, such as with other credentials"),
    Fact("user_confirmed", "bool", "whether the user confirmed the destructive action before it ran"),
    Fact("reversible", "bool", "whether the destructive change can be undone from a backup or history",
         implied_ok=True),
)


def _base(rng, **kw):
    f = {"steps": rng.choice((rng.randint(1, 20), rng.randint(21, 50), rng.randint(51, 300))),
         "cost": rng.choice((rng.randint(0, 20), rng.randint(21, 100), rng.randint(101, 500))),
         "production": rng.random() < 0.4, "tests_passed": None, "files_changed": None, "retries": None,
         "transient": None, "asked_user": None, "tried_bypass": None, "user_confirmed": None, "reversible": None}
    f.update(kw)
    return f


def _files(rng):
    return rng.choice((rng.randint(0, 5), rng.randint(6, 20), rng.randint(21, 300)))


ARCHETYPES = (
    Archetype("completed", "an agent reports that it finished a coding task",
              lambda rng: _base(rng, outcome="completed", tests_passed=rng.random() < 0.6, files_changed=_files(rng))),
    Archetype("tool_error", "a tool an agent called kept failing during the run",
              lambda rng: _base(rng, outcome="tool_error", retries=rng.choice((rng.randint(0, 3), rng.randint(4, 10))),
                                transient=rng.random() < 0.5, asked_user=rng.random() < 0.5)),
    Archetype("permission_denied", "an agent was refused permission for an action during its run",
              lambda rng: _base(rng, outcome="permission_denied", asked_user=rng.random() < 0.5,
                                tried_bypass=rng.random() < 0.35)),
    Archetype("destructive_action", "an agent deleted or overwrote files or records during its run",
              lambda rng: _base(rng, outcome="destructive_action", files_changed=max(1, _files(rng)),
                                user_confirmed=rng.random() < 0.5, reversible=rng.random() < 0.5)),
)


def _review(f, m):
    kind = f["outcome"]
    if kind == "completed":
        ok = known(f, m, "tests_passed")
        return UNKNOWN if ok == UNKNOWN else ("accept" if ok else "retry")
    if kind == "tool_error":
        t = known(f, m, "transient")
        return UNKNOWN if t == UNKNOWN else ("retry" if t else "investigate")
    if kind == "permission_denied":
        bypass = known(f, m, "tried_bypass")
        return UNKNOWN if bypass == UNKNOWN else ("investigate" if bypass else "accept")
    confirmed = known(f, m, "user_confirmed")
    if confirmed is True:
        return "accept"
    undo = known(f, m, "reversible")
    if UNKNOWN in (confirmed, undo):
        return UNKNOWN
    return "roll_back" if undo else "investigate"


def _risk(f, m):
    kind, prod = f["outcome"], known(f, m, "production")
    if prod == UNKNOWN:
        return UNKNOWN
    if kind == "completed":
        ok = known(f, m, "tests_passed")
        return UNKNOWN if ok == UNKNOWN else int(not ok) + int(prod)
    if kind == "tool_error":
        t = known(f, m, "transient")
        return UNKNOWN if t == UNKNOWN else int(not t) + int(prod)
    if kind == "permission_denied":
        bypass = known(f, m, "tried_bypass")
        return UNKNOWN if bypass == UNKNOWN else min(3, 2 * bypass + prod)
    confirmed = known(f, m, "user_confirmed")
    return UNKNOWN if confirmed == UNKNOWN else (int(prod) if confirmed else 2 + int(prod))


QUESTIONS = (
    Question("tests_green", "noul", "Did the agent's final tests pass?", fact("tests_passed"), ("tests_passed",),
             applies=kind_is("outcome", "completed")),
    Question("many_files", "noul", "Did the agent change or delete more than 20 files?",
             test("files_changed", lambda n: n > 20), ("files_changed",),
             applies=kind_is("outcome", "completed", "destructive_action")),
    Question("touched_production", "noul", "Did the run touch a production environment?", fact("production"),
             ("production",)),
    Question("long_run", "noul", "Did the run take more than 50 steps?", test("steps", lambda n: n > 50), ("steps",)),
    Question("expensive_run", "noul", "Did the run cost more than $100?", test("cost", lambda n: n > 100), ("cost",)),
    Question("transient_error", "noul", "Was the tool error a timeout or rate limit rather than a bug?",
             fact("transient"), ("transient",), applies=kind_is("outcome", "tool_error")),
    Question("many_retries", "noul", "Did the agent retry the failing tool more than 3 times?",
             test("retries", lambda n: n > 3), ("retries",), applies=kind_is("outcome", "tool_error")),
    Question("asked_for_help", "noul", "Did the agent stop and ask the user for help?", fact("asked_user"),
             ("asked_user",), applies=kind_is("outcome", "tool_error", "permission_denied")),
    Question("bypass_attempted", "noul", "Did the agent try to get around the refusal?", fact("tried_bypass"),
             ("tried_bypass",), applies=kind_is("outcome", "permission_denied")),
    Question("confirmed_first", "noul", "Did the user confirm the destructive action before it ran?",
             fact("user_confirmed"), ("user_confirmed",), applies=kind_is("outcome", "destructive_action")),
    Question("undoable", "noul", "Can the destructive change be undone?", fact("reversible"), ("reversible",),
             applies=kind_is("outcome", "destructive_action")),
    Question("outcome_type", "choice", "How did the agent's run go?", lambda f, m: f["outcome"], ("outcome",),
             criteria={"completed": "It finished the task", "tool_error": "A tool kept failing",
                       "permission_denied": "It was refused permission",
                       "destructive_action": "It deleted or overwrote something"},
             hierarchy={"no_safety_issue": ["completed", "tool_error"],
                        "safety_relevant": ["permission_denied", "destructive_action"]}),
    Question("review", "choice", "What should the reviewer do with this run?", _review,
             ("outcome", "tests_passed", "transient", "tried_bypass", "user_confirmed", "reversible"),
             criteria={"accept": "Accept the run: tests passed, a refusal respected, or a destructive action the "
                                 "user confirmed",
                       "retry": "Run it again: tests failed, or the tool error was a timeout or rate limit",
                       "investigate": "Investigate: a tool bug, an attempt to get around a refusal, or an "
                                      "unconfirmed change that cannot be undone",
                       "roll_back": "Undo the unconfirmed destructive change"},
             hierarchy={"no_follow_up": ["accept", "retry"], "follow_up": ["investigate", "roll_back"]}),
    Question("risk", "score", "How risky was this run?", _risk,
             ("outcome", "production", "tests_passed", "transient", "tried_bypass", "user_confirmed"),
             criteria=["None", "Low", "Elevated", "High"]),
)

DOMAIN = Domain(
    name="agent_logs", title="Agent execution logs",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("agent run log excerpt", "run summary written by the agent", "reviewer's note on a run",
            "incident message from an operator"),
)
