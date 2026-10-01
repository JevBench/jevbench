"""Scores: tests merge their variants, fixed tolerance, graded excess, exclusions, bootstrap, SVG output."""

import pytest

from jevbench.backends import Executor, FakeCoherent
from jevbench.engine import run
from jevbench.schema import load_cases
from jevbench.render import radar_grid_svg, radar_svg
from jevbench.score import scores
from _data import BANK, FOUR_CASES  # noqa: E402,F401


def outcome(rel, check, deviation, tolerance, case="c", target="q", variant=0, **detail):
    return {"relation": rel, "check": check, "deviation": deviation, "tolerance": tolerance, "case_id": case,
            "targets": [target], "variant": variant, "violated": deviation > tolerance, "detail": detail}


def result(outcomes, noise=0.0):
    return {"backend": "t", "noise_floor": 0.05, "bases": {"c": {"noise": {"q": noise}}}, "outcomes": outcomes}


def plain(r, **kw):
    return scores(r, min_n=1, bootstrap=0, **kw)


# one passing relation in every dimension, so that the overall score is defined
ONE_PER_DIMENSION = [("key_rename", "tv"), ("batch_solo", "tv"), ("negation_wrapper", "complement_gap"),
                     ("frechet_and_upper", "excess"), ("irrelevant_option", "iia_tv")]


def passing(case="c", target="q"):
    return [outcome(rel, check, 0.0, 0.05, case=case, target=target) for rel, check in ONE_PER_DIMENSION]


def test_fixed_tolerance_rejudges_noise_derived_checks():
    # a noisy run passed this trial (tolerance 0.3); a fixed 0.05 tolerance fails it
    r = result([outcome("option_permutation", "tv", 0.2, 0.3)], noise=0.15)
    assert plain(r, tolerance="run")["relations"]["option_permutation"] == 1.0
    assert plain(r)["relations"]["option_permutation"] == 0.0


def test_diagnostics_keep_their_own_tolerance_and_stay_out_of_the_means():
    r = result([outcome("confidence_consistency", "fits_definition", 0.03, 0.02)] + passing())
    s = plain(r)
    assert s["checks"]["confidence_consistency/fits_definition"]["score"] == 0.0
    assert s["excluded"]["diagnostic"] == ["confidence_consistency/fits_definition"]
    assert "DIAG.fields" not in s["groups"] and s["overall"] == 1.0


def test_outcomes_of_removed_relations_are_skipped():
    r = result([outcome("chain_rule", "chain_rule", 0.9, 0.05)] + passing())
    s = plain(r)
    assert s["skipped_outcomes"] == 1 and s["overall"] == 1.0


def test_variants_of_one_test_are_judged_together():
    # three templates of one question: the test fails if any does, and counts once
    r = result([outcome("negation_wrapper", "complement_gap", d, 0.05, variant=v) for v, d in enumerate((0, 0.5, 0))]
               + [outcome("negation_wrapper", "complement_gap", 0.0, 0.05, target="q2")])
    s = plain(r)
    assert s["checks"]["negation_wrapper/complement_gap"]["n"] == 2              # two tests, not four outcomes
    assert s["relations"]["negation_wrapper"] == pytest.approx(0.5)
    assert s["graded"]["relations"]["negation_wrapper"] == pytest.approx((1 + (1 - 0.45 / 0.95)) / 2)


def test_graded_score_measures_how_far_past_the_tolerance():
    r = result([outcome("option_permutation", "tv", 0.05 + 0.95 * 0.5, 0.05),   # halfway to the maximum
                outcome("option_permutation", "tv", 0.0, 0.05, target="q2")])
    s = plain(r)
    assert s["relations"]["option_permutation"] == pytest.approx(0.5)          # one of two violated
    assert s["graded"]["relations"]["option_permutation"] == pytest.approx(0.75)  # mean of 0.5 and 1.0


def test_dimensions_average_relations_not_groups():
    # REP: option_permutation 0 (equivariance), key_rename and typo_noise 1 (invariance)
    r = result([outcome("option_permutation", "tv", 0.5, 0.05), outcome("typo_noise", "tv", 0.0, 0.05)]
               + passing())
    s = plain(r)
    assert s["groups"]["REP.equivariance"] == 0.0 and s["groups"]["REP.invariance"] == 1.0
    assert s["pillars"]["REP"] == pytest.approx(2 / 3)                         # relations, not groups (0.5)
    assert s["overall"] == pytest.approx((2 / 3 + 4) / 5)


def test_overall_needs_every_dimension():
    s = plain(result([outcome("key_rename", "tv", 0.0, 0.05)]))
    assert s["pillars"]["REP"] == 1.0 and s["pillars"]["CHO"] is None and s["overall"] is None


def test_low_n_relations_are_left_out():
    r = result([outcome("option_rename", "tv", 0.1, 0.05)] +
               [outcome("option_permutation", "tv", 0.0, 0.05, target=f"q{i}") for i in range(5)])
    s = scores(r, min_n=5, bootstrap=0)
    assert s["groups"]["REP.equivariance"] == 1.0                              # the one-test relation is excluded
    assert s["excluded"]["low_n"] == ["option_rename/tv"]
    assert s["checks"]["option_rename/tv"]["score"] == 0.0                     # still reported


def test_bootstrap_interval_brackets_the_estimate():
    outs = []
    for c in "abcdefgh":
        outs += [outcome("option_permutation", "tv", 0.2 if c in "ab" else 0.0, 0.05, case=c)] + passing(case=c)
    s = scores(result(outs), min_n=1, bootstrap=500)
    lo, hi = s["ci"]["overall"]
    assert lo <= s["overall"] <= hi and lo < hi and s["n_cases"] == 8


def test_radars_render_for_real_runs():
    res = run(FOUR_CASES[:1], Executor(FakeCoherent()), repeats=1)
    s = scores(res, min_n=1, bootstrap=0)
    svg = radar_svg({"luce": s})
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>") and "luce: overall" in svg
    grid = radar_grid_svg({"a": s, "b": s, "c": s}, cols=2, family={"a": "encoder", "b": "decoder"})
    assert grid.count("overall") == 3 and "encoder" in grid and grid.rstrip().endswith("</svg>")


def test_a_trial_is_one_test_even_when_it_judges_every_question_of_a_batch():
    import jevbench as jb

    # jevbench-mini on two domains: each relation on 2 cases per domain, so 4 tests each, whatever the relation
    r = jb.evaluate(jb.fake("biased"), suite="jevbench-mini", domains=["finance_ops", "logistics"], cache=None,
                    bootstrap=0, min_n=1)
    n = {k.split("/")[0]: v["n"] for k, v in r.scores["checks"].items()}
    assert set(n.values()) == {4} and len(n) == 50
    batch = [o for o in r.result["outcomes"] if o["relation"] == "batch_order"]
    assert len(batch) > 4                     # batch_order judges every question of the reordered batch ...
    assert n["batch_order"] == 4              # ... and each trial is still one test
