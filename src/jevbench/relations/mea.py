"""MEA, probability measure coherence: questions about different events of one measure.

Oracle: a many-to-one map of the outcomes, or the additive identity it induces.
  complement       a probe for the complement of an event (a negation, "not o", "o or lower")
                   and the source output sum to one
  partition        merging, splitting, cloning, closing or regrouping the options of a Choice, or
                   coarsening the levels of a Score, keeps the mass of every original event
  marginalisation  indicator, cumulative and joint questions are projections of the source output
Probes are added to the case's batch and compared with the source output P_q, the answer to the
case's own request.
"""

from __future__ import annotations

import copy

from jevbench.relations._shared import _BooleanPair, _CloneTrials, _DeMorganTrials, _bank, _nouls
from jevbench.relations.base import Relation, batch_copy, fresh_key, register, replace_question
from jevbench.rewrite import question_source
from jevbench.schema import tv


@register
class NaturalNegation(Relation):
    name = "natural_negation"
    needs_rewrites = True
    expectation = "P(Q) + P(Q') = 1 for a Noul Q and a judged natural rewrite Q' with the opposite answer."
    source = "Complement rule of probability."
    deterministic = True

    def _rewrites(self, case, key, ctx):
        if not _bank(ctx) or case.questions[key]["type"] != "noul":
            return []
        return _bank(ctx).get("negation", question_source(case, key, "negation"))

    # one rewrite per test: the first usable natural negation in the bank's order

    def applicable(self, case, key, ctx):
        return bool(self._rewrites(case, key, ctx))

    def build(self, case, key, rng, ctx, variant=0):
        qs = batch_copy(case)
        neg = fresh_key(qs, f"{key}__opposite")
        text = self._rewrites(case, key, ctx)[0]
        qs[neg] = {"type": "noul", "criteria": None, "instructions": text}
        return self.trial(case, [key], {"variant": qs}, negated=neg, rewrite=text)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        p = ctx.base[key]["true"]
        q = answers["variant"][trial.params["negated"]]["true"]
        return [self.outcome(trial, "complement_gap", abs(p + q - 1.0), ctx.tolerance(key),
                             (p > 0.5) == (q > 0.5), p=p, p_negated=q, rewrite=trial.params["rewrite"])]


NEGATION = ("Answer yes if the correct answer to the following question is no, and answer no "
            "if it is yes. Question: {instructions}")


NEGATIONS = (
    NEGATION,
    "Is it false that the answer to the following question is yes? Question: {instructions}",
    "Consider this question: {instructions} Would the correct answer be no?",
)


OTHER_THAN = ("Question: {instructions} Is the correct answer anything other than the following "
              "option? Option: {description}")


OTHER_THANS = (
    OTHER_THAN,
    "Question: {instructions} Is the following option the wrong answer? Option: {description}",
    "{instructions} Would it be incorrect to choose this option: {description}?",
)


IS_OPTION = "Question: {instructions} Is the correct answer the following option? Option: {description}"


IS_OPTIONS = (
    IS_OPTION,
    "{instructions} Is this the best answer: {description}?",
)


@register
class NegationWrapper(Relation):
    name = "negation_wrapper"
    deterministic = True
    expectation = "P(Q) + P(not Q) = 1 for a Noul and its logically negated wording."
    source = "Complement rule of probability."
    templates = NEGATIONS

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "noul"

    def build(self, case, key, rng, ctx, variant=0):
        qs = batch_copy(case)
        neg = fresh_key(qs, f"{key}__not")
        qs[neg] = {"type": "noul", "criteria": None,
                   "instructions": self.templates[variant].format(instructions=case.questions[key]["instructions"])}
        return self.trial(case, [key], {"variant": qs}, negated=neg)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        p = ctx.base[key]["true"]
        q = answers["variant"][trial.params["negated"]]["true"]
        return [self.outcome(trial, "complement_gap", abs(p + q - 1.0), ctx.tolerance(key),
                             (p > 0.5) == (q > 0.5), p=p, p_negated=q)]


@register
class ChoiceComplement(Relation):
    name = "choice_complement"
    expectation = "P(answer is not o), asked as a Noul, equals 1 - P(o) from the Choice."
    source = "Complement rule of probability."
    templates = OTHER_THANS

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "choice"

    def build(self, case, key, rng, ctx, variant=0):
        q = case.questions[key]
        option = rng.choice(list(q["criteria"]))
        qs = batch_copy(case)
        probe = fresh_key(qs, f"{key}__not_{option}")
        qs[probe] = {"type": "noul", "criteria": None, "instructions": self.templates[variant].format(
            instructions=q["instructions"], description=q["criteria"][option])}
        return self.trial(case, [key], {"variant": qs}, option=option, probe=probe)

    def evaluate(self, trial, answers, ctx):
        key, option = trial.targets[0], trial.params["option"]
        p = ctx.base[key][option]
        q = answers["variant"][trial.params["probe"]]["true"]
        return [self.outcome(trial, "complement_gap", abs(p + q - 1.0), ctx.tolerance(key),
                             (p > 0.5) == (q > 0.5), option=option, p_option=p, p_not_option=q)]


@register
class ChoiceIndicator(Relation):
    name = "choice_indicator"
    deterministic = True
    expectation = "For every option o, the Noul 'is the answer o?' equals P(o) from the Choice."
    source = "Marginalisation: the Noul asks for the indicator 1[answer = o] of the Choice's outcome."
    templates = IS_OPTIONS

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "choice"

    def build(self, case, key, rng, ctx, variant=0):
        q = case.questions[key]
        qs = batch_copy(case)
        probes = {}
        for option, description in q["criteria"].items():
            probe = fresh_key(qs, f"{key}__is_{option}")
            qs[probe] = {"type": "noul", "criteria": None,
                         "instructions": self.templates[variant].format(instructions=q["instructions"],
                                                                        description=description)}
            probes[option] = probe
        return self.trial(case, [key], {"variant": qs}, probes=probes)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        a, base = answers["variant"], ctx.base[key]
        ps = {o: a[p]["true"] for o, p in trial.params["probes"].items()}
        gaps = {o: abs(ps[o] - base[o]) for o in ps}
        return [self.outcome(trial, "indicator_gap", max(gaps.values()), ctx.tolerance(key), None,
                             nouls=ps, noul_sum=sum(ps.values()))]


NOT_LEVEL = (
    "Question: {instructions} The levels are: {scale}. Is the correct level anything other than '{level}'?",
    "{instructions} Scale: {scale}. Would it be wrong to choose the level '{level}'?",
)


@register
class ScoreComplement(Relation):
    name = "score_complement"
    expectation = "P(level is not k), asked as a Noul, equals 1 - P(k) from the Score."
    source = "Complement rule of probability."
    templates = NOT_LEVEL

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "score"

    def build(self, case, key, rng, ctx, variant=0):
        q = case.questions[key]
        k = rng.randrange(len(q["criteria"]))
        qs = batch_copy(case)
        probe = fresh_key(qs, f"{key}__not_level_{k}")
        qs[probe] = {"type": "noul", "criteria": None, "instructions": self.templates[variant].format(
            instructions=q["instructions"], scale=_scale(q["criteria"]), level=q["criteria"][k])}
        return self.trial(case, [key], {"variant": qs}, level=str(k), probe=probe)

    def evaluate(self, trial, answers, ctx):
        key, level = trial.targets[0], trial.params["level"]
        p = ctx.base[key][level]
        q = answers["variant"][trial.params["probe"]]["true"]
        return [self.outcome(trial, "complement_gap", abs(p + q - 1.0), ctx.tolerance(key),
                             (p > 0.5) == (q > 0.5), level=level, p_level=p, p_not_level=q)]


@register
class OptionMerge(Relation):
    name = "option_merge"
    expectation = "Merging options a and b into 'a or b' gives it P(a) + P(b) and leaves the others unchanged."
    source = "Additivity over a coarsened partition (law of total probability)."

    def applicable(self, case, key, ctx):
        q = case.questions[key]
        return q["type"] == "choice" and len(q["criteria"]) >= 3

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        items = list(q["criteria"].items())
        i, j = sorted(rng.sample(range(len(items)), 2))
        (a, da), (b, db) = items[i], items[j]
        merged = f"{a}_or_{b}"
        if merged in q["criteria"]:   # an option of that id exists already: never overwrite it
            merged = fresh_key(q["criteria"], merged)
        new = [(merged, f"Either: {da}; or: {db}") if n == i else it
               for n, it in enumerate(items) if n != j]
        q["criteria"] = dict(new)
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          merged=merged, parts=[a, b])

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        a, b = trial.params["parts"]
        base = {k: v for k, v in ctx.base[key].items() if k not in (a, b)}
        base[trial.params["merged"]] = ctx.base[key][a] + ctx.base[key][b]
        d = answers["variant"][key]
        return [self.outcome(trial, "tv_to_coarsened", tv(d, base), ctx.tolerance(key),
                             max(d, key=d.get) != max(base, key=base.get),
                             p_merged=d[trial.params["merged"]], p_parts_sum=base[trial.params["merged"]])]


@register
class OptionClone(_CloneTrials):
    name = "option_clone"
    expectation = ("Duplicating option o (same description, new id) gives the two copies P(o) together and "
                   "leaves the others unchanged.")
    source = "Additivity; clone consistency (red-bus/blue-bus, Debreu 1960)."

    def evaluate(self, trial, answers, ctx):
        key, o, c = trial.targets[0], trial.params["option"], trial.params["clone"]
        d = dict(answers["variant"][key])
        p_o, p_c = d[o], d.pop(c)
        d[o] = p_o + p_c
        tol = ctx.tolerance(key)
        return [self.outcome(trial, "tv_after_collapse", tv(d, ctx.base[key]), tol,
                             max(d, key=d.get) != max(ctx.base[key], key=ctx.base[key].get),
                             p_original=p_o, p_clone=p_c, p_base=ctx.base[key][o])]


SPLIT_PREDICATES = (
    ("the text mentions a specific number", "the text mentions no specific number"),
    ("the text mentions a date or time", "the text mentions no date or time"),
    ("the text names a person, team or organization", "the text names no person, team or organization"),
    ("the text contains a question", "the text contains no question"),
)


@register
class OptionSplit(Relation):
    name = "option_split"
    expectation = ("Splitting option o into 'o, and X' and 'o, and not X' gives the two parts P(o) in total "
                   "and leaves the other options unchanged.")
    source = ("Additivity over a refined partition; unpacking effect of support theory "
              "(Tversky & Koehler 1994), where judged parts sum to more than the whole.")

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "choice"

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        items = list(q["criteria"].items())
        i = rng.randrange(len(items))
        o, desc = items[i]
        yes, no = rng.choice(SPLIT_PREDICATES)
        parts = [f"{o}__with", f"{o}__without"]
        while any(p in q["criteria"] for p in parts):
            parts = [p + "_" for p in parts]
        new = items[:i] + [(parts[0], f"{desc}, and {yes}"), (parts[1], f"{desc}, and {no}")] + items[i + 1:]
        q["criteria"] = dict(new)
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          option=o, parts=parts, predicate=yes)

    def evaluate(self, trial, answers, ctx):
        key, o = trial.targets[0], trial.params["option"]
        d = dict(answers["variant"][key])
        with_x, without_x = (d.pop(p) for p in trial.params["parts"])
        d[o] = with_x + without_x
        base = ctx.base[key]
        # signed in detail: positive = subadditive whole, i.e. the unpacking effect
        return [self.outcome(trial, "tv_after_collapse", tv(d, base), ctx.tolerance(key),
                             max(d, key=d.get) != max(base, key=base.get),
                             parts_sum=d[o], whole=base[o], unpacking=d[o] - base[o])]


NOTA = "None of the other options is correct"


@register
class OptionClosure(Relation):
    name = "option_closure"
    expectation = ("Replacing an option o by 'none of the other options' gives the catch-all P(o) and leaves "
                   "the rest unchanged, for every option in turn.")
    source = "The catch-all relabels the event o within the menu (a Choice is conditioned on its options)."
    deterministic = True

    def applicable(self, case, key, ctx):
        q = case.questions[key]
        return q["type"] == "choice" and len(q["criteria"]) >= 3

    def variants(self, case, key, ctx):
        return len(case.questions[key]["criteria"])

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        replaced = list(q["criteria"])[variant]
        nota = "none_of_the_others"
        while nota in q["criteria"]:
            nota += "_"
        q["criteria"] = {(nota if o == replaced else o): (NOTA if o == replaced else d)
                         for o, d in q["criteria"].items()}
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          replaced=replaced, nota=nota)

    def evaluate(self, trial, answers, ctx):
        key, o, nota = trial.targets[0], trial.params["replaced"], trial.params["nota"]
        base = ctx.base[key]
        catch = answers["variant"][key]
        expected = {(nota if k == o else k): v for k, v in base.items()}
        return [self.outcome(trial, "catch_all_tv", tv(catch, expected), ctx.tolerance(key),
                             p_catch_all=catch[nota], p_replaced=base[o])]


@register
class PartitionHierarchy(Relation):
    name = "partition_hierarchy"
    expectation = ("Grouping all options into coarse blocks gives each block the sum of its options' "
                   "probabilities.")
    source = "Additivity over a coarsened partition (law of total probability)."

    def applicable(self, case, key, ctx):
        q = case.questions[key]
        declared = case.meta.get("hierarchies", {}).get(key)
        return q["type"] == "choice" and (bool(declared) or len(q["criteria"]) >= 4)

    def variants(self, case, key, ctx):
        return len(case.meta.get("hierarchies", {}).get(key, [])) or 1

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        declared = case.meta.get("hierarchies", {}).get(key)
        if declared:
            blocks = declared[variant]  # {coarse id: [fine ids]}
            fine = [o for block in blocks.values() for o in block]
            if sorted(fine) != sorted(q["criteria"]) or len(blocks) < 2:
                raise ValueError(f"{case.id}/{key}: declared hierarchy {blocks} is not a partition of its options "
                                 f"{list(q['criteria'])} into two or more blocks")
        else:
            ids = list(q["criteria"])
            rng.shuffle(ids)
            cut = len(ids) // 2
            blocks = {"block_a": sorted(ids[:cut], key=list(q["criteria"]).index),
                      "block_b": sorted(ids[cut:], key=list(q["criteria"]).index)}
        q["criteria"] = {b: "Either: " + "; or: ".join(case.questions[key]["criteria"][o] for o in fine)
                         if len(fine) > 1 else case.questions[key]["criteria"][fine[0]]
                         for b, fine in blocks.items()}
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)}, blocks=blocks)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        base = {b: sum(ctx.base[key][o] for o in fine) for b, fine in trial.params["blocks"].items()}
        d = answers["variant"][key]
        return [self.outcome(trial, "tv_to_coarsened", tv(d, base), ctx.tolerance(key),
                             max(d, key=d.get) != max(base, key=base.get), blocks=trial.params["blocks"])]


@register
class ExtremeLevel(Relation):
    name = "extreme_level"
    expectation = ("Adding a level beyond the top of a Score refines the top level: the new and the old top level "
                   "together keep P(top), and every lower level keeps its probability.")
    source = "Additivity over a refined partition; the compromise effect (Simonson 1989) moves mass to the middle."
    deterministic = True

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "score"

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        q["criteria"] = q["criteria"] + [f"Even more extreme than: {q['criteria'][-1]}"]
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          added=str(len(q["criteria"]) - 1))

    def evaluate(self, trial, answers, ctx):
        key, added = trial.targets[0], trial.params["added"]
        d, base = dict(answers["variant"][key]), ctx.base[key]
        p_new = d.pop(added)
        top = str(len(base) - 1)
        d[top] += p_new
        lower_gain = max(d[k] - base[k] for k in base if k != top)
        return [self.outcome(trial, "tv_after_collapse", tv(d, base), ctx.tolerance(key),
                             max(d, key=d.get) != max(base, key=base.get), p_added=p_new,
                             lower_level_gain=lower_gain)]


@register
class SimilarityEffect(Relation):
    name = "similarity_effect"
    expectation = ("A near-duplicate of option b, in other words, refines b: merged back into b, the "
                   "distribution equals the original one.")
    source = ("Additivity; the similarity effect (Tversky 1972): a similar newcomer takes share mainly from "
              "its twin, which a Luce scorer cannot reproduce.")

    def applicable(self, case, key, ctx):
        q = case.questions[key]
        return q["type"] == "choice" and len(q["criteria"]) >= 3

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        items = list(q["criteria"].items())
        i = rng.randrange(len(items))
        b, desc = items[i]
        twin = f"{b}__similar"
        while twin in q["criteria"]:
            twin += "_"
        items.insert(i + 1, (twin, f"Essentially the same as this: {desc}"))
        q["criteria"] = dict(items)
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)},
                          option=b, twin=twin)

    def evaluate(self, trial, answers, ctx):
        key, b, twin = trial.targets[0], trial.params["option"], trial.params["twin"]
        d, base = dict(answers["variant"][key]), ctx.base[key]
        p_twin = d.pop(twin)
        taken = {o: base[o] - d[o] for o in base}
        d[b] += p_twin
        others = max(abs(d[o] - base[o]) for o in base if o != b)
        new_mass = sum(taken.values())
        from_twin = taken[b] / new_mass if new_mass > 1e-9 else None
        tol = ctx.tolerance(key)
        return [self.outcome(trial, "tv_after_collapse", tv(d, base), tol, max(d, key=d.get) != max(base, key=base.get),
                             others_changed=others, share_taken_from_twin=from_twin, p_twin=p_twin)]


def _scale(levels):
    return "; ".join(f"{i + 1}) {t}" for i, t in enumerate(levels))


AT_LEAST = ("Question: {instructions} The levels, from lowest to highest, are: {scale}. "
            "Is the correct level '{level}' or higher?")


AT_LEASTS = (
    AT_LEAST,
    "Question: {instructions} On the scale {scale}, is the correct level at least '{level}'?",
)


@register
class ScoreCumulative(Relation):
    name = "score_cumulative"
    expectation = "For every level k, the Noul 'is it level k or higher?' equals the Score's upper tail P(level >= k)."
    source = "Marginalisation: the Noul asks for the indicator 1[level >= k] of the Score's outcome."
    deterministic = True
    templates = AT_LEASTS

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "score"

    def build(self, case, key, rng, ctx, variant=0):
        q = case.questions[key]
        qs = batch_copy(case)
        probes = {}
        for k in range(1, len(q["criteria"])):
            probe = fresh_key(qs, f"{key}__ge_{k}")
            qs[probe] = {"type": "noul", "criteria": None, "instructions": self.templates[variant].format(
                instructions=q["instructions"], scale=_scale(q["criteria"]), level=q["criteria"][k])}
            probes[k] = probe
        return self.trial(case, [key], {"variant": qs}, probes=probes)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        a, score = answers["variant"], ctx.base[key]
        n = len(score)
        tail = {k: sum(score[str(i)] for i in range(k, n)) for k in range(1, n)}
        noul = {int(k): a[p]["true"] for k, p in trial.params["probes"].items()}
        gaps = {k: abs(noul[k] - tail[k]) for k in tail}
        return [self.outcome(trial, "tail_gap_max", max(gaps.values()), ctx.tolerance(key), tails=tail, nouls=noul)]


@register
class ScoreGranularity(Relation):
    name = "score_granularity"
    expectation = "Merging adjacent Score levels into pairs gives each coarse level the sum of its fine levels."
    source = "Additivity over a coarsened ordinal scale."
    deterministic = True

    def applicable(self, case, key, ctx):
        q = case.questions[key]
        return q["type"] == "score" and len(q["criteria"]) >= 4

    def build(self, case, key, rng, ctx, variant=0):
        q = copy.deepcopy(case.questions[key])
        levels = q["criteria"]
        blocks = [list(range(i, min(i + 2, len(levels)))) for i in range(0, len(levels), 2)]
        if len(blocks[-1]) == 1 and len(blocks) > 1:  # odd count: fold the last level into its neighbour
            last = blocks.pop()                        # (not blocks[-2] += blocks.pop(): -2 is read before the pop)
            blocks[-1] = blocks[-1] + last
        # "a or b", not "Either: a; or: b": some servers read the text before a colon as the level's name
        q["criteria"] = [" or ".join(levels[i] for i in b) for b in blocks]
        return self.trial(case, [key], {"variant": replace_question(batch_copy(case), key, key, q)}, blocks=blocks)

    def evaluate(self, trial, answers, ctx):
        key = trial.targets[0]
        base = {str(j): sum(ctx.base[key][str(i)] for i in b) for j, b in enumerate(trial.params["blocks"])}
        d = answers["variant"][key]
        return [self.outcome(trial, "tv_to_coarsened", tv(d, base), ctx.tolerance(key),
                             max(d, key=d.get) != max(base, key=base.get))]


@register
class InclusionExclusion(_BooleanPair):
    name = "inclusion_exclusion"
    expectation = "P(A and B) + P(A or B) = P(A) + P(B)."
    source = "Finite additivity: the four answers are projections of one joint distribution of (A, B)."

    def evaluate(self, trial, answers, ctx):
        a, b, p_and, p_or, tol = self._read(trial, answers, ctx)
        return [self.outcome(trial, "inclusion_exclusion", abs(p_and + p_or - a - b), tol,
                             a=a, b=b, p_and=p_and, p_or=p_or)]


@register
class CompoundNegation(_DeMorganTrials):
    name = "compound_negation"
    expectation = "P(not (A and B)) + P(A and B) = 1."
    source = "Complement rule of probability, for a compound proposition."
    rng_name = "de_morgan"

    def evaluate(self, trial, answers, ctx):
        v = answers["variant"]
        p_and, p_nand = (v[trial.params[k]]["true"] for k in ("and", "nand"))
        return [self.outcome(trial, "complement_gap", abs(p_nand + p_and - 1.0), ctx.tolerance(*trial.targets),
                             (p_nand > 0.5) == (p_and > 0.5), p_and=p_and, p_nand=p_nand)]


PAIR = {
    "00": "The answer to the first question is no and the answer to the second question is no",
    "01": "The answer to the first question is no and the answer to the second question is yes",
    "10": "The answer to the first question is yes and the answer to the second question is no",
    "11": "The answer to the first question is yes and the answer to the second question is yes",
}


@register
class PairChoiceMarginals(Relation):
    name = "pair_choice_marginals"
    expectation = "A four-way Choice over the joint answers of two Nouls has the Nouls as its marginals."
    source = "Marginalisation of a joint distribution."

    def applicable(self, case, key, ctx):
        return case.questions[key]["type"] == "noul" and len(_nouls(case)) >= 2

    def build(self, case, key, rng, ctx, variant=0):
        partner = rng.choice(_nouls(case, (key,)))
        a, b = (case.questions[k]["instructions"] for k in (key, partner))
        qs = batch_copy(case)
        pair = fresh_key(qs, f"{key}__pair__{partner}")
        qs[pair] = {"type": "choice", "criteria": dict(PAIR),
                    "instructions": f"Answer two questions jointly. First question: {a} Second question: {b}"}
        return self.trial(case, [key, partner], {"variant": qs}, pair=pair)

    def evaluate(self, trial, answers, ctx):
        key, partner = trial.targets
        a, b = ctx.base[key]["true"], ctx.base[partner]["true"]
        cell = answers["variant"][trial.params["pair"]]
        pa, pb = cell["10"] + cell["11"], cell["01"] + cell["11"]
        return [self.outcome(trial, "marginal_gap", max(abs(pa - a), abs(pb - b)), ctx.tolerance(key, partner),
                             a=a, b=b, pair_a=pa, pair_b=pb)]
