"""Definitions shared by relations of several dimensions: templates, probes and
the unregistered trial builders two relations judge in different ways.
"""

from __future__ import annotations

import copy

from jevbench.relations.base import Relation, batch_copy, fresh_key, replace_question
from jevbench.schema import argmax


def _flip(a, b):
    return argmax(a) != argmax(b)


def _bank(ctx):
    return ctx.rewrites


def _insert_after(items, index, new_item):
    return items[: index + 1] + [new_item] + items[index + 1:]


class _CloneTrials(Relation):
    """A Choice with one option duplicated (same description, new id), inserted after it. Not
    registered: the partition law and the symmetry of the two copies judge it."""

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "choice"

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        items = list(q["criteria"].items())
        i = rng.randrange(len(items))
        o, desc = items[i]
        clone = f"{o}_alt"
        while clone in q["criteria"]:
            clone += "_"
        q["criteria"] = dict(_insert_after(items, i, (clone, desc)))
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          option=o, clone=clone)


AND = "Are both of the following true? (1) {a} (2) {b}"


OR = "Is at least one of the following true? (1) {a} (2) {b}"


TEMPLATES = (
    (AND, OR),
    ("Consider two questions. First: {a} Second: {b} Is the answer to both questions yes?",
     "Consider two questions. First: {a} Second: {b} Is the answer to at least one of them yes?"),
    ("Answer yes only if both of these are answered yes: [{a}] and [{b}]",
     "Answer yes if either of these is answered yes: [{a}] or [{b}]"),
)


class _BooleanPair(Relation):
    """Nouls 'A and B' and 'A or B' for a target A and a partner B, added to the batch.

    frechet_and_upper and inclusion_exclusion read the same requests.
    """

    rng_name = "conjunction_disjunction"
    templates = TEMPLATES

    def applicable(self, case, key, ctx):
        nouls = [k for k, q in case.questions.items() if q["type"] == "noul"]
        return case.questions[key]["type"] == "noul" and len(nouls) >= 2

    def build(self, case, key, rng, ctx, variant=0):
        partner = rng.choice([k for k, q in case.questions.items() if q["type"] == "noul" and k != key])
        a, b = (case.questions[k]["instructions"] for k in (key, partner))
        qs = batch_copy(case)
        k_and = fresh_key(qs, f"{key}__and__{partner}")
        and_t, or_t = self.templates[variant]
        qs[k_and] = {"type": "noul", "criteria": None, "instructions": and_t.format(a=a, b=b)}
        k_or = fresh_key(qs, f"{key}__or__{partner}")
        qs[k_or] = {"type": "noul", "criteria": None, "instructions": or_t.format(a=a, b=b)}
        return self.trial(case, [key, partner], {"variant": qs}, conj=k_and, disj=k_or)

    def _read(self, trial, answers, ctx):
        key, partner = trial.targets
        v = answers["variant"]
        a, b = ctx.base[key]["true"], ctx.base[partner]["true"]
        return a, b, v[trial.params["conj"]]["true"], v[trial.params["disj"]]["true"], ctx.tolerance(key, partner)


def _nouls(case, exclude=()):
    return [k for k, q in case.questions.items() if q["type"] == "noul" and k not in exclude]


def _probe(qs, stem, text):
    key = fresh_key(qs, stem)
    qs[key] = {"type": "noul", "criteria": None, "instructions": text}
    return key


class _DeMorganTrials(Relation):
    """A Noul and a partner Noul, with probes for their conjunction, its negation and the
    disjunction of their negations. Not registered: De Morgan and the compound complement judge it."""

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "noul" and len(_nouls(case)) >= 2

    def build(self, case, key, rng, ctx, variant=0):
        partner = rng.choice(_nouls(case, (key,)))
        a, b = (case.questions[k]["instructions"] for k in (key, partner))
        qs = batch_copy(case)
        keys = {
            "and": _probe(qs, f"{key}__and__{partner}", AND.format(a=a, b=b)),
            "nand": _probe(qs, f"{key}__nand__{partner}",
                           "Is it false that both of the following are true? (1) {a} (2) {b}".format(a=a, b=b)),
            "or_not": _probe(qs, f"{key}__ornot__{partner}",
                             "Is at least one of the following false? (1) {a} (2) {b}".format(a=a, b=b)),
        }
        return self.trial(case, [key, partner], {"variant": qs}, **keys)
