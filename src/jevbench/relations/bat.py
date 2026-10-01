"""BAT, batch independence: the question is fixed and only its companions in the request change.

Oracle: identity, P_q given batch B' = P_q given batch B: asked alone, reordered, duplicated, with
other companions, or in batches of other sizes, a question keeps its answer.
"""

from __future__ import annotations

import copy

from jevbench.relations._shared import _flip
from jevbench.relations.base import Relation, batch_copy, fresh_key, register
from jevbench.schema import tv


@register
class BatchSolo(Relation):
    name = "batch_solo"
    deterministic = True
    expectation = "A question asked alone gets the same answer as inside its batch."
    source = "Questions are evaluated independently against the shared state (Jev documentation)."

    def applicable(self, case, key, ctx):
        return len(case.questions) > 1

    def build(self, case, key, rng, ctx, variant=0):
        return self.trial(case, [key], {"variant": {key: copy.deepcopy(case.questions[key])}})

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d = answers["variant"][key]
        return [self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), _flip(d, ctx.base[key]))]


@register
class BatchOrder(Relation):
    name = "batch_order"
    deterministic = True
    expectation = "Reversing the order of questions in a batch changes no answer."
    source = "Questions are evaluated independently against the shared state (Jev documentation)."

    def applicable(self, case, key, ctx):
        return len(case.questions) > 1 and key == next(iter(case.questions))

    def build(self, case, key, rng, ctx, variant=0):
        qs = batch_copy(case)
        return self.trial(case, list(qs), {"variant": dict(reversed(list(qs.items())))})

    def evaluate(self, trial, answers, ctx):
        out = []
        for key in trial.targets:
            d = answers["variant"][key]
            o = self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), _flip(d, ctx.base[key]))
            o.targets = [key]
            out.append(o)
        return out


@register
class DuplicateQuestion(Relation):
    name = "duplicate_question"
    deterministic = True
    expectation = "The same question asked twice in one request gets the same answer both times."
    source = "Idempotence of a deterministic query; isolation between questions."

    def applicable(self, case, key, ctx):
        return True

    def build(self, case, key, rng, ctx, variant=0):
        qs = batch_copy(case)
        dup = fresh_key(qs, f"{key}__copy")
        qs[dup] = copy.deepcopy(case.questions[key])
        return self.trial(case, [key], {"variant": qs}, duplicate=dup)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        a, b = answers["variant"][key], answers["variant"][trial.params["duplicate"]]
        return [self.outcome(trial, "within_request_tv", tv(a, b), ctx.tolerance(key), _flip(a, b))]


FILLERS = (
    "Is the text longer than one sentence?",
    "Does the text mention a colour?",
    "Is the text written in the first person?",
    "Does the text contain a web address?",
    "Does the text mention a day of the week?",
    "Does the text mention an animal?",
    "Does the text contain a direct quotation?",
    "Does the text mention a city or country?",
    "Does the text use an exclamation mark?",
    "Does the text mention a food or drink?",
    "Does the text mention a musical instrument?",
    "Does the text mention the weather?",
)


@register
class BatchContent(Relation):
    name = "batch_content"
    expectation = "Replacing the other questions with unrelated fillers, batch size fixed, changes nothing."
    source = "Questions are evaluated independently against the shared state (Jev documentation)."
    deterministic = True

    def applicable(self, case, key, ctx):
        return len(case.questions) > 1

    def build(self, case, key, rng, ctx, variant=0):
        qs, n = {}, 0
        for k, q in case.questions.items():
            if k == key:
                qs[k] = copy.deepcopy(q)
            else:
                text = FILLERS[n % len(FILLERS)] + ("" if n < len(FILLERS) else f" (check {n // len(FILLERS) + 1})")
                qs[fresh_key(case.questions, f"filler_{n + 1}")] = {"type": "noul", "criteria": None,
                                                                     "instructions": text}
                n += 1
        return self.trial(case, [key], {"variant": qs})

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d = answers["variant"][key]
        return [self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), _flip(d, ctx.base[key]))]


@register
class BatchSizeSweep(Relation):
    name = "batch_size_sweep"
    expectation = "Answers asked in the first 2, 5 or 10 questions of the batch match the full batch."
    source = "Questions are evaluated independently against the shared state (Jev documentation)."
    deterministic = True

    def _sizes(self, case):
        n = len(case.questions)
        return [s for s in (2, 5, 10) if s < n]  # size 1 is batch_solo

    def applicable(self, case, key, ctx):
        return len(case.questions) >= 3 and key == next(iter(case.questions))

    def variants(self, case, key, ctx):
        return len(self._sizes(case))

    def build(self, case, key, rng, ctx, variant=0):
        size = self._sizes(case)[variant]
        keys = list(case.questions)[:size]
        return self.trial(case, keys, {"variant": {k: copy.deepcopy(case.questions[k]) for k in keys}}, size=size)

    def evaluate(self, trial, answers, ctx):
        out = []
        for key in trial.targets:
            d = answers["variant"][key]
            o = self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), _flip(d, ctx.base[key]),
                             size=trial.params["size"])
            o.targets = [key]
            out.append(o)
        return out
