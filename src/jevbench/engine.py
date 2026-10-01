"""Run relations over cases: noise floor, seeded trial generation, judging, minimization.

A run has three rounds, and every request inside a round is independent, so a
round is sent with up to `concurrency` requests in flight:

  1. base      every case's questions as one request: the source output (`repeats` > 1 also
               measures the model's repeat noise, as a diagnostic)
  2. trials    every relation's transformed requests, built from the seed and the base
  3. minimize  (a diagnostic, off by default) for each violated trial, the batch reduced to its
               targets (a base, then the trial): does the violation persist without the batch?

Trials depend only on the seed and the case (never on answers), so the outcomes do
not depend on `concurrency` or on the order in which answers arrive. With a frozen
`plan` (jevbench.plan) the trials are read, not built: the run draws no random numbers.
"""

from __future__ import annotations

import hashlib
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from jevbench import __version__
from jevbench.backends import Budget, Executor
from jevbench.relations.base import RAW
from jevbench.relations import REGISTRY, Context
from jevbench.schema import Case, read_distribution, tv

def is_deterministic(rel) -> bool:
    """A relation whose trial does not depend on the random draw runs once per target and variant."""
    return rel.deterministic


def environment() -> dict:
    """Versions that can change answers: record them with every run."""
    import platform
    from importlib import metadata

    env = {"python": platform.python_version()}
    for pkg in ("httpx", "torch", "transformers"):
        try:
            env[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            pass
    return env


def trial_rng(seed: int, *parts: str) -> random.Random:
    digest = hashlib.sha256("\x1f".join([str(seed), *parts]).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def read_all(raw: dict, questions: dict) -> dict:
    return {k: read_distribution(raw[k], q) for k, q in questions.items()}



# groups whose trials are not about one question inside a batch: never minimized
NO_MINIMIZE = ("BAT.isolation", "DIAG.fields")


def _context(case: Case, raws: list, multiplier: float, floor: float, noise: dict | None = None):
    runs = [read_all(raw, case.questions) for raw in raws]
    mean = {k: {o: sum(run[k][o] for run in runs) / len(runs) for o in runs[0][k]} for k in case.questions}
    if noise is None:
        noise = {k: max(tv(run[k], mean[k]) for run in runs) for k in case.questions}
    ctx = Context(base=mean, noise=noise, noise_multiplier=multiplier, noise_floor=floor)
    ctx.raw_base = raws
    ctx.questions = case.questions
    return ctx, runs


def base_context(case: Case, executor: Executor, repeats: int, multiplier: float, floor: float,
                 noise: dict | None = None):
    raws = [executor.ask(case.state, case.questions, repeat=r) for r in range(repeats)]
    return _context(case, raws, multiplier, floor, noise)


def resolve_relations(relations=None) -> list[str]:
    """None or "all": every scored relation. Diagnostics run only when named, singly or as "diagnostics"."""
    from jevbench import taxonomy

    if relations in (None, "all"):
        return taxonomy.scored()
    if isinstance(relations, str):
        relations = [relations]
    names = []
    for r in relations:
        for n in {"all": taxonomy.scored(), "diagnostics": taxonomy.diagnostics()}.get(r, [r]):
            if n not in names:
                names.append(n)
    return names


class _Job:
    """One trial: where it came from, its requests in flight, and later its outcomes."""

    __slots__ = ("case", "name", "key", "v", "t", "rng_parts", "trial", "sent", "got", "persists", "small",
                 "small_ctx", "again", "again_sent", "frozen")

    def __init__(self, case, name, key, v, t, rng_parts, trial, sent):
        self.case, self.name, self.key, self.v, self.t = case, name, key, v, t
        self.rng_parts, self.trial, self.sent = rng_parts, trial, sent
        self.got, self.persists = None, {}
        self.small = self.small_ctx = self.again = self.again_sent = None
        self.frozen = False  # from a plan: `again` is the plan's reduced trial (None: it does not apply)


def _send(pool, executor, case, trial):
    """Submit every request of a trial, always with the case's own state.

    The state is the outside input a model is asked about; no relation may edit
    it. A trial carries questions only, so there is no way to send another state.
    """
    if "states" in trial.params:
        raise ValueError(f"{trial.relation}: relations may not replace the state")
    return {label: (qs, pool.submit(executor.ask, case.state, qs)) for label, qs in trial.requests.items()}


def _answers(sent):
    answers, raw = {}, {}
    for label, (qs, fut) in sent.items():
        raw[label] = fut.result()
        answers[label] = read_all(raw[label], qs)
    answers[RAW] = raw
    return answers


def _planned(cases, names, plan, rewrites, seed, trials) -> dict:
    """{relation: tests the run was to judge}, over every case, including cases whose base request failed:
    from the frozen plan, else built without the model (trials never depend on its answers)."""
    from jevbench.plan import _trials, sealed_context

    out = {name: set() for name in names}
    for case in cases:
        for name in names:
            if plan is not None and plan.covers(case.id, name):
                out[name] |= {(case.id, r["key"]) for r in plan.rows(case.id, name)}
                continue
            try:
                out[name] |= {(case.id, key) for key, *_ in _trials(case, name, sealed_context(rewrites), seed, trials)}
            except Exception:  # noqa: BLE001 - a relation that cannot be built without answers (diagnostics)
                pass
    return {name: len(v) for name, v in out.items()}


def run(cases, executor: Executor, *, relations=None, seed=0, repeats=1, trials=1, minimize=False,
        noise_multiplier=2.0, noise_floor=0.05, max_requests=None, progress=None, rewrites=None, concurrency=1,
        plan=None):
    names = resolve_relations(relations)
    if plan is not None and (plan.seed, plan.trials) != (seed, trials):
        raise ValueError(f"the plan was frozen with seed {plan.seed} and trials {plan.trials}")
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        raise ValueError(f"unknown relations: {unknown}")
    if max_requests is not None:
        executor.max_requests = max_requests
    started = time.time()
    outcomes, errors, bases, truncated = [], [], {}, False
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        # round 1: the source output of every case
        pending = {c.id: [pool.submit(executor.ask, c.state, c.questions, repeat=r) for r in range(repeats)]
                   for c in cases}
        ctxs = {}
        for case in cases:
            try:
                ctx, _ = _context(case, [f.result() for f in pending[case.id]], noise_multiplier, noise_floor)
                ctx.rewrites = rewrites
            except Budget:
                truncated = True
                continue
            except Exception as e:  # noqa: BLE001 - one bad case must not stop the run
                errors.append({"case": case.id, "stage": "base", "error": repr(e)})
                continue
            ctxs[case.id] = ctx
            bases[case.id] = {"base": ctx.base, "noise": ctx.noise}

        # round 2: build every trial from the seed and the base, and send its requests
        jobs = {}
        for case in cases:
            ctx = ctxs.get(case.id)
            if ctx is None:
                continue
            for name in names:
                rel = REGISTRY[name]
                batch = jobs[(case.id, name)] = []
                if plan is not None and plan.covers(case.id, name):
                    for row in plan.rows(case.id, name):
                        try:
                            trial = plan.trial(row, case)
                            job = _Job(case, name, row["key"], row["v"], row["t"], None, trial,
                                       _send(pool, executor, case, trial))
                            job.frozen, job.again = True, plan.reduced(row, case)
                            batch.append(job)
                        except Exception as e:  # noqa: BLE001 - e.g. a plan row naming a question the case lacks
                            errors.append({"case": case.id, "relation": name, "target": row.get("key"),
                                           "stage": "plan", "error": repr(e)})
                    continue
                for key in case.questions:
                    try:
                        if not rel.applicable(case, key, ctx):
                            continue
                        draws = [(v, t) for v in range(rel.variants(case, key, ctx))
                                 for t in range(1 if is_deterministic(rel) else trials)]
                    except Exception as e:  # noqa: BLE001 - one relation's bug must not stop the run
                        errors.append({"case": case.id, "relation": name, "target": key, "stage": "applicable",
                                       "error": repr(e)})
                        continue
                    for v, t in draws:
                        rng_parts = (case.id, rel.rng_name or name, key, str(t)) + ((f"v{v}",) if v else ())
                        try:
                            trial = rel.build(case, key, trial_rng(seed, *rng_parts), ctx, variant=v)
                            if trial is None:
                                continue
                            batch.append(_Job(case, name, key, v, t, rng_parts, trial,
                                              _send(pool, executor, case, trial)))
                        except Exception as e:  # noqa: BLE001
                            errors.append({"case": case.id, "relation": name, "target": key, "error": repr(e)})

        # judge the trials; a violated one is minimized by rerunning it on the reduced batch
        todo = []
        for case in cases:
            ctx = ctxs.get(case.id)
            if ctx is None:
                continue
            for name in names:
                rel = REGISTRY[name]
                for job in jobs[(case.id, name)]:
                    try:
                        job.got = rel.evaluate(job.trial, _answers(job.sent), ctx)
                    except Budget:
                        truncated = True
                        continue
                    except Exception as e:  # noqa: BLE001
                        errors.append({"case": case.id, "relation": name, "target": job.key, "error": repr(e)})
                        continue
                    if (minimize and rel.group not in NO_MINIMIZE and len(case.questions) > len(job.trial.targets)
                            and any(o.violated for o in job.got)):
                        small = Case(id=case.id, state=case.state,
                                     questions={k: case.questions[k] for k in job.trial.targets}, meta=case.meta)
                        job.small = (small, pool.submit(executor.ask, small.state, small.questions, repeat=0))
                        todo.append(job)
                if progress:
                    progress(case, name)   # as each (case, relation) is judged, while the run goes on

        # round 3: the reduced base keeps the full case's noise estimate, then the trial again
        for job in todo:
            rel, ctx = REGISTRY[job.name], ctxs[job.case.id]
            small, fut = job.small
            try:
                runs = [read_all(fut.result(), small.questions)]
                sctx = Context(base=runs[0], noise={k: ctx.noise[k] for k in small.questions},
                               noise_multiplier=noise_multiplier, noise_floor=noise_floor, rewrites=ctx.rewrites)
                if job.frozen:
                    if job.again is not None:
                        job.small_ctx, job.again_sent = sctx, _send(pool, executor, small, job.again)
                    continue
                target = job.trial.targets[0]
                if not rel.applicable(small, target, sctx) or job.v >= rel.variants(small, target, sctx):
                    continue
                again = rel.build(small, target, trial_rng(seed, *job.rng_parts), sctx, variant=job.v)
                if again is not None:
                    job.small_ctx, job.again = sctx, again
                    job.again_sent = _send(pool, executor, small, again)
            except Budget:
                truncated = True
            except Exception as e:  # noqa: BLE001
                errors.append({"case": job.case.id, "relation": job.name, "target": job.key, "stage": "minimize",
                               "error": repr(e)})
        for job in todo:
            if job.again is None or job.again_sent is None:
                continue
            try:
                result = {o.check: o.violated
                          for o in REGISTRY[job.name].evaluate(job.again, _answers(job.again_sent), job.small_ctx)}
                job.persists = {o.check: result.get(o.check) for o in job.got if o.violated}
            except Budget:
                truncated = True
            except Exception as e:  # noqa: BLE001
                errors.append({"case": job.case.id, "relation": job.name, "target": job.key, "stage": "minimize",
                               "error": repr(e)})

    for case in cases:
        if case.id not in ctxs:
            continue
        for name in names:
            for job in jobs[(case.id, name)]:
                for o in job.got or ():
                    row = asdict(o)
                    row["violated"] = o.violated
                    row["trial_id"] = f"{name}:{case.id}:{job.key}:{job.t}" + (f":v{job.v}" if job.v else "")
                    row["variant"] = job.v
                    if o.violated and o.check in job.persists:
                        row["persists_without_batch"] = job.persists[o.check]
                    outcomes.append(row)
    return {
        "jevbench_version": __version__,
        "backend": executor.backend.name,
        "environment": environment(),
        "seed": seed, "repeats": repeats, "trials": trials,
        "noise_multiplier": noise_multiplier, "noise_floor": noise_floor,
        "relations": names, "cases": [c.id for c in cases],
        "requests": executor.calls, "cache_hits": executor.cache_hits,
        "backend_seconds": round(executor.seconds, 3), "wall_seconds": round(time.time() - started, 3),
        "planned_tests": _planned(cases, names, plan, rewrites, seed, trials),
        "concurrency": concurrency, "truncated_by_budget": truncated and not executor.down,
        "backend_down": executor.down,
        "bases": bases, "outcomes": outcomes, "errors": errors,
    }
