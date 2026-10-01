"""Reference models that need no GPU, scored on the bundled suites: what the scores mean at the extremes.

    python bench/baselines.py [--suites jevbench-mini,jevbench-240] [--out runs/reference]

Writes <out>/<suite>/<name>.json, the layout bench/analysis/site_data.py reads (as <results>/reference/).

  uniform        every Noul 0.5, every Choice and Score uniform: ignores the input entirely, and so keeps
                 every invariance by construction (the caveat of "what coherence does not measure")
  random         a distribution drawn afresh for every distinct (state, question), seeded by their hash:
                 deterministic, but unrelated across any two questions
  luce           the package's Luce-type toy scorer (jb.fake("coherent"), word overlap): invariant to order,
                 ids and batching
  luce-biased    the same with a first-option bias, key-name reading and batch leakage (jb.fake("biased"))
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import jevbench as jb


def _levels(q):
    return list(q["criteria"]) if q["type"] == "choice" else [str(i) for i in range(len(q["criteria"]))]


def uniform(state, questions):
    out = {}
    for key, q in questions.items():
        if q["type"] == "noul":
            out[key] = {"type": "noul", "noul": 0.5}
        else:
            ks = _levels(q)
            out[key] = {"type": q["type"], "probabilities": {k: 1.0 / len(ks) for k in ks}}
    return out


def rand(state, questions):
    out = {}
    for key, q in questions.items():
        body = {k: q.get(k) for k in ("type", "instructions", "criteria")}
        seed = hashlib.sha256(json.dumps([state, body], sort_keys=True, ensure_ascii=False).encode()).digest()
        rng = random.Random(seed)
        if q["type"] == "noul":
            out[key] = {"type": "noul", "noul": rng.random()}
        else:
            ks = _levels(q)
            w = [rng.expovariate(1.0) for _ in ks]          # Dirichlet(1, ..., 1)
            out[key] = {"type": q["type"], "probabilities": {k: x / sum(w) for k, x in zip(ks, w)}}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--suites", default="jevbench-mini,jevbench-240")
    p.add_argument("--out", default="runs/reference")
    args = p.parse_args()
    models = {
        "uniform": jb.from_callable(uniform, name="baseline-uniform", concurrent=True),
        "random": jb.from_callable(rand, name="baseline-random", concurrent=True),
        "luce": jb.fake("coherent"),
        "luce-biased": jb.fake("biased"),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for suite in args.suites.split(","):
        for name, model in models.items():
            r = jb.evaluate(model, suite, name=name, cache=None, concurrency=8)
            r.save(out / suite / f"{name}.json")
            print(f"{suite:14s} {r}", flush=True)


if __name__ == "__main__":
    main()
