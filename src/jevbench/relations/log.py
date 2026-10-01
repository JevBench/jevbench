"""LOG, logical coherence: propositions ordered by entailment.

Oracle: order, A entails B implies P(A) <= P(B), and the bounds of Boolean combinations.
  bounds        Frechet bounds of conjunctions and disjunctions of two or three Nouls, and the
                bounds of "at least two of three" from the expected count
  monotonicity  stronger readings of a question, more demanding quantifiers and higher count
                thresholds never get more probability
The atomic answers are the source outputs P_q; compound propositions are probes added to the
case's batch.
"""

from __future__ import annotations

import re

from jevbench.relations._shared import _BooleanPair, _nouls, _probe
from jevbench.relations.base import Relation, batch_copy, fresh_key, register


STRONG = ("Does the text explicitly and unambiguously establish that the answer to this question is yes? "
          "Question: {instructions}")


WEAK = "Is it at least possible, given the text, that the answer to this question is yes? Question: {instructions}"


@register
class EntailmentStrength(Relation):
    name = "entailment_strength"
    expectation = ("A stronger claim cannot be more probable than a weaker one it entails: "
                   "P(explicitly established) <= P(Q) <= P(at least possible).")
    source = "Monotonicity of probability under entailment."
    deterministic = True

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "noul"

    def build(self, case, key, rng, ctx, variant=0):
        text = case.questions[key]["instructions"]
        qs = batch_copy(case)
        strong, weak = fresh_key(qs, f"{key}__strong"), fresh_key(qs, f"{key}__weak")
        qs[strong] = {"type": "noul", "criteria": None, "instructions": STRONG.format(instructions=text)}
        qs[weak] = {"type": "noul", "criteria": None, "instructions": WEAK.format(instructions=text)}
        return self.trial(case, [key], {"variant": qs}, strong=strong, weak=weak)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        a = answers["variant"]
        p, s, w = ctx.base[key]["true"], a[trial.params["strong"]]["true"], a[trial.params["weak"]]["true"]
        return [self.outcome(trial, "chain", max(0.0, s - p, p - w, s - w), ctx.tolerance(key),
                             p=p, p_strong=s, p_weak=w)]


@register
class FrechetAndUpper(_BooleanPair):
    name = "frechet_and_upper"
    expectation = "A conjunction is never more probable than either conjunct: P(A and B) <= min(P(A), P(B))."
    source = "Monotonicity under entailment (A and B entails A); conjunction fallacy (Tversky & Kahneman 1983)."

    def evaluate(self, trial, answers, ctx):
        a, b, p_and, p_or, tol = self._read(trial, answers, ctx)
        return [self.outcome(trial, "excess", max(0.0, p_and - min(a, b)), tol, a=a, b=b, p_and=p_and)]


AND3 = "Are all of the following true? (1) {a} (2) {b} (3) {c}"


TWO3 = "Are at least two of the following true? (1) {a} (2) {b} (3) {c}"


ANY3 = "Is at least one of the following true? (1) {a} (2) {b} (3) {c}"


def _triple(case, key, rng):
    others = rng.sample(_nouls(case, (key,)), 2)
    return [key] + others


class _Nary(Relation):
    """Nouls 'all of A1..A3' and 'at least one of A1..A3' for a target and two partners."""

    rng_name = "nary_conjunction"

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "noul" and len(_nouls(case)) >= 3

    def build(self, case, key, rng, ctx, variant=0):
        keys = _triple(case, key, rng)
        a, b, c = (case.questions[k]["instructions"] for k in keys)
        qs = batch_copy(case)
        return self.trial(case, keys, {"variant": qs},
                          all=_probe(qs, f"{key}__all3", AND3.format(a=a, b=b, c=c)),
                          any=_probe(qs, f"{key}__any3", ANY3.format(a=a, b=b, c=c)))

    def gap(self, ps, p_all, p_any):
        raise NotImplementedError

    def evaluate(self, trial, answers, ctx):
        v = answers["variant"]
        ps = [ctx.base[k]["true"] for k in trial.targets]
        p_all, p_any = v[trial.params["all"]]["true"], v[trial.params["any"]]["true"]
        return [self.outcome(trial, "excess", max(0.0, self.gap(ps, p_all, p_any)), ctx.tolerance(*trial.targets),
                             atomic=ps, p_all=p_all, p_any=p_any)]


@register
class NaryAndUpper(_Nary):
    name = "nary_and_upper"
    expectation = "P(all of A1..An) <= min_i P(Ai)."
    source = "Monotonicity under entailment (the conjunction entails each conjunct)."

    def gap(self, ps, p_all, p_any):
        return p_all - min(ps)


@register
class NaryAndLower(_Nary):
    name = "nary_and_lower"
    expectation = "P(all of A1..An) >= sum_i P(Ai) - (n - 1)."
    source = "Bonferroni inequality."

    def gap(self, ps, p_all, p_any):
        return sum(ps) - (len(ps) - 1) - p_all


@register
class NaryOrUpper(_Nary):
    name = "nary_or_upper"
    expectation = "P(at least one of A1..An) <= min(1, sum_i P(Ai))."
    source = "Union bound (Boole's inequality)."

    def gap(self, ps, p_all, p_any):
        return p_any - min(1.0, sum(ps))


@register
class NaryOrLower(_Nary):
    name = "nary_or_lower"
    expectation = "P(at least one of A1..An) >= max_i P(Ai)."
    source = "Monotonicity under entailment (each disjunct entails the disjunction)."

    def gap(self, ps, p_all, p_any):
        return max(ps) - p_any


@register
class QuantifierMonotonicity(Relation):
    name = "quantifier_monotonicity"
    expectation = "P(all three) <= P(at least two) <= P(at least one), for every pair of the chain."
    source = "Monotonicity of probability under entailment between counting quantifiers."

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "noul" and len(_nouls(case)) >= 3

    def build(self, case, key, rng, ctx, variant=0):
        keys = _triple(case, key, rng)
        a, b, c = (case.questions[k]["instructions"] for k in keys)
        qs = batch_copy(case)
        return self.trial(case, keys, {"variant": qs},
                          all=_probe(qs, f"{key}__q_all", AND3.format(a=a, b=b, c=c)),
                          two=_probe(qs, f"{key}__q_two", TWO3.format(a=a, b=b, c=c)),
                          any=_probe(qs, f"{key}__q_any", ANY3.format(a=a, b=b, c=c)))

    def evaluate(self, trial, answers, ctx):
        v = answers["variant"]
        p_all, p_two, p_any = (v[trial.params[k]]["true"] for k in ("all", "two", "any"))
        return [self.outcome(trial, "chain", max(0.0, p_all - p_two, p_two - p_any, p_all - p_any),
                             ctx.tolerance(*trial.targets), p_all=p_all, p_two=p_two, p_any=p_any)]


class _Count(QuantifierMonotonicity):
    rng_name = "quantifier_monotonicity"

    def gap(self, s, n, p_two):
        raise NotImplementedError

    def evaluate(self, trial, answers, ctx):
        s = sum(ctx.base[k]["true"] for k in trial.targets)
        p_two = answers["variant"][trial.params["two"]]["true"]
        return [self.outcome(trial, "excess", max(0.0, self.gap(s, len(trial.targets), p_two)),
                             ctx.tolerance(*trial.targets), expected_count=s, p_two=p_two)]


@register
class CountUpper(_Count):
    name = "count_upper"
    expectation = "P(at least two of A1..An) <= (sum_i P(Ai)) / 2."
    source = "Markov's inequality for the number N of true propositions: E[N] >= 2 P(N >= 2)."

    def gap(self, s, n, p_two):
        return p_two - s / 2.0


@register
class CountLower(_Count):
    name = "count_lower"
    expectation = "P(at least two of A1..An) >= (sum_i P(Ai) - 1) / (n - 1)."
    source = "E[N] <= 1 + (n - 1) P(N >= 2) for the number N of true propositions."

    def gap(self, s, n, p_two):
        return (s - 1.0) / (n - 1) - p_two


DIGIT_GROUPS = re.compile(r"\d+(?:[.,]\d+)*")


MORE_THAN_DIGITS = ("Count every number written with digits in the text (for example '2x502' contains two, "
                    "'$4,800' contains one). Are there more than {k} such numbers?")


MORE_THAN_SUBJECT = "According to the text, were there more than {k} {subject}?"


def _grid(value: int, width: int = 3, cap: int = 9):
    ks = sorted({max(0, value + d) for d in range(-width, width + 1)})
    if value > 20:  # large counts: probe proportional steps instead of units
        ks = sorted({int(value * f) for f in (0.25, 0.5, 0.8, 0.95)} | {value, int(value * 1.05), int(value * 1.25),
                                                                       int(value * 2)})
    return ks[:cap]


@register
class ThresholdSweep(Relation):
    name = "threshold_sweep"
    expectation = "P('more than k?') does not increase with k, for every pair of thresholds k < k'."
    source = "Monotonicity of upper tails; entailment between threshold questions."
    deterministic = True

    def applicable(self, case, key, ctx):
        return key == next(iter(case.questions))  # once per case, not per question

    def variants(self, case, key, ctx):
        return len(case.meta.get("thresholds", [])) or 1

    def build(self, case, key, rng, ctx, variant=0):
        declared = case.meta.get("thresholds", [])
        if declared:
            spec = declared[variant]
            value, template = int(spec["value"]), MORE_THAN_SUBJECT
            fmt = {"subject": spec["subject"]}
        else:
            value = len(DIGIT_GROUPS.findall(str(case.state)))
            template, fmt = MORE_THAN_DIGITS, {}
        qs = batch_copy(case)
        probes = {}
        for k in _grid(value):
            probe = fresh_key(qs, f"__more_than_{k}")
            qs[probe] = {"type": "noul", "criteria": None, "instructions": template.format(k=k, **fmt)}
            probes[k] = probe
        return self.trial(case, [key], {"variant": qs}, probes=probes, value=value,
                          subject=fmt.get("subject", "digit groups"))

    def evaluate(self, trial, answers, ctx):
        a = answers["variant"]
        ps = {int(k): a[p]["true"] for k, p in trial.params["probes"].items()}
        ks = sorted(ps)
        rises = [ps[ks[j]] - ps[ks[i]] for i in range(len(ks)) for j in range(i + 1, len(ks))]
        tol = ctx.noise_floor  # probes are new questions without their own repeat noise
        detail = dict(value=trial.params["value"], subject=trial.params["subject"],
                      curve={k: round(ps[k], 4) for k in ks})
        return [self.outcome(trial, "monotonicity", max([0.0] + rises), tol, **detail)]
