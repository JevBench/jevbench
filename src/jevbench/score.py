"""Coherence scores per relation, group and dimension, with intervals (tables and radars: jevbench.render).

A test is one relation on one case, at the target its trial was built for (the
question in `trial_id`). Everything the trial judges belongs to that test: its
variants when a run has several (a bundled suite's plan has one), and the
outcome of every question a batch relation compares (batch_order, for example,
compares every question of the reordered batch). The test is violated if any of
them is, and its graded score is the worst one: the maximum over the law's
index, as in the definition of the measure.

Per relation (its one check):
  score  = 1 - violation rate over tests            (binary: violated or not)
  graded = 1 - mean excess beyond the tolerance      (how far past it, scaled to [0, 1])
Dimension (called a pillar in the output keys) = mean of its relation scores;
groups report the mean of their relations but add no weighting level, so
regrouping relations changes no dimension score. Overall = mean of the five
dimensions, and is not reported if a dimension has no scored relation.

Kept out of the means, and listed separately:
  - relations with fewer than `min_n` tests (default 5): too few to score;
  - exploratory relations (taxonomy `exploratory=True`);
  - diagnostics (response-field checks), which belong to no dimension;
  - checks a relation no longer scores, from older result files.

Tolerance. A run judges each trial against max(2 x repeat noise, floor), right
for testing one model but lenient to noisy ones. `tolerance="fixed"` (default)
re-judges every noise-derived check against one fixed tolerance for all
models; checks with their own tolerance keep theirs. Outcomes of relations no
longer in the registry (from older result files) are skipped and counted in
`skipped_outcomes`.

Intervals. Cases are resampled with replacement (`bootstrap` draws, fixed seed);
each draw recomputes the overall score over the same included relations. With
few cases the interval is wide and should be read as such.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from statistics import mean

from jevbench import taxonomy
from jevbench.relations import REGISTRY


# ------------------------------------------------------------------ judging

def _judge(o: dict, result: dict, tolerance="fixed", fixed: float = 0.05) -> tuple[bool, float]:
    """(violated, graded score in [0, 1]) of one outcome. A NaN deviation is a violation with graded 0."""
    kind = o.get("tolerance_kind")
    if kind is None:  # result files written before outcomes recorded their tolerance's kind
        kind = "noise" if o["tolerance"] >= result.get("noise_floor", 0.05) - 1e-12 else "own"
    tol = fixed if (tolerance == "fixed" and kind == "noise") else o["tolerance"]
    dev = o["deviation"]
    if not math.isfinite(dev):
        return True, 0.0
    excess = max(0.0, dev - tol) / (1.0 - tol) if tol < 1.0 else 0.0
    return not (dev <= tol), 1.0 - min(1.0, excess)


def _test_target(o: dict) -> str:
    """The target the outcome's trial was built for: "relation:case:target:trial[:vN]" -> target."""
    tid = o.get("trial_id")
    if tid and tid.startswith(f"{o['relation']}:{o['case_id']}:"):
        return tid[len(o["relation"]) + len(o["case_id"]) + 2:].split(":")[0]
    return o["targets"][0]   # result files written before trial ids carried the target


def _aggregate(check_values: dict) -> dict:
    """check -> value  =>  relations, groups, pillars (dimensions), overall."""
    relations = {rel: v for (rel, _check), v in check_values.items()}
    by_group, by_pillar = defaultdict(list), defaultdict(list)
    for rel, v in relations.items():
        group = REGISTRY[rel].group
        by_group[group].append(v)
        by_pillar[group.split(".")[0]].append(v)
    groups = {g.id: (mean(by_group[g.id]) if by_group.get(g.id) else None) for g in taxonomy.GROUPS}
    pillars = {p.id: (mean(by_pillar[p.id]) if by_pillar.get(p.id) else None) for p in taxonomy.PILLARS}
    complete = all(v is not None for v in pillars.values())
    return {"relations": relations, "groups": groups, "pillars": pillars,
            "overall": mean(pillars.values()) if complete else None}


def planned_tests(result: dict) -> dict | None:
    """{relation: tests the run was to judge}: recorded by the engine, else counted from the suite's frozen plan
    (result files written before the engine recorded it); None when neither is available."""
    if result.get("planned_tests"):
        return result["planned_tests"]
    suite = result.get("suite") or {}
    if not suite.get("plan"):
        return None
    try:
        from jevbench.suites import load_suite

        plan = load_suite(suite["name"]).plan
    except Exception:  # noqa: BLE001 - another version of the suite: no coverage
        return None
    cases, rels = set(result["cases"]), set(result["relations"])
    out = defaultdict(set)
    for (case, rel), rows in plan.by.items():
        if case in cases and rel in rels:
            out[rel] |= {(case, r["key"]) for r in rows}
    return {r: len(v) for r, v in out.items()}


def scores(result: dict, tolerance="fixed", fixed: float = 0.05, min_n: int = 5,
           bootstrap: int = 1000, seed: int = 0, min_coverage: float = 0.95) -> dict:
    """Scores of a run. A relation whose judged tests are fewer than `min_coverage` of its planned tests
    (requests the model refused or answered invalidly) is not scored, and neither are its dimension and the
    overall score: every model is scored on the same tests or not at all."""
    # per check, per test (case, question): the (violated, graded) of each variant
    tests = defaultdict(list)
    skipped = 0
    for o in result["outcomes"]:
        if o["relation"] not in REGISTRY:
            skipped += 1
            continue
        tests[(o["relation"], o["check"], o["case_id"], _test_target(o))].append(_judge(o, result, tolerance, fixed))
    # per check, per case: one (violated, graded) per test
    cells = defaultdict(lambda: defaultdict(list))
    for (rel, check, case_id, _target), js in tests.items():
        cells[(rel, check)][case_id].append((any(v for v, _ in js), min(g for _, g in js)))

    planned = planned_tests(result)
    checks, included, low_n, exploratory, diagnostic, incomplete = {}, [], [], [], [], []
    for key, per_case in sorted(cells.items()):
        judged = [j for js in per_case.values() for j in js]
        n = len(judged)
        row = {"n": n, "score": 1.0 - sum(v for v, _ in judged) / n, "graded": mean(g for _, g in judged)}
        if planned and planned.get(key[0]):
            row["planned"], row["coverage"] = planned[key[0]], n / planned[key[0]]
        e = taxonomy.entry(key[0])
        if e.diagnostic:
            row["excluded"] = "diagnostic"
            diagnostic.append(key)
        elif key[1] not in e.primary:
            row["excluded"] = "not the relation's check (an older result file)"
        elif taxonomy.entry(key[0]).exploratory:
            row["excluded"] = "exploratory"
            exploratory.append(key)
        elif row.get("coverage", 1.0) < min_coverage:
            row["excluded"] = f"coverage {row['coverage']:.0%} < {min_coverage:.0%}"
            incomplete.append(key[0])
        elif n < min_n:
            row["excluded"] = f"n < {min_n}"
            low_n.append(key)
        else:
            included.append(key)
        checks[f"{key[0]}/{key[1]}"] = row
    judged_rels = {k[0] for k in cells}
    for rel in sorted(set(planned or {}) - judged_rels):   # planned, but not one test judged
        if not taxonomy.entry(rel).diagnostic and planned[rel]:
            incomplete.append(rel)
            checks[f"{rel}/{taxonomy.entry(rel).primary[0]}"] = {"n": 0, "planned": planned[rel], "coverage": 0.0,
                                                                  "excluded": "coverage 0%"}

    binary = _aggregate({k: checks[f"{k[0]}/{k[1]}"]["score"] for k in included})
    graded = _aggregate({k: checks[f"{k[0]}/{k[1]}"]["graded"] for k in included})
    for agg in (binary, graded):     # an incomplete relation leaves its group, dimension and the overall unscored
        for rel in incomplete:
            group = taxonomy.entry(rel).group
            agg["groups"][group] = agg["pillars"][group.split(".")[0]] = None
        if incomplete:
            agg["overall"] = None

    case_ids = sorted({c for k in included for c in cells[k]})
    ci = {}
    if bootstrap and len(case_ids) > 1:
        rng = random.Random(seed)
        draws = defaultdict(list)
        for _ in range(bootstrap):
            sample = [rng.choice(case_ids) for _ in case_ids]
            b_vals, g_vals = {}, {}
            for k in included:
                js = [j for c in sample for j in cells[k].get(c, [])]
                if js:
                    b_vals[k] = 1.0 - sum(v for v, _ in js) / len(js)
                    g_vals[k] = mean(g for _, g in js)
            b, g = _aggregate(b_vals), _aggregate(g_vals)
            if incomplete:
                b["overall"] = g["overall"] = None
            for name, val in (("overall", b["overall"]), ("graded_overall", g["overall"])):
                if val is not None:
                    draws[name].append(val)
        for name, vals in draws.items():
            vals.sort()
            ci[name] = [vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))]]

    # repeat noise is measured only when the base was requested more than once
    noise = [v for b in result["bases"].values() for v in b["noise"].values()] if result.get("repeats", 1) > 1 else []
    return {
        "backend": result["backend"], "environment": result.get("environment"),
        "tolerance": f"fixed {fixed}" if tolerance == "fixed" else "per-run", "min_n": min_n,
        "overall": binary["overall"],
        "pillars": binary["pillars"], "groups": binary["groups"], "relations": binary["relations"],
        "graded": graded, "ci": ci, "n_cases": len(case_ids), "bootstrap": bootstrap,
        "checks": checks, "incomplete": sorted(set(incomplete)), "min_coverage": min_coverage,
        "excluded": {"low_n": [f"{r}/{c}" for r, c in low_n],
                                       "exploratory": [f"{r}/{c}" for r, c in exploratory],
                                       "diagnostic": [f"{r}/{c}" for r, c in diagnostic]},
        "n_checks": len(included), "n_outcomes": len(result["outcomes"]) - skipped, "skipped_outcomes": skipped,
        "mean_repeat_noise": mean(noise) if noise else None,
    }
