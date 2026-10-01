"""The data behind the JevBench website, from the saved reports of an evaluation.

    python bench/analysis/site_data.py --results RESULTS --out OUT

RESULTS holds <suite>/<model>.json[.gz] (bench/run_model.sh writes runs/<suite>/<model>.json) and
reference/<suite>/<name>.json[.gz] (bench/baselines.py). The script also reads bench/models.json,
bench/serving.json, bench/timings.json and data/gold.jsonl, and writes to OUT:

  leaderboard.json   per model: jevbench-mini scores (overall with its 95% interval and rank range,
                     dimensions, groups, relations), jevbench-240 overall where run, accuracy; and the
                     reference models
  agreement.json     how jevbench-mini reproduces jevbench-240 on the models run on both
  models.json        facts about each model, how it was served, and its first-run timing
  taxonomy.json      dimensions, groups and relations

Rank range: the ranks the 95% intervals allow. Its best end counts the models whose interval lies wholly
above, its worst end every model whose interval reaches this one's; models whose ranges overlap are not
separated. Accuracy: the base answers (each case's questions, asked once) against the gold answers of
data/gold.jsonl, over the questions whose gold is known; the most probable answer counts, and a k-way tie
earns 1/k.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
from pathlib import Path
from statistics import mean

import jevbench as jb
from jevbench import taxonomy
from jevbench.results import Report

HERE = Path(__file__).resolve().parents[2]
DIMS = [p.id for p in taxonomy.PILLARS]


def _reports(folder: Path) -> dict:
    out = {}
    for f in sorted(folder.glob("*.json*")):
        out[f.name.split(".")[0]] = Report.load(f)
    return out


# ------------------------------------------------------------------ accuracy

def _accuracy(report: Report, gold: dict, questions: dict, draws: int = 1000) -> dict:
    per_case = {}
    for cid, b in report.result["bases"].items():
        items = []
        for qid, g in gold[cid].items():
            if g == "unknown" or qid not in b["base"]:
                continue
            p, t = b["base"][qid], questions[cid][qid]["type"]
            k = ("true" if g is True else "false") if t == "noul" else str(g)
            top = max(p.values())
            winners = [a for a, v in p.items() if abs(v - top) <= 1e-9]
            items.append((1.0 / len(winners) if k in winners else 0.0, p[k]))
        per_case[cid] = items
    flat = [x for xs in per_case.values() for x in xs]
    rng, ids, boot = random.Random(0), sorted(per_case), []
    for _ in range(draws):
        xs = [a for c in (rng.choice(ids) for _ in ids) for a, _ in per_case[c]]
        boot.append(mean(xs))
    boot.sort()
    return {"accuracy": mean(a for a, _ in flat), "gold_prob": mean(g for _, g in flat), "n": len(flat),
            "ci": [boot[int(0.025 * (draws - 1))], boot[int(0.975 * (draws - 1))]]}


# ------------------------------------------------------------------ agreement

def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r, i = [0.0] * len(xs), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def _pearson(x, y):
    mx, my = mean(x), mean(y)
    sx, sy = math.sqrt(sum((a - mx) ** 2 for a in x)), math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else None


def _agreement(mini: dict, full: dict) -> dict:
    both = sorted(m for m in full if m in mini and full[m].overall is not None and mini[m].overall is not None)
    a, b = [100 * full[m].overall for m in both], [100 * mini[m].overall for m in both]
    ci = {m: [100 * v for v in full[m].scores["ci"]["overall"]] for m in both}
    pairs = list(itertools.combinations(range(len(both)), 2))
    same = [(a[i] - a[j]) * (b[i] - b[j]) > 0 for i, j in pairs]
    sep = [k for k, (i, j) in enumerate(pairs) if ci[both[i]][0] > ci[both[j]][1] or ci[both[j]][0] > ci[both[i]][1]]
    width = {s: mean(100 * (r[m].scores["ci"]["overall"][1] - r[m].scores["ci"]["overall"][0]) for m in both)
             for s, r in (("jevbench-mini", mini), ("jevbench-240", full))}
    dims = {}
    for d in DIMS:
        x, y = [100 * full[m].dimensions[d] for m in both], [100 * mini[m].dimensions[d] for m in both]
        dims[d] = {"spearman": _pearson(_ranks(x), _ranks(y)), "mean_abs_diff": mean(abs(q - p) for p, q in zip(x, y))}
    return {"models": both, "full": a, "mini": b, "pearson": _pearson(a, b), "spearman": _pearson(_ranks(a), _ranks(b)),
            "mean_diff": mean(q - p for p, q in zip(a, b)), "max_abs_diff": max(abs(q - p) for p, q in zip(a, b)),
            "pairs": len(pairs), "pairs_same_order": sum(same), "separated_pairs": len(sep),
            "separated_pairs_same_order": sum(same[k] for k in sep), "mean_ci_width": width, "dimensions": dims}


# ------------------------------------------------------------------ main

def _row(name, r: Report, acc=None):
    s = r.scores
    return {"model": name, "overall": s["overall"], "ci": s["ci"].get("overall"), "dimensions": s["pillars"],
            "groups": s["groups"], "relations": s["relations"], "accuracy": acc}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gold", default=str(HERE / "data/gold.jsonl"))
    args = ap.parse_args()
    res, out = Path(args.results), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    gold = {g["id"]: g["gold"] for g in map(json.loads, open(args.gold))}
    questions = {c.id: c.questions for c in jb.load_suite("jevbench-240").cases}
    facts = {k: v for k, v in json.loads((HERE / "bench/models.json").read_text()).items() if not k.startswith("_")}
    serving = {k: v for k, v in json.loads((HERE / "bench/serving.json").read_text()).items() if not k.startswith("_")}
    timings = {k: v for k, v in json.loads((HERE / "bench/timings.json").read_text()).items() if not k.startswith("_")}

    mini, full = _reports(res / "jevbench-mini"), _reports(res / "jevbench-240")
    rows = []
    for m, r in mini.items():
        if r.overall is None:
            continue
        row = _row(m, r, _accuracy(r, gold, questions))
        row["full"] = full[m].overall if m in full else None
        rows.append(row)
    rows.sort(key=lambda x: -x["overall"])
    for x in rows:
        lo, hi = x["ci"]
        x["rank_range"] = [sum(o["ci"][0] > hi for o in rows) + 1, sum(o["ci"][1] >= lo for o in rows)]
    refs = []
    for name, r in _reports(res / "reference" / "jevbench-mini").items():
        refs.append(_row(name, r, _accuracy(r, gold, questions)))
    refs.sort(key=lambda x: -x["overall"])
    (out / "leaderboard.json").write_text(json.dumps(
        {"suite": "jevbench-mini", "jevbench_version": jb.__version__, "tolerance": 0.05, "models": rows,
         "reference": refs}, indent=1) + "\n")
    (out / "agreement.json").write_text(json.dumps(_agreement(mini, full), indent=1) + "\n")
    models = {}
    for m in (x["model"] for x in rows):
        t = timings.get(m)
        spr = t["mini"]["seconds"] * t["replicas"] / t["mini"]["requests"] if t else None
        models[m] = {**facts[m], "serving": serving.get(m), "seconds_per_request": spr,
                     "mini_minutes": spr * 1248 / 60 if spr else None}
    (out / "models.json").write_text(json.dumps(models, indent=1, ensure_ascii=False) + "\n")
    tax = {"dimensions": [{"id": p.id, "title": p.title} for p in taxonomy.PILLARS],
           "groups": [{"id": g.id, "title": g.title} for g in taxonomy.GROUPS],
           "relations": [{"name": n, "group": taxonomy.entry(n).group, "summary": taxonomy.entry(n).summary,
                          "form": taxonomy.entry(n).law} for n in taxonomy.scored()]}
    (out / "taxonomy.json").write_text(json.dumps(tax, indent=1) + "\n")
    print(f"{len(rows)} models, {len(refs)} reference models -> {out}")


if __name__ == "__main__":
    main()
