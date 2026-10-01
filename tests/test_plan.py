"""Frozen test plans: one per suite, each relation tested once per case, built without any model.

A run from the plan equals a run that builds its trials; the plan is the full set of trials restricted
to one test per relation and case; freezing is byte-reproducible; bundled suites refuse any setting that
would run other tests.
"""

import hashlib
import shutil
import tempfile
from pathlib import Path

import pytest

import jevbench as jb
from jevbench.backends import Executor, FakeBiased, FakeCoherent
from jevbench.engine import run
from jevbench.plan import ModelDependent, build_plan, load_plan, write_plan
from jevbench.relations import REGISTRY
from jevbench.suites import freeze, load_suite

from _data import FOUR  # noqa: E402


@pytest.fixture(scope="module")
def four():
    return load_suite(FOUR)


def _full(suite, _cache={}):
    """Every trial of the suite, written and read back as a stored plan is (tuples become lists)."""
    if suite.path not in _cache:
        path = Path(tempfile.mkdtemp()) / "full.jsonl.gz"
        write_plan(build_plan(suite.cases, jb.select_relations(), rewrites=suite.rewrites), path)
        _cache[suite.path] = load_plan(path)
    return _cache[suite.path]


def _tests(plan):
    return {(r["relation"], r["case"], r["key"]) for rows in plan.by.values() for r in rows}


def _trials(plan):
    return {(r["relation"], r["case"], r["key"], r["v"]) for rows in plan.by.values() for r in rows}


def _trial_of(o):
    """(relation, case, target, variant) of an outcome row."""
    return o["relation"], o["case_id"], o["trial_id"].split(":")[2], o["variant"]


@pytest.mark.parametrize("backend", [FakeCoherent, FakeBiased])
@pytest.mark.parametrize("cached", [True, False])
def test_a_run_from_a_plan_equals_a_run_that_builds(tmp_path, four, backend, cached):
    kw = dict(seed=0, rewrites=four.rewrites, relations="all", concurrency=4)
    built = run(four.cases, Executor(backend(), cache_dir=tmp_path / "a" if cached else None), **kw)
    planned = run(four.cases, Executor(backend(), cache_dir=tmp_path / "b" if cached else None), plan=_full(four), **kw)
    for field in ("outcomes", "bases", "errors", "requests", "cache_hits"):
        assert built[field] == planned[field], field


def test_the_plan_tests_each_relation_once_per_case_with_one_variant(four):
    plan, full = four.plan, _full(four)
    tests = _tests(plan)
    assert tests <= _tests(full) and plan.relations == set(jb.select_relations())
    for rel in jb.select_relations():
        assert sorted(c for r, c, _ in tests if r == rel) == sorted(c.id for c in four.cases), rel
    for (case, rel), rows in plan.by.items():
        assert len(rows) == 1 and rows[0] in full.rows(case, rel)    # one trial, byte for byte the full plan's


def test_variants_are_used_in_turn():
    from collections import Counter

    plan = load_suite("jevbench-240").plan
    # relations whose variants exist on every question are used in turn, evenly (typo_noise has no typo
    # variant for questions without a word to misspell; batch_size_sweep no size 10 for smaller batches)
    for rel in ("negation_wrapper", "verbosity", "remove_option_iia", "pairwise_iia"):
        used = Counter(r["v"] for (c, rr), rows in plan.by.items() if rr == rel for r in rows)
        assert len(used) > 1 and max(used.values()) - min(used.values()) <= 2, (rel, used)


def test_the_plan_run_is_the_full_run_restricted_to_its_tests(four):
    kw = dict(seed=0, rewrites=four.rewrites, relations="all")
    full = run(four.cases, Executor(FakeBiased()), plan=_full(four), **kw)
    std = run(four.cases, Executor(FakeBiased()), plan=four.plan, **kw)
    chosen = _trials(four.plan)
    keep = [o for o in full["outcomes"] if _trial_of(o) in chosen]
    assert std["outcomes"] == keep and std["requests"] < full["requests"]


def test_freezing_is_reproducible(tmp_path, four):
    d = tmp_path / "again"
    shutil.copytree(four.path, d)
    freeze(d, full_out=tmp_path / "full.jsonl.gz")
    h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
    assert h(d / "tests.jsonl.gz") == h(four.path / "tests.jsonl.gz")
    assert (tmp_path / "full.jsonl.gz").is_file() and "full.jsonl.gz" not in load_suite(str(d)).files


def test_a_bundled_suite_runs_only_its_own_tests(four):
    kw = dict(suite=four, relations=["option_permutation"], cache=None, bootstrap=0)
    assert jb.evaluate(jb.fake(), **kw).result["suite"]["plan"] == "tests.jsonl.gz"
    for change in (dict(seed=1), dict(trials=2), dict(rewrites=four.rewrites)):
        with pytest.raises(ValueError, match="frozen"):
            jb.evaluate(jb.fake(), **kw, **change)
    own = jb.evaluate(jb.fake(), cases=four.cases, seed=1, relations=["option_permutation"], cache=None, bootstrap=0)
    assert own.result["suite"]["plan"] is None and own.relations       # your own cases: built from the seed


def test_a_relation_that_reads_answers_cannot_be_frozen(four):
    rel = REGISTRY["option_permutation"]
    orig = rel.build

    def peeking(case, key, rng, ctx, variant=0):
        ctx.base[key]  # a trial that depends on the model's answer
        return orig(case, key, rng, ctx, variant=variant)

    rel.build = peeking
    try:
        with pytest.raises(ModelDependent):
            build_plan(four.cases, ["option_permutation"])
    finally:
        rel.build = orig


def test_the_bundled_suites_test_each_relation_once_per_case():
    for name in ("examples", "jevbench-240"):          # jevbench-mini samples relations, tested below
        s = load_suite(name)
        tests = _tests(s.plan)
        for rel in jb.select_relations():
            assert sum(r == rel for r, _, _ in tests) == len(s.cases), (name, rel)


def test_mini_samples_relations_from_jevbench_240():
    from collections import Counter, defaultdict

    base, mini = load_suite("jevbench-240"), load_suite("jevbench-mini")
    assert [c.id for c in mini.cases] == [c.id for c in base.cases]
    tests = _tests(mini.plan)
    assert tests <= _tests(base.plan)
    per_rel_dom = Counter((r, base.cases[[c.id for c in base.cases].index(c)].meta["domain"]) for r, c, _ in tests)
    assert set(per_rel_dom.values()) == {2} and len(per_rel_dom) == 50 * 12   # 2 cases per domain, every relation
    per_case = defaultdict(set)
    for r, c, _ in tests:
        per_case[c].add(r)
    loads = [len(v) for v in per_case.values()]
    assert len(per_case) == 240 and max(loads) - min(loads) <= 1               # every case, balanced
    unit = {r: (REGISTRY[r].rng_name or r) for r in jb.select_relations()}
    for c, rels in per_case.items():                                          # units that share requests stay together
        for r in rels:
            assert all(o in rels for o in jb.select_relations() if unit[o] == unit[r])
    for (case, rel), rows in mini.plan.by.items():                            # byte-for-byte the parent's tests
        assert rows == base.plan.rows(case, rel)


def test_a_mini_run_is_the_240_run_restricted_to_its_tests():
    doms = ["finance_ops", "logistics"]
    kw = dict(domains=doms, cache=None, bootstrap=0)
    full = jb.evaluate(jb.fake("biased"), suite="jevbench-240", **kw).result
    mini = jb.evaluate(jb.fake("biased"), suite="jevbench-mini", **kw).result
    chosen = _trials(load_suite("jevbench-mini").plan)
    keep = [o for o in full["outcomes"] if _trial_of(o) in chosen]
    assert mini["outcomes"] == keep and mini["requests"] < full["requests"] / 5


def test_merging_score_levels_never_repeats_a_level():
    import random

    from jevbench.plan import sealed_context
    from jevbench.schema import Case

    for n in range(4, 9):
        levels = [f"L{i}" for i in range(n)]
        case = Case(id="c", state="s", questions={"q": {"type": "score", "instructions": "?", "criteria": levels}})
        trial = REGISTRY["score_granularity"].build(case, "q", random.Random(0), sealed_context(None))
        merged, blocks = trial.requests["variant"]["q"]["criteria"], trial.params["blocks"]
        assert len(set(merged)) == len(merged) and sorted(i for b in blocks for i in b) == list(range(n)), (n, blocks)


def test_freezing_refuses_an_invalid_request(four):
    from jevbench.plan import InvalidRequest

    rel = REGISTRY["score_granularity"]
    orig = rel.build

    def repeating(case, key, rng, ctx, variant=0):
        trial = orig(case, key, rng, ctx, variant=variant)
        q = trial.requests["variant"][key]
        q["criteria"] = [q["criteria"][0]] * len(q["criteria"])
        return trial

    rel.build = repeating
    try:
        with pytest.raises(InvalidRequest, match="repeats a level"):
            build_plan(four.cases, ["score_granularity"])
    finally:
        rel.build = orig
