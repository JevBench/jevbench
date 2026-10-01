"""Relation behavior, by dimension: toy models that satisfy or break each law, and hand-set answers.

The Luce scorer (fake:coherent) scores each option independently: invariant to ids, keys, order and
batching, and exactly IIA, but blind to negation and conjunction and additive only by accident.
fake:biased adds a first-option bias, key reading and batch-size leakage.
"""

import pytest

from jevbench.backends import Executor, FakeBiased, FakeCoherent
from jevbench.engine import run
from jevbench.relations import REGISTRY
from jevbench.results import card
from jevbench.schema import Case, load_cases

from _data import FOUR_CASES  # noqa: E402


def rates(result):
    return {(r["relation"], r["check"]): r["violation_rate"] for r in card(result)}


@pytest.fixture(scope="module")
def luce():
    result = run(FOUR_CASES, Executor(FakeCoherent()), seed=0, relations=["all", "diagnostics"])
    assert not result["errors"]
    return rates(result)


@pytest.fixture(scope="module")
def biased():
    return rates(run(FOUR_CASES, Executor(FakeBiased()), seed=0, relations=["all", "diagnostics"]))


class Table:
    """Hand-set answers. Nouls by substring rules, first match (0.5 when none); Choices by
    instructions; Scores from one fixed distribution; optional confidence field."""

    name = "table"

    def __init__(self, nouls=(), choices=None, score=None, confidence=None):
        self.nouls, self.choices, self.score, self.confidence = nouls, choices or {}, score, confidence

    def ask(self, state, questions):
        out = {}
        for k, q in questions.items():
            if q["type"] == "noul":
                out[k] = {"noul": next((v for sub, v in self.nouls if sub in q["instructions"]), 0.5)}
            elif q["type"] == "score" and self.score is not None:
                out[k] = {"probabilities": {str(i): p for i, p in enumerate(self.score)}}
            else:
                out[k] = {"probabilities": self.choices[q["instructions"]]}
            if self.confidence:
                out[k]["confidence"] = self.confidence(out[k])
        return out


class Exact:
    """Each Noul answered from a table keyed by its exact instructions (0.5 when absent)."""

    name = "exact"

    def __init__(self, table):
        self.table = table

    def ask(self, state, questions):
        return {k: {"type": "noul", "noul": self.table.get(q["instructions"], 0.5)} for k, q in questions.items()}


def nouls(*texts):
    qs = {"a": {"type": "noul", "instructions": "A?"}, "b": {"type": "noul", "instructions": "B?"}}
    for i, text in enumerate(texts):
        qs[f"x{i}"] = {"type": "noul", "instructions": text}
    return [Case(id="c", state="s", questions=qs)]


def outcomes(cases, backend, relation, **kw):
    result = run(cases, Executor(backend), relations=[relation], repeats=1, minimize=False, **kw)
    assert not result["errors"], result["errors"]
    return result["outcomes"]


def test_every_relation_documents_itself():
    for rel in REGISTRY.values():
        assert rel.group and rel.expectation and rel.source


# ------------------------------------------------------------------ REP representation consistency

def test_luce_is_invariant_and_bound_to_meaning(luce):
    for check in [("option_permutation", "tv"), ("option_rename", "tv"), ("key_rename", "tv"),
                  ("description_swap", "tv"), ("clone_symmetry", "clone_symmetry"),
                  ("name_description_conflict", "tv"), ("key_instruction_conflict", "tv")]:
        assert luce[check] == 0.0, check


def test_rep_defects_are_detected(biased):
    assert biased[("option_permutation", "tv")] > 0.5         # first-option bias
    assert biased[("description_swap", "tv")] > 0.5           # follows position, not description
    assert biased[("key_rename", "tv")] > 0.0                 # reads question keys
    assert biased[("key_instruction_conflict", "tv")] > 0.0   # keys are read
    assert biased[("option_rename", "tv")] == 0.0             # ids are not read


def test_de_morgan_accepts_coherent_and_flags_incoherent_answers():
    good = [("Is it false that both", 0.8), ("Is at least one of the following false", 0.8),
            ("Are both of the following true", 0.2), ("A?", 0.5), ("B?", 0.4)]
    bad = [("Is it false that both", 0.9), ("Is at least one of the following false", 0.3),
           ("Are both of the following true", 0.6), ("A?", 0.7), ("B?", 0.7)]
    for rel in ("de_morgan", "compound_negation"):   # compound_negation is MEA; it judges the same trials
        assert not any(o["violated"] for o in outcomes(nouls(), Table(good), rel))
    assert all(o["violated"] for o in outcomes(nouls(), Table(bad), "de_morgan"))          # 0.9 vs 0.3
    assert all(o["violated"] for o in outcomes(nouls(), Table(bad), "compound_negation"))  # 0.9 + 0.6


# ------------------------------------------------------------------ BAT batch independence

def test_luce_is_isolated(luce):
    for check in [("batch_solo", "tv"), ("batch_order", "tv"), ("duplicate_question", "within_request_tv"),
                  ("batch_content", "tv"), ("batch_size_sweep", "tv")]:
        assert luce[check] == 0.0, check


def test_batch_size_leakage_is_detected(biased):
    assert biased[("batch_solo", "tv")] > 0.0          # batch size leaks into answers
    assert biased[("batch_size_sweep", "tv")] > 0.0
    assert biased[("batch_content", "tv")] == 0.0      # same size, so no leak


# ------------------------------------------------------------------ MEA probability measure coherence

def test_luce_fails_additivity_on_refinement(luce):
    # red-bus/blue-bus: independent scores give a clone, each part of a split, a near-duplicate and a new
    # top level their own full share
    assert luce[("option_clone", "tv_after_collapse")] == 1.0
    for check in [("option_split", "tv_after_collapse"), ("option_closure", "catch_all_tv"),
                  ("similarity_effect", "tv_after_collapse"), ("extreme_level", "tv_after_collapse")]:
        assert luce[check] > 0.0, check


@pytest.mark.parametrize("p_neg,violated", [(0.3, False), (0.7, True)])
def test_negation_gap(p_neg, violated):
    from jevbench.relations.mea import NEGATION

    table = Exact({"A?": 0.7, NEGATION.format(instructions="A?"): p_neg})
    case = [Case(id="c", state="s", questions={"a": {"type": "noul", "instructions": "A?"}})]
    (o,) = [o for o in outcomes(case, table, "negation_wrapper") if o["variant"] == 0]
    assert o["violated"] is violated and o["deviation"] == pytest.approx(abs(0.7 + p_neg - 1))


def test_templates_run_as_variants():
    assert len(REGISTRY["negation_wrapper"].templates) == 3
    result = run(FOUR_CASES[:1], Executor(FakeCoherent()), relations=["negation_wrapper"], repeats=1)
    assert {o["variant"] for o in result["outcomes"]} == {0, 1, 2}


SCORE_CASE = [Case(id="s", state="x", questions={
    "lvl": {"type": "score", "instructions": "How bad?", "criteria": ["none", "low", "mid", "high"]}})]


def test_score_cumulative_accepts_exact_tails_and_flags_rising_ones():
    def tail_gap(tails):
        (o,) = [o for o in outcomes(SCORE_CASE, Table(tails, score=[0.1, 0.2, 0.3, 0.4]), "score_cumulative")
                if o["check"] == "tail_gap_max" and o["variant"] == 0]
        return o

    assert not tail_gap([("'low'", 0.9), ("'mid'", 0.7), ("'high'", 0.4)])["violated"]
    rising = tail_gap([("'low'", 0.3), ("'mid'", 0.7), ("'high'", 0.4)])
    assert rising["violated"] and rising["deviation"] == pytest.approx(0.6)   # 'low or higher': |0.3 - 0.9|


def test_pair_choice_marginals():
    pair = {"00": 0.3, "01": 0.2, "10": 0.1, "11": 0.4}
    choices = {"Answer two questions jointly. First question: A? Second question: B?": pair,
               "Answer two questions jointly. First question: B? Second question: A?": pair}
    got = {o["check"]: o for o in outcomes(nouls(), Table([("A?", 0.5), ("B?", 0.6)], choices),
                                           "pair_choice_marginals") if o["targets"] == ["a", "b"]}
    assert not got["marginal_gap"]["violated"]


def test_conjunction_fallacy_is_flagged():
    from jevbench.relations._shared import AND, OR

    table = {"A?": 0.4, "B?": 0.5, AND.format(a="A?", b="B?"): 0.8, OR.format(a="A?", b="B?"): 0.6,
             AND.format(a="B?", b="A?"): 0.2, OR.format(a="B?", b="A?"): 0.7}
    result = run(nouls(), Executor(Exact(table)), relations=["frechet_and_upper", "inclusion_exclusion"],
                 repeats=1, minimize=False)
    by = {(o["targets"][0], o["relation"]): o for o in result["outcomes"] if o["variant"] == 0}
    assert by[("a", "frechet_and_upper")]["violated"]                        # LOG: 0.8 > min(0.4, 0.5)
    assert by[("a", "frechet_and_upper")]["deviation"] == pytest.approx(0.4)
    assert not by[("b", "frechet_and_upper")]["violated"]
    assert by[("b", "inclusion_exclusion")]["deviation"] == pytest.approx(0.0)  # MEA: 0.2 + 0.7 = 0.4 + 0.5


# ------------------------------------------------------------------ LOG logical coherence

def test_quantifier_bounds_from_expected_count():
    # a = b = c = 0.9: expected count 2.7, so P(at least two) must lie in [0.85, 1]
    rules = [("Are all of the following", 0.7), ("Are at least two", 0.5), ("Is at least one", 0.99),
             ("A?", 0.9), ("B?", 0.9), ("C?", 0.9)]
    cases, table = nouls("C?"), Table(rules)
    chain = [o for o in outcomes(cases, table, "quantifier_monotonicity") if o["targets"][0] == "a"]
    assert chain[0]["violated"]                                                  # P(all) 0.7 > P(two) 0.5
    lower = [o for o in outcomes(cases, table, "count_lower") if o["targets"][0] == "a"]
    assert lower[0]["violated"] and lower[0]["deviation"] == pytest.approx(0.35)  # (2.7 - 1) / 2 - 0.5
    assert not any(o["violated"] for o in outcomes(cases, table, "count_upper"))


def test_entailment_chain():
    rules = [("explicitly and unambiguously", 0.9), ("at least possible", 0.95), ("A?", 0.6), ("B?", 0.6)]
    got = [o for o in outcomes(nouls(), Table(rules), "entailment_strength") if o["targets"] == ["a"]]
    assert got[0]["violated"] and got[0]["deviation"] == pytest.approx(0.3)


def test_threshold_sweep_uses_declared_count():
    case = [Case(id="t", state="There were 214 failed logins.", meta={"thresholds": [
        {"subject": "failed logins", "value": 214}]},
        questions={"q": {"type": "noul", "instructions": "Any failed login?"}})]
    # a perfect step: yes below 214, no at or above
    table = Table([(f"more than {k} ", 1.0 if k < 214 else 0.0) for k in range(0, 500)])
    by = {o["check"]: o for o in outcomes(case, table, "threshold_sweep")}
    assert set(by) == {"monotonicity"}
    assert by["monotonicity"]["deviation"] == 0.0 and by["monotonicity"]["detail"]["value"] == 214


# ------------------------------------------------------------------ CHO choice-set coherence

def test_luce_satisfies_conditioning(luce):
    for check in [("irrelevant_option", "iia_tv"), ("remove_option_iia", "iia_tv"), ("pairwise_iia", "iia_tv")]:
        assert luce[check] == 0.0, check


# ------------------------------------------------------------------ diagnostics (not scored)

def test_routing_is_stable_for_luce(luce):
    assert luce[("routing_stability", "route_flip")] == 0.0


def test_confidence_must_follow_one_definition():
    choice = {"Which?": {"x": 0.7, "y": 0.3}}
    case = [Case(id="c", state="s", questions={"q": {"type": "choice", "instructions": "Which?",
                                                      "criteria": {"x": "X", "y": "Y"}},
                                                "n": {"type": "noul", "instructions": "A?"}})]

    def maxp(ans):
        return max(ans["probabilities"].values()) if "probabilities" in ans else max(ans["noul"], 1 - ans["noul"])

    good = outcomes(case, Table([("A?", 0.2)], choice, confidence=maxp), "confidence_consistency")
    assert {o["detail"]["definition"] for o in good} == {"max_probability"} and not any(o["violated"] for o in good)
    bad = outcomes(case, Table([("A?", 0.2)], choice, confidence=lambda a: 0.5), "confidence_consistency")
    assert any(o["violated"] for o in bad)
