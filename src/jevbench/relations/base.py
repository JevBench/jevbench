"""The relation plugin interface.

A relation is a metamorphic test: a transformation T of the questions (never
the state) and one law R that the transformed answers should bear to the
untransformed ones. `build` makes a Trial of one or more requests; `evaluate`
turns their answers into one Outcome per tested question, a nonnegative
deviation compared with a tolerance derived from the backend's own repeat
noise. Variants (templates, or one per option for a law stated for every
option) are separate trials of the same test; scoring takes their largest
deviation, so the law holds for a test only if it holds for every variant.
Relations that read the same questions share a build and `rng_name`, so their
requests coincide and are answered once.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from jevbench import taxonomy
from jevbench.schema import Case


@dataclass
class Trial:
    relation: str
    case_id: str
    targets: list[str]
    requests: dict[str, dict]  # label -> questions sent with the case's state
    params: dict = field(default_factory=dict)


class NoiseTolerance(float):
    """A tolerance derived from repeat noise (Context.tolerance): scores re-judge it at one fixed tolerance."""


@dataclass
class Outcome:
    relation: str
    check: str
    case_id: str
    targets: list[str]
    deviation: float
    tolerance: float
    flip: bool | None = None
    detail: dict = field(default_factory=dict)
    tolerance_kind: str = "own"   # "noise": from Context.tolerance (re-judged at the fixed tolerance); "own": the law's

    @property
    def violated(self) -> bool:
        return not (self.deviation <= self.tolerance)   # a NaN deviation is a violation, never a pass


@dataclass
class Context:
    """Per-case data available to relations: base answers and noise."""

    base: dict[str, dict[str, float]]   # key -> mean distribution over repeats
    noise: dict[str, float]             # key -> max TV of a repeat to the mean
    noise_multiplier: float = 2.0
    noise_floor: float = 0.05
    rewrites: object = None             # jevbench.rewrite.RewriteBank or None
    raw_base: list = None               # unparsed wire answers of each base repeat
    questions: dict = None              # the case's questions, for relations reading raw answers

    def tolerance(self, *keys: str) -> float:
        return NoiseTolerance(max(self.noise_floor, self.noise_multiplier * max(self.noise[k] for k in keys)))


class Relation:
    name = ""
    expectation = ""   # the relation R in one line
    source = ""        # where the expected relation comes from
    deterministic = False  # True: the trial does not depend on the random draw
    templates: tuple = ()  # alternative wordings; each is run as its own variant
    rng_name = ""          # draw with another relation's seed, to share its requests (and cache)
    needs_rewrites = False  # its variants come from a rewrite bank; inapplicable without one

    def applicable(self, case: Case, key: str, ctx: Context) -> bool:
        raise NotImplementedError

    def variants(self, case: Case, key: str, ctx: Context) -> int:
        """How many distinct variants (templates, rewrites) to run for this target."""
        return max(1, len(self.templates))

    def build(self, case: Case, key: str, rng: random.Random, ctx: Context, variant: int = 0) -> Trial | None:
        raise NotImplementedError

    def evaluate(self, trial: Trial, answers: dict[str, dict[str, dict[str, float]]],
                 ctx: Context) -> list[Outcome]:
        raise NotImplementedError

    # classification lives in jevbench.taxonomy, not in each class
    @property
    def group(self) -> str:
        return taxonomy.entry(self.name).group


    @property
    def edits(self) -> tuple:
        return taxonomy.entry(self.name).edits

    @property
    def law(self) -> str:
        return taxonomy.entry(self.name).law

    # helpers
    def trial(self, case, targets, requests, **params):
        return Trial(self.name, case.id, list(targets), requests, params)

    def outcome(self, trial, check, deviation, tolerance, flip=None, **detail):
        kind = "noise" if isinstance(tolerance, NoiseTolerance) else "own"
        return Outcome(self.name, check, trial.case_id, trial.targets, float(deviation), float(tolerance),
                       flip, detail, kind)


def batch_copy(case: Case) -> dict:
    return copy.deepcopy(case.questions)


def replace_question(questions: dict, key: str, new_key: str, new_q: dict) -> dict:
    """Swap one question in place, keeping every other key in its position."""
    return {(new_key if k == key else k): (new_q if k == key else v) for k, v in questions.items()}


def fresh_key(existing, stem: str) -> str:
    key, n = stem, 1
    while key in existing:
        n += 1
        key = f"{stem}_{n}"
    return key


# answers[RAW][label] holds the unparsed wire answers of each request (for relations reading output fields)
RAW = "__raw__"

REGISTRY: dict[str, Relation] = {}


def register(cls):
    REGISTRY[cls.name] = cls()
    return cls
