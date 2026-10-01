"""Plan balanced cases: sample facts and mentions, compute gold answers, pick a balanced subset.

No language model is involved here; a plan is fully determined by the seed.

Balance is reached greedily. A large pool of candidate cases is sampled per
domain; cases are then picked one at a time, each time the candidate that
keeps the running counts most even across: archetypes, the gold answer of
every question (yes/no for a Noul, the correct option of a Choice, the level
of a Score), with "unknown" answers held near a target share. Afterwards the
options of every Choice are rotated so the correct option lands evenly on each
position, and styles and length bands are assigned round-robin.
"""

from __future__ import annotations

import hashlib
import random
from collections import Counter, defaultdict

from jevbench.datagen.spec import MENTIONS, UNKNOWN, Domain

LENGTHS = ((80, 150), (150, 250), (250, 350))
UNKNOWN_TARGET = 0.2  # share of unknown gold answers the balancer aims for


def _rng(seed, *parts):
    h = hashlib.sha256("\x1f".join(map(str, (seed, *parts))).encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def _mentions(domain: Domain, facts: dict, rng) -> dict:
    out = {}
    for name, value in facts.items():
        if value is None:
            continue
        f = domain.fact_index[name]
        if f.always:
            out[name] = "explicit"
            continue
        if f.speech_act and value is False:  # not saying X is how a text conveys "X: no"
            out[name] = "absent"
            continue
        r = rng.random()
        if r < 0.2 and not f.never_absent:
            out[name] = "absent"
        elif r < 0.5 and f.implied_ok:
            out[name] = "implied"
        else:
            out[name] = "explicit"
    # every case states at least one count, so that threshold questions have something to probe
    counts = [n for n in out if domain.fact_index[n].kind == "int" and domain.fact_index[n].subject]
    if counts and not any(out[n] == "explicit" for n in counts):
        out[rng.choice(counts)] = "explicit"
    return out


def _pick_questions(domain: Domain, facts: dict, rng, lo=8, hi=12):
    """Applicable questions, trimmed at random to at most `hi`, keeping 4 Nouls, 2 Choices, 1 Score."""
    qs = [q for q in domain.questions if q.applies(facts)]
    need = {"noul": 4, "choice": 2, "score": 1}
    by_type = defaultdict(list)
    for q in qs:
        by_type[q.type].append(q)
    if any(len(by_type[t]) < n for t, n in need.items()) or len(qs) < lo:
        return None
    keep = list(qs)
    while len(keep) > hi:
        droppable = [q for q in keep if sum(x.type == q.type for x in keep) > need[q.type]]
        keep.remove(rng.choice(droppable))
    return keep


def candidate(domain: Domain, index: int, seed: int):
    rng = _rng(seed, domain.name, "pool", index)
    arche = rng.choice(domain.archetypes)
    facts = arche.sample(rng)
    domain.check_facts(facts)
    mention = _mentions(domain, facts, rng)
    qs = _pick_questions(domain, facts, rng)
    if qs is None:
        return None
    gold = {}
    for q in qs:
        g = q.answer(facts, mention)
        if g != UNKNOWN and q.type == "noul":
            g = bool(g)
        gold[q.key] = g
    return {"archetype": arche.name, "facts": {k: v for k, v in facts.items() if v is not None},
            "mention": mention, "question_keys": [q.key for q in qs], "gold": gold}


def _features(c):
    yield ("archetype", c["archetype"])
    for key, g in c["gold"].items():
        yield (key, "unknown" if g == UNKNOWN else str(g))


def _cost(counts, c):
    total = 0.0
    for feat, val in _features(c):
        n = counts[feat][val]
        weight = 8.0 if feat == "archetype" else 1.0  # archetypes must come out even
        if val == "unknown":  # hold unknowns near the target share instead of an even share
            seen = sum(counts[feat].values()) + 1
            weight = 3.0 if (n + 1) / seen > UNKNOWN_TARGET else 0.5
        total += weight * ((n + 1) ** 2 - n ** 2)
    return total


def plan_domain(domain: Domain, n: int, seed: int = 0, pool: int = 3000) -> list[dict]:
    cands = [c for c in (candidate(domain, i, seed) for i in range(pool)) if c is not None]
    counts = defaultdict(Counter)
    chosen = []
    for _ in range(n):
        # archetypes are a hard constraint (the least-used ones only), answers a soft one (the cost)
        low = min(counts["archetype"].get(a.name, 0) for a in domain.archetypes)
        allowed = [i for i, c in enumerate(cands) if counts["archetype"].get(c["archetype"], 0) == low]
        best = min(allowed or range(len(cands)), key=lambda i: _cost(counts, cands[i]))
        c = cands.pop(best)
        for feat, val in _features(c):
            counts[feat][val] += 1
        chosen.append(c)
    # rotate Choice options so the correct option lands evenly on each position
    position_turn = Counter()
    rng = _rng(seed, domain.name, "layout")
    qindex = {q.key: q for q in domain.questions}
    plans = []
    for i, c in enumerate(chosen):
        questions = {}
        for key in c["question_keys"]:
            q = qindex[key]
            crit = q.criteria
            if q.type == "choice":
                items = list(crit.items())
                g = c["gold"][key]
                if g == UNKNOWN:
                    shift = rng.randrange(len(items))
                else:
                    target = position_turn[key] % len(items)
                    position_turn[key] += 1
                    shift = ([k for k, _ in items].index(g) - target) % len(items)
                crit = dict(items[shift:] + items[:shift])
            questions[key] = {"type": q.type, "instructions": q.instructions,
                              **({"criteria": crit} if crit is not None else {})}
        thresholds = [{"subject": domain.fact_index[name].subject, "value": value}
                      for name, value in c["facts"].items()
                      if domain.fact_index[name].kind == "int" and domain.fact_index[name].subject
                      and c["mention"].get(name) == "explicit"]
        plans.append({
            "id": f"{domain.name}-{i + 1:03d}", "domain": domain.name, "archetype": c["archetype"],
            "style": domain.styles[i % len(domain.styles)], "length_words": LENGTHS[i % len(LENGTHS)],
            "facts": c["facts"], "mention": c["mention"], "questions": questions,
            "gold": {k: ("unknown" if v == UNKNOWN else v) for k, v in c["gold"].items()},
            "thresholds": thresholds, "seed": seed,
            "hierarchies": {k: [qindex[k].hierarchy] for k in c["question_keys"] if qindex[k].hierarchy},
        })
    return plans


def balance_report(plans: list[dict]) -> dict:
    """Counts per archetype, style, length band, mention level and per-question gold answer."""
    rep = {"cases": len(plans), "archetype": Counter(), "style": Counter(), "length": Counter(),
           "mention": Counter(), "gold": defaultdict(Counter), "choice_position": defaultdict(Counter),
           "question_types": Counter()}
    for p in plans:
        rep["archetype"][p["archetype"]] += 1
        rep["style"][p["style"]] += 1
        rep["length"][f"{p['length_words'][0]}-{p['length_words'][1]}"] += 1
        rep["mention"].update(p["mention"].values())
        for key, q in p["questions"].items():
            rep["question_types"][q["type"]] += 1
            g = p["gold"][key]
            rep["gold"][key][str(g)] += 1
            if q["type"] == "choice" and g != "unknown":
                rep["choice_position"][key][list(q["criteria"]).index(g)] += 1
    return rep


assert set(MENTIONS) == {"explicit", "implied", "absent"}
