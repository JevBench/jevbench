"""CHO, choice-set coherence: the menu a Choice is conditioned on changes.

Oracle: restriction to a sub-menu, P'|K = P|K. A Choice is the model's distribution over its options
given that the answer is one of them, so adding an irrelevant option, removing one option or keeping
only a pair must leave the relative probabilities of the remaining options unchanged.
"""

from __future__ import annotations

import copy
from itertools import combinations
import re

from jevbench.relations.base import Relation, batch_copy, register, replace_question
from jevbench.schema import renormalized, tv


IRRELEVANT = (
    "The text is a recipe for baking sourdough bread",
    "The text describes the migration of humpback whales",
    "The text is a poem about autumn leaves",
    "The text explains the rules of chess openings",
    "The text reviews a film about medieval castles",
)


@register
class IrrelevantOption(Relation):
    name = "irrelevant_option"
    expectation = ("Adding an off-topic option leaves the distribution over the original options unchanged "
                   "after renormalisation.")
    source = "Conditioning on the original menu; Luce's choice axiom / IIA (Luce 1959)."

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "choice"

    def build(self, case, key, rng, ctx, variant=0):
        # off-topic: shares no content word with the state or with any existing option
        text = " ".join([str(case.state)] + list(case.questions[key]["criteria"].values())).lower()
        words = set(re.findall(r"[a-z]+", text))
        pool = [t for t in IRRELEVANT if not (set(re.findall(r"[a-z]{5,}", t.lower())) & words)]
        if not pool:
            return None
        q = copy.deepcopy(case.questions[key])
        items = list(q["criteria"].items())
        new = "irrelevant_option"
        while new in q["criteria"]:
            new += "_"
        pos = rng.randrange(len(items) + 1)
        items.insert(pos, (new, rng.choice(pool)))
        q["criteria"] = dict(items)
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          new=new, position=pos)

    def evaluate(self, trial, answers, ctx):
        key, new = trial.targets[0], trial.params["new"]
        d, base = answers["variant"][key], ctx.base[key]
        tol = ctx.tolerance(key)
        kept = renormalized(d, base)
        return [self.outcome(trial, "iia_tv", tv(kept, base), tol, max(kept, key=kept.get) != max(base, key=base.get),
                             p_added=d[new])]


@register
class RemoveOptionIIA(Relation):
    name = "remove_option_iia"
    expectation = ("Removing an option leaves the others with their renormalised probabilities, "
                   "for every option in turn.")
    source = "Conditioning on the smaller menu: P(a | not o) = P(a) / (1 - P(o)); Luce's choice axiom."
    deterministic = True

    def applicable(self, case, key, ctx):
        q = case.questions[key]
        return q["type"] == "choice" and len(q["criteria"]) >= 3

    def variants(self, case, key, ctx):
        return len(case.questions[key]["criteria"])

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        drop = list(q["criteria"])[variant]
        del q["criteria"][drop]
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)}, removed=drop)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d = answers["variant"][key]
        base = renormalized(ctx.base[key], d)
        return [self.outcome(trial, "iia_tv", tv(d, base), ctx.tolerance(key),
                             max(d, key=d.get) != max(base, key=base.get), removed=trial.params["removed"])]


@register
class PairwiseIIA(Relation):
    name = "pairwise_iia"
    expectation = ("Asking any two options alone gives their renormalised probabilities from the full menu, "
                   "for every pair.")
    source = "Conditioning on a two-option menu; the binary form of Luce's choice axiom."
    deterministic = True

    def _pairs(self, case, key):
        return list(combinations(case.questions[key]["criteria"], 2))

    def applicable(self, case, key, ctx):
        q = case.questions[key]
        return q["type"] == "choice" and len(q["criteria"]) >= 4  # with three, a pair is a removal

    def variants(self, case, key, ctx):
        return len(self._pairs(case, key))

    def build(self, case, key, rng, ctx, variant=0):
        a, b = self._pairs(case, key)[variant]
        q = copy.deepcopy(case.questions[key])
        q["criteria"] = {o: d for o, d in q["criteria"].items() if o in (a, b)}
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)}, pair=[a, b])

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d = answers["variant"][key]
        base = renormalized(ctx.base[key], d)
        return [self.outcome(trial, "iia_tv", tv(d, base), ctx.tolerance(key),
                             max(d, key=d.get) != max(base, key=base.get), pair=trial.params["pair"])]
