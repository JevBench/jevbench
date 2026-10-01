"""Domain specifications for fact-first synthetic cases.

A domain declares fact slots, scenario archetypes that sample facts, a bank of
typed questions whose answers are rules over the facts, and text styles. A
case is built fact-first: sample facts and how each is mentioned, compute every
answer from the rules, and only then have a language model write the state.
The writer never sees the questions.

Mention levels, per fact:
  explicit  stated plainly in the text
  implied   clear from context without being stated (only for facts marked implied_ok)
  absent    not in the text at all, not even hinted

Answer rules receive (facts, mention) and return the gold answer: True/False
for a Noul, an option key for a Choice, a level index for a Score, or UNKNOWN
when the text cannot settle it. Two kinds of question must not be confused:
"does the text mention X" (absent -> False) and "is X true" (absent -> UNKNOWN).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

UNKNOWN = "__unknown__"
MENTIONS = ("explicit", "implied", "absent")


@dataclass(frozen=True)
class Fact:
    name: str
    kind: str                       # "bool" | "cat" | "int"
    describe: str                   # what the fact is, for the writer and the extractor
    values: tuple = ()              # allowed values for "cat"
    lo: int = 0                     # range for "int"
    hi: int = 0
    implied_ok: bool = False        # may be conveyed indirectly
    always: bool = False            # always explicit (the core of the scenario)
    subject: str | None = None      # for "int": plural noun phrase for threshold questions
    labels: dict | None = None      # for "cat": value -> how the writer should read it
    speech_act: bool = False        # "does the text say X": when False, X is simply not said (absent)
    topic: str | None = None        # short name of the fact for the writer (defaults to describe)
    never_absent: bool = False      # every text conveys it (a tone, a register): explicit or implied, never absent
    absent_note: str | None = None  # when absent: what the writer must leave out, spelled out (common leaks)

    def validate(self, v):
        if v is None:
            return True
        if self.kind == "bool":
            return isinstance(v, bool)
        if self.kind == "cat":
            return v in self.values
        return isinstance(v, int) and self.lo <= v <= self.hi


@dataclass(frozen=True)
class Question:
    key: str
    type: str                                   # "noul" | "choice" | "score"
    instructions: str
    answer: Callable[[dict, dict], Any]         # (facts, mention) -> gold or UNKNOWN
    depends: tuple                              # facts the answer reads
    criteria: Any = None                        # dict for choice, list for score
    applies: Callable[[dict], bool] = lambda f: True
    hierarchy: dict | None = None               # choice: coarse block -> its options, a partition of the options


@dataclass(frozen=True)
class Archetype:
    name: str
    description: str                            # what kind of situation, for the writer
    sample: Callable[[random.Random], dict]     # returns every fact; None where irrelevant


@dataclass(frozen=True)
class Domain:
    name: str
    title: str
    facts: tuple
    archetypes: tuple
    questions: tuple
    styles: tuple                               # text genres, e.g. "customer email"
    fact_index: dict = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "fact_index", {f.name: f for f in self.facts})
        def need(ok, msg):  # an explicit check, not `assert`: it must hold under `python -O` too
            if not ok:
                raise ValueError(f"domain {self.name}: {msg}")

        names = [q.key for q in self.questions]
        need(len(names) == len(set(names)), "duplicate question keys")
        for q in self.questions:
            need(q.type in ("noul", "choice", "score"), f"{q.key}: unknown type {q.type!r}")
            need(all(d in self.fact_index for d in q.depends), f"{q.key}: unknown fact in depends")
            if q.type == "choice":  # four or more options: pairwise conditioning needs them
                need(isinstance(q.criteria, dict) and len(q.criteria) >= 4, f"{q.key}: a Choice needs 4+ options")
                if q.hierarchy:
                    fine = [o for block in q.hierarchy.values() for o in block]
                    need(sorted(fine) == sorted(q.criteria) and len(q.hierarchy) >= 2,
                         f"{q.key}: the hierarchy is not a partition of the options into 2+ blocks")
            if q.type == "score":
                need(isinstance(q.criteria, list) and len(q.criteria) >= 4, f"{q.key}: a Score needs 4+ levels")

    def check_facts(self, facts: dict):
        for name, v in facts.items():
            f = self.fact_index[name]
            if not f.validate(v):
                raise ValueError(f"{self.name}.{name}: invalid value {v!r}")


def mentioned(mention: dict, name: str) -> bool:
    return mention.get(name, "absent") != "absent"


def known(facts: dict, mention: dict, name: str):
    """The fact's value if the text conveys it, else UNKNOWN."""
    return facts.get(name) if mentioned(mention, name) and facts.get(name) is not None else UNKNOWN
