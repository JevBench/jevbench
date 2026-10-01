"""Diagnostics: auxiliary response fields (confidence, routing) checked against the probabilities they
summarize. Run only when named; in no dimension and no score.
"""

from __future__ import annotations

import copy
import math

from jevbench.relations.base import RAW, Relation, batch_copy, fresh_key, register, replace_question
from jevbench.schema import read_distribution


def _candidates(dist: dict) -> dict:
    """Common definitions of a 'confidence' for a distribution."""
    ps = sorted(dist.values(), reverse=True)
    n = len(ps)
    entropy = -sum(p * math.log(p) for p in ps if p > 0)
    return {
        "max_probability": ps[0],
        "margin": ps[0] - (ps[1] if n > 1 else 0.0),
        "one_minus_normalized_entropy": 1.0 - entropy / math.log(n) if n > 1 else 1.0,
    }


@register
class ConfidenceConsistency(Relation):
    name = "confidence_consistency"
    expectation = ("A returned 'confidence' field is a fixed function of the returned probabilities: it matches "
                   "one standard definition (max probability, top-two margin, or 1 - normalized entropy) for "
                   "every question of the case.")
    source = "Internal consistency of response fields; reads the base answers, sends no request."
    deterministic = True
    field_tolerance = 0.02

    def applicable(self, case, key, ctx):
        raw = (ctx.raw_base or [{}])[0]
        return key == next(iter(case.questions)) and any("confidence" in (raw.get(k) or {}) for k in case.questions)

    def build(self, case, key, rng, ctx, variant=0):
        return self.trial(case, list(case.questions), {})

    def evaluate(self, trial, answers, ctx):
        raw = ctx.raw_base[0]
        rows = {}
        for key in trial.targets:
            ans = raw.get(key) or {}
            if "confidence" not in ans:
                continue
            fits = _candidates(read_distribution(ans, ctx.questions[key]))  # the same answer's probabilities
            rows[key] = (float(ans["confidence"]), fits)
        # the same definition must fit every question
        best, best_err = None, math.inf
        for name in ("max_probability", "margin", "one_minus_normalized_entropy"):
            err = max(abs(c - f[name]) for c, f in rows.values())
            if err < best_err:
                best, best_err = name, err
        out = []
        for key, (c, fits) in rows.items():
            o = self.outcome(trial, "fits_definition", abs(c - fits[best]), self.field_tolerance, None,
                             confidence=c, definition=best, value=fits[best])
            o.targets = [key]
            out.append(o)
        return out


@register
class RoutingStability(Relation):
    name = "routing_stability"
    expectation = ("The decision to auto-accept (confidence >= 0.8) or send to review survives a neutral key, "
                   "reversed options and asking the question alone.")
    source = "Operational consequence of invariance at the common 0.8 routing threshold."
    deterministic = True
    threshold = 0.8

    def applicable(self, case, key, ctx):
        return True

    def build(self, case, key, rng, ctx, variant=0):
        q = case.questions[key]
        requests, read = {}, {}
        new = fresh_key(case.questions, f"q_{key}_neutral")
        requests["neutral_key"] = replace_question(batch_copy(case), key, new, copy.deepcopy(q))
        read["neutral_key"] = new
        if q["type"] in ("choice", "score"):
            r = copy.deepcopy(q)
            r["criteria"] = (dict(reversed(list(q["criteria"].items()))) if q["type"] == "choice"
                             else list(reversed(q["criteria"])))
            requests["reversed_options"] = replace_question(batch_copy(case), key, key, r)
            read["reversed_options"] = key
        if len(case.questions) > 1:
            requests["solo"] = {key: copy.deepcopy(q)}
            read["solo"] = key
        return self.trial(case, [key], requests, read=read)

    def _confidence(self, raw_answer, dist):
        c = raw_answer.get("confidence") if isinstance(raw_answer, dict) else None
        return float(c) if c is not None else max(dist.values())

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        base_c = self._confidence((ctx.raw_base or [{}])[0].get(key, {}), ctx.base[key])
        routed = base_c >= self.threshold
        flips = {}
        for label, sent_as in trial.params["read"].items():
            c = self._confidence(answers[RAW][label].get(sent_as, {}), answers[label][sent_as])
            flips[label] = (c >= self.threshold) != routed
        share = sum(flips.values()) / len(flips)
        near = abs(base_c - self.threshold) <= ctx.tolerance(key)
        return [self.outcome(trial, "route_flip", share, 0.0, any(flips.values()),
                             base_confidence=base_c, auto_accept=routed, flips=flips, near_threshold=near)]
