"""Frozen test plans: every trial of a suite, generated once without any model, and stored as data.

A plan lists, for each (case, relation), the trials in the order the engine runs
them: the target, the variant, the exact requests and the relation's parameters,
plus the reduced trial that minimization reruns on the target questions alone.
With a plan, a run draws no random numbers: it sends the plan's requests and
judges the answers. The plan's SHA-256 is recorded in the suite's manifest.

Plans are built against a sealed context: a relation that read the model's base
answers or noise while building a trial would fail here, so a plan that builds
is, by construction, independent of every model.

A suite ships one plan: each relation tested exactly once per case, one target
question and one variant (template, option, pair, batch size) per test, so a suite
of n cases has 50 n tests, each one trial. See `standard_plan` for how the target
and the variant are chosen; `full` plans (every trial) are kept only for analysis.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from jevbench.relations import REGISTRY, Context, Trial
from jevbench.schema import Case

FORMAT = 1


class ModelDependent(RuntimeError):
    """A relation read model outputs while building a trial: it cannot be frozen."""


class _Sealed(dict):
    """A mapping that refuses every read: the base answers and noise do not exist yet."""

    def _refuse(self, *a, **k):
        raise ModelDependent("a trial may not depend on the model's answers")

    __getitem__ = get = items = keys = values = __iter__ = __len__ = __contains__ = _refuse


class _SealedList(list):
    """A list that refuses every read: the raw wire answers do not exist yet either."""

    def _refuse(self, *a, **k):
        raise ModelDependent("a trial may not depend on the model's answers")

    __getitem__ = __iter__ = __len__ = __contains__ = __bool__ = _refuse


def sealed_context(rewrites) -> Context:
    return Context(base=_Sealed(), noise=_Sealed(), rewrites=rewrites, raw_base=_SealedList())


def _trials(case: Case, name: str, ctx: Context, seed: int, trials: int):
    """(key, variant, trial index, rng parts, Trial) in engine order; the same code the engine runs."""
    from jevbench.engine import is_deterministic, trial_rng

    rel = REGISTRY[name]
    for key in case.questions:
        if not rel.applicable(case, key, ctx):
            continue
        for v in range(rel.variants(case, key, ctx)):
            for t in range(1 if is_deterministic(rel) else trials):
                parts = (case.id, rel.rng_name or name, key, str(t)) + ((f"v{v}",) if v else ())
                trial = rel.build(case, key, trial_rng(seed, *parts), ctx, variant=v)
                if trial is not None:
                    yield key, v, t, parts, trial


def reduced_trial(case: Case, name: str, key: str, v: int, parts, trial: Trial, rewrites, seed: int):
    """The trial rebuilt on the batch reduced to its targets, or None when it does not apply there."""
    from jevbench.engine import trial_rng

    rel = REGISTRY[name]
    small = Case(id=case.id, state=case.state, questions={k: case.questions[k] for k in trial.targets},
                 meta=case.meta)
    ctx = sealed_context(rewrites)
    target = trial.targets[0]
    if not rel.applicable(small, target, ctx) or v >= rel.variants(small, target, ctx):
        return None
    return rel.build(small, target, trial_rng(seed, *parts), ctx, variant=v)


def _q(q: dict) -> str:
    return json.dumps(q, ensure_ascii=False)  # order-preserving: option order is part of a question


def encode_requests(case: Case, requests: dict) -> dict:
    """Each request as a list of [key, question]; a question identical to one of the case's, in order
    too, is stored as {"@": its key}. Most trials change one question of the batch."""
    own = {_q(q): k for k, q in case.questions.items()}
    return {label: [[k, {"@": own[_q(q)]} if _q(q) in own else q] for k, q in qs.items()]
            for label, qs in requests.items()}


def decode_requests(case: Case, encoded: dict) -> dict:
    return {label: {k: case.questions[q["@"]] if set(q) == {"@"} else q for k, q in items}
            for label, items in encoded.items()}


class InvalidRequest(ValueError):
    """A trial would send a request that is not a well-formed batch of questions."""


def check_request(questions: dict, where: str) -> None:
    """Every question valid on its own (jevbench.schema), Score levels and Choice ids distinct."""
    from jevbench.schema import SchemaError, validate_question

    for key, q in questions.items():
        try:
            validate_question(key, q)
        except SchemaError as e:
            raise InvalidRequest(f"{where}: {e}") from None
        crit = q.get("criteria")
        if q["type"] == "score" and len(set(crit)) != len(crit):
            raise InvalidRequest(f"{where}: Score {key!r} repeats a level: {crit}")
        if q["type"] == "choice" and len(set(crit)) != len(crit):
            raise InvalidRequest(f"{where}: Choice {key!r} repeats an option id")


def build_plan(cases, relations, rewrites=None, seed: int = 0, trials: int = 1) -> dict:
    """The full plan of `relations` over `cases`. Raises ModelDependent for a relation that reads outputs."""
    from jevbench.engine import NO_MINIMIZE

    rows = []
    for case in cases:
        ctx = sealed_context(rewrites)
        for name in relations:
            rel = REGISTRY[name]
            for key, v, t, parts, trial in _trials(case, name, ctx, seed, trials):
                for label, qs in trial.requests.items():
                    check_request(qs, f"{name} on {case.id}/{key} (variant {v}, request {label!r})")
                reduced = None
                if rel.group not in NO_MINIMIZE and len(case.questions) > len(trial.targets):
                    again = reduced_trial(case, name, key, v, parts, trial, rewrites, seed)
                    if again is not None:
                        reduced = {"targets": again.targets, "requests": encode_requests(case, again.requests),
                                   "params": again.params}
                rows.append({"case": case.id, "relation": name, "key": key, "v": v, "t": t,
                             "targets": trial.targets, "requests": encode_requests(case, trial.requests),
                             "params": trial.params, "reduced": reduced})
    return {"format": FORMAT, "seed": seed, "trials": trials, "relations": list(relations),
            "cases": [c.id for c in cases], "rows": rows}


def _h(*parts) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def standard_plan(full: dict, cases) -> dict:
    """One test per relation per case, and one variant per test, chosen from the full plan without any
    random number.

    Relations that share requests (the same `rng_name`) form a group and test the same question with the
    same variant. Cases are taken in hash order. In each case, the group's target is the question of the
    case's domain bank that the group has tested least often so far (ties broken by hash); its variant
    (template, option, pair, batch size) is the next one in turn for the group in that domain, the k-th
    domain starting at the k-th variant, so a relation's tests cycle through its variants evenly within
    each domain and in total. Each chosen row is the full plan's row, byte for
    byte, with its reduced trial.
    """
    domain = {c.id: c.meta.get("domain", "") for c in cases}
    offset = {d: k for k, d in enumerate(sorted(set(domain.values())))}
    group = {r: (REGISTRY[r].rng_name or r) for r in full["relations"]}
    members = defaultdict(set)
    for r in full["relations"]:
        members[group[r]].add(r)
    rows_of = defaultdict(list)   # (relation, case) -> rows
    for row in full["rows"]:
        rows_of[(row["relation"], row["case"])].append(row)
    chosen = {}
    for g in sorted(members):
        used, turn = defaultdict(Counter), Counter()
        for case in sorted(full["cases"], key=lambda c: _h(g, "case", c)):
            per_rel = {r: {x["key"] for x in rows_of[(r, case)]} for r in members[g] if rows_of[(r, case)]}
            if not per_rel:
                continue
            common = set.intersection(*per_rel.values())
            dom = domain[case]
            picked = set()
            for r in sorted(per_rel):
                options = common or per_rel[r]    # the group's shared question when there is one
                k = min(options, key=lambda q: (used[dom][q], _h(g, case, q)))
                variants = sorted({x["v"] for x in rows_of[(r, case)] if x["key"] == k})
                v = variants[(turn[dom] + offset[dom]) % len(variants)]
                chosen[(r, case)] = next(x for x in rows_of[(r, case)] if x["key"] == k and x["v"] == v)
                picked.add(k)
            for q in picked:
                used[dom][q] += 1
            turn[dom] += 1
    rows = [row for row in full["rows"] if chosen.get((row["relation"], row["case"])) is row]
    return dict(full, rows=rows, selection="standard: one test per relation per case, one variant per test")


def relation_sample(plan, cases, per_domain: int = 2, salt: str = "mini") -> dict:
    """A smaller plan with every case kept and each relation tested on `per_domain` cases of each domain.

    Relations that share requests (the same `rng_name`) are one unit and go to the same cases. Units are
    placed in a fixed order (larger first, then by name); in each domain a unit goes to the cases with the
    fewest relations so far, then the fewest requests, ties broken by hash. Every chosen test is the
    parent plan's test, byte for byte, so a run of the sample is a run of the parent restricted to it.
    """
    unit = {r: (REGISTRY[r].rng_name or r) for r in plan.relations}
    size = Counter(unit.values())
    by_domain = defaultdict(list)
    for c in cases:
        by_domain[c.meta.get("domain", "")].append(c.id)
    requests = defaultdict(int)
    for (case, rel), rows in plan.by.items():
        requests[(unit[rel], case)] += sum(len(r["requests"]) for r in rows)
    load = defaultdict(lambda: [0, 0])
    chosen = set()
    for u in sorted(size, key=lambda u: (-size[u], u)):
        for dom in sorted(by_domain):
            ids = [i for i in by_domain[dom] if requests[(u, i)]]
            for case in sorted(ids, key=lambda i: (load[i][0], load[i][1], _h(salt, u, i)))[:per_domain]:
                chosen.add((u, case))
                load[case][0] += size[u]
                load[case][1] += requests[(u, case)]
    rows = [r for (case, rel), rs in sorted(plan.by.items()) for r in rs if (unit[rel], case) in chosen]
    order = {c.id: i for i, c in enumerate(cases)}
    rows.sort(key=lambda r: order[r["case"]])  # the engine reads rows by (case, relation); keep case order
    return {"format": FORMAT, "seed": plan.seed, "trials": plan.trials, "relations": sorted(plan.relations),
            "cases": [c.id for c in cases], "rows": rows,
            "selection": f"each relation on {per_domain} cases per domain"}


def write_plan(plan: dict, path) -> Path:
    """One header line, then one trial per line, keys in their own order (never sorted: the order of
    questions and options is what some relations test); gzip with a fixed mtime, so the bytes are
    reproducible."""
    path = Path(path)
    head = {k: v for k, v in plan.items() if k != "rows"}
    lines = [json.dumps(head, ensure_ascii=False)] + [json.dumps(r, ensure_ascii=False) for r in plan["rows"]]
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as f:
        f.write(("\n".join(lines) + "\n").encode("utf-8"))
    return path


class Plan:
    """A loaded plan: the trials of each (case, relation), ready for the engine."""

    def __init__(self, head: dict, rows: list[dict]):
        self.seed, self.trials = head["seed"], head["trials"]
        self.relations, self.cases = set(head["relations"]), set(head["cases"])
        self.by = {}
        for r in rows:
            self.by.setdefault((r["case"], r["relation"]), []).append(r)

    def __len__(self):
        return sum(len(v) for v in self.by.values())

    def covers(self, case_id: str, relation: str) -> bool:
        return case_id in self.cases and relation in self.relations

    def rows(self, case_id: str, relation: str) -> list[dict]:
        return self.by.get((case_id, relation), [])

    @staticmethod
    def trial(row: dict, case: Case) -> Trial:
        return Trial(row["relation"], row["case"], list(row["targets"]), decode_requests(case, row["requests"]),
                     row["params"])

    @staticmethod
    def reduced(row: dict, case: Case) -> Trial | None:
        r = row.get("reduced")
        if r is None:
            return None
        return Trial(row["relation"], row["case"], list(r["targets"]), decode_requests(case, r["requests"]),
                     r["params"])


def load_plan(path) -> Plan:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        head = json.loads(f.readline())
        rows = [json.loads(line) for line in f if line.strip()]
    if head.get("format") != FORMAT:
        raise ValueError(f"{path}: plan format {head.get('format')}, expected {FORMAT}")
    return Plan(head, rows)
