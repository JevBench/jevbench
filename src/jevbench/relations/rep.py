"""REP, representation consistency: two questions that describe the same events.

Oracle: a bijection of the answers, P' = sigma#P. The four groups differ only in sigma.
  invariance    sigma = id: paraphrases, translations, typos, verbosity, neutral keys,
                paraphrased option descriptions, De Morgan
  equivariance  sigma relabels the answers: options reordered or renamed, two identical
                options exchanged (clone symmetry)
  binding       a surface cue (key, option id) moves while the meaning stays, or the reverse:
                the answer must follow the meaning
  type          the same question asked as another answer type (Noul as Choice, as Score)
Natural rewrites come from the suite's frozen bank (jevbench.rewrite), one per test.
"""

from __future__ import annotations

import copy
import json
import re

from jevbench.relations._shared import _CloneTrials, _DeMorganTrials, _bank, _flip
from jevbench.relations.base import Relation, batch_copy, fresh_key, register, replace_question
from jevbench.rewrite import question_source
from jevbench.schema import argmax, tv


@register
class OptionPermutation(Relation):
    name = "option_permutation"
    expectation = "Reordering Choice options (reversing Score levels) leaves each option's probability unchanged."
    source = "Invariance of the declared option set; CheckList INV (Ribeiro et al. 2020)."

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] in ("choice", "score")

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        if q["type"] == "choice":
            items = list(q["criteria"].items())
            order = list(range(len(items)))
            while order == list(range(len(items))):
                rng.shuffle(order)
            q["criteria"] = {items[i][0]: items[i][1] for i in order}
            params = {"order": order}
        else:
            q["criteria"] = list(reversed(q["criteria"]))
            params = {"order": "reversed"}
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)}, **params)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d = answers["variant"][key]
        if trial.params["order"] == "reversed":
            n = len(d)
            d = {str(n - 1 - int(k)): v for k, v in d.items()}
        return [self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), _flip(d, ctx.base[key]))]


@register
class OptionRename(Relation):
    name = "option_rename"
    deterministic = True
    expectation = "Replacing Choice option ids with neutral ids, descriptions unchanged, changes nothing."
    source = "Descriptions define the options; ids are labels (cf. Type-Safe Is Not Error-Free, 2026)."

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "choice"

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        old = list(q["criteria"])
        new = [f"option_{i + 1}" for i in range(len(old))]
        q["criteria"] = dict(zip(new, q["criteria"].values()))
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          mapping=dict(zip(new, old)))

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d = {trial.params["mapping"][k]: v for k, v in answers["variant"][key].items()}
        return [self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), _flip(d, ctx.base[key]))]


@register
class KeyRename(Relation):
    name = "key_rename"
    expectation = "Renaming a question's key to a neutral id changes nothing; the instructions define the question."
    source = "Keys are program identifiers in the wire format."

    def applicable(self, case, key, ctx):
        return True

    def build(self, case, key, rng, ctx, variant=0):
        new = fresh_key(case.questions, f"q_{rng.randrange(16 ** 6):06x}")
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, new, case.questions[key])},
                          new_key=new)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d = answers["variant"][trial.params["new_key"]]
        return [self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), _flip(d, ctx.base[key]))]


@register
class NoulAsChoice(Relation):
    name = "noul_as_choice"
    expectation = "A yes/no question gives the same P(yes) as a Noul and as a two-option Choice."
    source = "Equivalent answer types for a binary question."

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "noul"

    def build(self, case, key, rng, ctx, variant=0):
        opts = [("yes", "Yes"), ("no", "No")]
        rng.shuffle(opts)
        q = {"type": "choice", "instructions": case.questions[key]["instructions"], "criteria": dict(opts)}
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          order=[k for k, _ in opts])

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        p_choice = answers["variant"][key]["yes"]
        p_noul = ctx.base[key]["true"]
        return [self.outcome(trial, "abs_diff", abs(p_choice - p_noul), ctx.tolerance(key),
                             (p_choice > 0.5) != (p_noul > 0.5), p_choice=p_choice, p_noul=p_noul)]


@register
class DescriptionSwap(Relation):
    name = "description_swap"
    expectation = "Swapping two options' descriptions, ids fixed, moves their probabilities with the descriptions."
    source = "Options are bound to descriptions, not ids (sensitivity control)."

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "choice"

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        a, b = rng.sample(list(q["criteria"]), 2)
        q["criteria"][a], q["criteria"][b] = q["criteria"][b], q["criteria"][a]
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)}, pair=[a, b])

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        a, b = trial.params["pair"]
        d = dict(answers["variant"][key])
        d[a], d[b] = d[b], d[a]  # read back by description
        return [self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), _flip(d, ctx.base[key]),
                             base_pair=[ctx.base[key][a], ctx.base[key][b]])]


PROTECTED = {"never", "neither", "without", "cannot", "nobody", "nothing", "nowhere", "except", "unless",
             "fewer", "least", "fewest", "before", "after"}


def _typos(text, rng):
    """Swap two interior letters in up to two words of five or more letters, sparing negations and numbers."""
    words = text.split(" ")
    long = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha() and w.lower() not in PROTECTED]
    for i in rng.sample(long, min(2, len(long))):
        w = words[i]
        j = rng.randrange(1, len(w) - 2)
        words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2:]
    return " ".join(words)


SURFACE = ("lowercase", "typos", "no_punctuation")


@register
class TypoNoise(Relation):
    name = "typo_noise"
    expectation = "Lowercasing, two letter swaps, or stripping punctuation from the instructions changes nothing."
    source = "Robustness to surface noise (CheckList INV: typos)."
    templates = SURFACE

    def applicable(self, case, key, ctx):
        return True

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        text = q["instructions"]
        kind = self.templates[variant]
        if kind == "lowercase":
            new = text.lower()
        elif kind == "typos":
            new = _typos(text, rng)
        else:
            new = " ".join(re.sub(r"[^\w\s']", " ", text).split())  # keep apostrophes: "isn't" stays a negation
        if new == text:
            return None
        q["instructions"] = new
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          kind=kind, rewrite=new)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d = answers["variant"][key]
        return [self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), _flip(d, ctx.base[key]),
                             kind=trial.params["kind"])]


VERBOSE = (
    "Read the text carefully. {instructions}",
    "{instructions} Base your answer on the text.",
    "Please consider every detail of the text before answering the following question. {instructions} Take your time.",
)


@register
class Verbosity(Relation):
    name = "verbosity"
    expectation = "Wrapping the instructions in redundant, content-free guidance changes nothing."
    source = "Invariance to meaning-preserving additions (CheckList INV)."
    templates = VERBOSE

    def applicable(self, case, key, ctx):
        return True

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        q["instructions"] = self.templates[variant].format(instructions=q["instructions"])
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)})

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d = answers["variant"][key]
        return [self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), _flip(d, ctx.base[key]))]


@register
class NoulAsScore(Relation):
    name = "noul_as_score"
    expectation = "A yes/no question gives the same P(yes) as a Noul and as a two-level Score."
    source = "Equivalent answer types for a binary question."
    templates = (("No", "Yes"), ("False", "True"))

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "noul"

    def build(self, case, key, rng, ctx, variant=0):
        q = {"type": "score", "instructions": case.questions[key]["instructions"],
             "criteria": list(self.templates[variant])}
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)})

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        p_score, p_noul = answers["variant"][key]["1"], ctx.base[key]["true"]
        return [self.outcome(trial, "abs_diff", abs(p_score - p_noul), ctx.tolerance(key),
                             (p_score > 0.5) != (p_noul > 0.5), p_score=p_score, p_noul=p_noul)]


@register
class InstructionParaphrase(Relation):
    name = "instruction_paraphrase"
    needs_rewrites = True
    expectation = "A judged paraphrase of the instructions leaves the answer distribution unchanged."
    source = "Invariance to meaning-preserving rewording (CheckList INV)."
    deterministic = True

    # one rewrite per test: the first usable paraphrase in the bank's order

    def _rewrites(self, case, key, ctx):
        return _bank(ctx).get("paraphrase", question_source(case, key, "paraphrase")) if _bank(ctx) else []

    def applicable(self, case, key, ctx):
        return bool(self._rewrites(case, key, ctx))

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        q["instructions"] = self._rewrites(case, key, ctx)[0]
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          rewrite=q["instructions"])

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d, base = answers["variant"][key], ctx.base[key]
        return [self.outcome(trial, "tv", tv(d, base), ctx.tolerance(key), argmax(d) != argmax(base),
                             rewrite=trial.params["rewrite"])]


@register
class DescriptionParaphrase(Relation):
    name = "description_paraphrase"
    needs_rewrites = True
    expectation = "A judged paraphrase of one option's description leaves the answer distribution unchanged."
    source = "Invariance to meaning-preserving rewording (CheckList INV)."
    deterministic = True

    def _pairs(self, case, key, ctx):
        q = case.questions[key]
        if not _bank(ctx) or q["type"] != "choice":
            return []
        return [(o, r) for o in q["criteria"]
                for r in _bank(ctx).get("description", question_source(case, key, "description", o))]

    # one rewrite per test: the first option, in the question's order, with a usable paraphrase, and its first one

    def applicable(self, case, key, ctx):
        return bool(self._pairs(case, key, ctx))

    def build(self, case, key, rng, ctx, variant=0):
        option, text = self._pairs(case, key, ctx)[0]
        q = copy.deepcopy(case.questions[key])
        q["criteria"][option] = text
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          option=option, rewrite=text)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d, base = answers["variant"][key], ctx.base[key]
        return [self.outcome(trial, "tv", tv(d, base), ctx.tolerance(key), argmax(d) != argmax(base),
                             option=trial.params["option"], rewrite=trial.params["rewrite"])]


@register
class CrossLingual(Relation):
    name = "cross_lingual"
    needs_rewrites = True
    expectation = ("Translating a question's instructions and criteria texts (keys unchanged, state unchanged) "
                   "leaves the answer distribution unchanged.")
    source = "Language invariance of the question; the state stays in its original language."
    deterministic = True

    def _langs(self, case, key, ctx):
        if not _bank(ctx):
            return []
        return _bank(ctx).languages(question_source(case, key, "translate"))

    # one rewrite per test: the first language with a usable translation, and its first one

    def applicable(self, case, key, ctx):
        return bool(self._langs(case, key, ctx))

    def build(self, case, key, rng, ctx, variant=0):
        lang = self._langs(case, key, ctx)[0]
        t = _bank(ctx).get(lang, question_source(case, key, "translate"))[0]
        q = copy.deepcopy(case.questions[key])
        q["instructions"] = t["instructions"]
        if q["type"] != "noul":
            q["criteria"] = t["criteria"]
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          language=lang, translation=json.dumps(t, ensure_ascii=False))

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        d, base = answers["variant"][key], ctx.base[key]
        return [self.outcome(trial, "tv", tv(d, base), ctx.tolerance(key), argmax(d) != argmax(base),
                             language=trial.params["language"])]


@register
class NameDescriptionConflict(Relation):
    name = "name_description_conflict"
    expectation = ("Exchanging the ids of two options, descriptions and positions fixed, leaves each "
                   "description's probability where it was: answers follow descriptions, not ids.")
    source = "Options are bound to descriptions (cf. Type-Safe Is Not Error-Free, 2026)."

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "choice"

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        items = list(q["criteria"].items())
        i, j = sorted(rng.sample(range(len(items)), 2))
        (a, da), (b, db) = items[i], items[j]
        items[i], items[j] = (b, da), (a, db)
        q["criteria"] = dict(items)
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)}, pair=[a, b])

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        a, b = trial.params["pair"]
        d = dict(answers["variant"][key])
        d[a], d[b] = d[b], d[a]  # id b now labels description a
        return [self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), argmax(d) != argmax(ctx.base[key]))]


@register
class KeyInstructionConflict(Relation):
    name = "key_instruction_conflict"
    expectation = ("A misleading question key (negated, or swapped with another question's key) leaves the "
                   "answer unchanged: answers follow instructions, not keys.")
    source = "Keys are program identifiers in the wire format."
    templates = ("negated_key", "swapped_keys")

    def applicable(self, case, key, ctx):
        return True

    def build(self, case, key, rng, ctx, variant=0):
        qs = batch_copy(case)
        if self.templates[variant] == "negated_key":
            new = fresh_key(qs, f"not_{key}")
            return self.trial(case, [key], {"variant": replace_question(qs, key, new, qs[key])}, keys={key: new})
        others = [k for k in qs if k != key]
        if not others:
            return None
        other = rng.choice(others)
        swapped = {(other if k == key else key if k == other else k): v for k, v in qs.items()}
        return self.trial(case, [key, other], {"variant": swapped}, keys={key: other, other: key})

    def evaluate(self, trial, answers, ctx):
        out = []
        for key, sent_as in trial.params["keys"].items():
            d = answers["variant"][sent_as]
            o = self.outcome(trial, "tv", tv(d, ctx.base[key]), ctx.tolerance(key), argmax(d) != argmax(ctx.base[key]),
                             sent_as=sent_as)
            o.targets = [key]
            out.append(o)
        return out


@register
class CloneSymmetry(_CloneTrials):
    name = "clone_symmetry"
    expectation = "Two identical options (same description, different ids) receive equal probability."
    source = "Exchangeability: swapping the two copies maps the question to itself."
    rng_name = "option_clone"

    def evaluate(self, trial, answers, ctx):
        key, o, c = trial.targets[0], trial.params["option"], trial.params["clone"]
        d = answers["variant"][key]
        # TV between P and its image under the swap of o and c is |P(o) - P(c)|
        return [self.outcome(trial, "clone_symmetry", abs(d[o] - d[c]), ctx.tolerance(key),
                             p_original=d[o], p_clone=d[c])]


@register
class DeMorgan(_DeMorganTrials):
    name = "de_morgan"
    expectation = "P(not (A and B)) = P(not A or not B): the two describe the same event."
    source = "De Morgan's laws: logically equivalent propositions."

    def evaluate(self, trial, answers, ctx):
        v = answers["variant"]
        p_nand, p_ornot = (v[trial.params[k]]["true"] for k in ("nand", "or_not"))
        return [self.outcome(trial, "nand_vs_or_not", abs(p_nand - p_ornot), ctx.tolerance(*trial.targets),
                             (p_nand > 0.5) != (p_ornot > 0.5), p_nand=p_nand, p_or_not=p_ornot)]
