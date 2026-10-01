"""The Python API: connect a model, pick what to test, evaluate, compare.

    import jevbench as jb

    model = jb.systemone("http://localhost:8000/v1/systemone", model="my-model")
    report = jb.evaluate(model)                                  # the full suite, every relation
    report = jb.evaluate(model, domains=["finance_ops"],         # cases of some domains
                         dimensions=["MEA"], groups=["CHO.conditioning"], relations=["option_clone"])
    print(report.table())
    report.save("my-model.json")

`domains` selects cases; `dimensions`, `groups` and `relations` select relations
(their union, in taxonomy order). The overall score is reported only when every
dimension was tested.
"""

from __future__ import annotations

import sys
import threading
import warnings
from pathlib import Path

from jevbench import taxonomy
from jevbench.backends import (CallableBackend, Executor, FakeBiased, FakeCoherent, ModelError, Refused,
                               SystemOneHTTP)
from jevbench.engine import run
from jevbench.results import Report
from jevbench.schema import FORMAT_URL, AnswerFormatError, Case, load_cases
from jevbench.suites import PLAN as PLAN_NAME
from jevbench.suites import load_suite

# ------------------------------------------------------------------ models


def systemone(url, model: str, api_key: str | None = None, api_key_env: str | None = "JEVBENCH_API_KEY",
              timeout: float = 180.0, min_interval: float = 0.0, per_replica: int = 1,
              revision: str | None = None) -> SystemOneHTTP:
    """A model behind `POST /v1/systemone`. `url` may list several replicas of the same model
    (a list or comma-separated): each request takes a free replica, and a replica never has
    more than `per_replica` requests at once (1 keeps the answers of a sequential run). The
    bearer token is `api_key`, else the environment variable `api_key_env` when set. `revision` names the
    model's version in the request cache, so a new checkpoint never reads an old one's answers."""
    import os

    key = api_key or (os.environ.get(api_key_env) if api_key_env else None)
    return SystemOneHTTP(url, model, api_key=key, timeout=timeout, min_interval=min_interval,
                         per_replica=per_replica, revision=revision)


def from_callable(fn, name: str | None = None, concurrent: bool = False) -> CallableBackend:
    """A model in this process: any function `fn(state, questions) -> answers` in the System One
    wire format, or a list of such functions, one per replica (for example one per GPU).

    name        the model's name, and its key in the request cache: give each model (and each
                version of it) its own. Without a name, answers are cached for this run only.
    concurrent  a single function that may be called from several threads at once."""
    return CallableBackend(fn, name=name, concurrent=concurrent)


def fake(kind: str = "coherent"):
    """Deterministic toy models for trying the tool: "coherent" (a Luce scorer) or "biased"."""
    return {"coherent": FakeCoherent, "biased": FakeBiased}[kind]()


def _as_backend(model):
    if hasattr(model, "ask") and hasattr(model, "name"):
        return model
    if callable(model):
        return from_callable(model)
    raise TypeError("model must be a backend (jb.systemone, jb.from_callable, jb.fake) or a function "
                    "(state, questions) -> answers")


# ------------------------------------------------------------------ the taxonomy


def list_dimensions() -> list[dict]:
    return [{"id": p.id, "title": p.title, "law": p.oracle} for p in taxonomy.PILLARS]


def list_groups(dimension: str | None = None) -> list[dict]:
    return [{"id": g.id, "title": g.title, "dimension": g.pillar, "question": g.question}
            for g in taxonomy.GROUPS if dimension in (None, g.pillar)]


def list_relations(dimension: str | None = None, group: str | None = None, diagnostics: bool = False) -> list[dict]:
    names = taxonomy.scored() + (taxonomy.diagnostics() if diagnostics else [])
    return [describe(n) for n in names
            if group in (None, taxonomy.entry(n).group) and dimension in (None, taxonomy.entry(n).group.split(".")[0])]


def describe(relation: str) -> dict:
    e = taxonomy.entry(relation)
    return {"name": e.name, "group": e.group, "dimension": e.group.split(".")[0], "form": e.law,
            "edits": list(e.edits), "summary": e.summary, "check": e.primary[0], "diagnostic": e.diagnostic}


def select_relations(dimensions=None, groups=None, relations=None, diagnostics: bool = False) -> list[str]:
    """The union of the named dimensions, groups and relations, in taxonomy order; every scored
    relation when none is named. Diagnostics are added only on request."""
    scored, diag = taxonomy.scored(), taxonomy.diagnostics()
    relations = list(relations or ())
    if "all" in relations:      # the names "all" and "diagnostics" stand for those sets, as in `jevbench run`
        relations = [r for r in relations if r != "all"] + scored
    if "diagnostics" in relations:
        relations = [r for r in relations if r != "diagnostics"] + diag
    relations = relations or None
    known_dims = [p.id for p in taxonomy.PILLARS]
    known_groups = [g.id for g in taxonomy.GROUPS]
    for kind, asked, known in (("dimensions", dimensions, known_dims), ("groups", groups, known_groups),
                               ("relations", relations, scored + diag)):
        bad = sorted(set(asked or ()) - set(known))
        if bad:
            raise ValueError(f"unknown {kind} {bad}; known: {known}")
    if not (dimensions or groups or relations):
        chosen = list(scored)
    else:
        chosen = [n for n in scored + diag
                  if n in (relations or ())
                  or taxonomy.entry(n).group in (groups or ())
                  or (n in scored and taxonomy.entry(n).group.split(".")[0] in (dimensions or ()))]
    return chosen + [n for n in diag if diagnostics and n not in chosen]


# ------------------------------------------------------------------ evaluate


def _cases_and_bank(suite, cases, domains, rewrites, seed=0, trials=1, repeats=1):
    """(cases, suite record, rewrite bank, frozen plan or None, min_n).

    A bundled suite runs its one frozen plan and nothing else: the same requests for everyone. Settings
    that would make other tests (another seed, rewrite bank or number of trials) are refused; for them,
    pass your own `cases`, whose trials are built from the seed."""
    from jevbench.rewrite import RewriteBank

    if cases is not None:
        cs = load_cases(cases) if isinstance(cases, (str, Path)) else list(cases)
        if domains is not None:
            cs = [c for c in cs if c.meta.get("domain") in domains]
        bank = RewriteBank.load(rewrites) if isinstance(rewrites, (str, Path)) else rewrites
        record, plan, min_n = {"name": "custom", "version": None, "files": {}, "plan": None}, None, 5
    else:
        s = suite if hasattr(suite, "cases") else load_suite(suite)
        cs, bank, plan, min_n = s.select(domains=domains), s.rewrites, s.plan, s.min_n
        record = dict(s.record(), plan=PLAN_NAME if plan is not None else None)
        if plan is not None:
            changed = [k for k, bad in (("seed", seed != plan.seed), ("trials", trials != plan.trials),
                                        ("rewrites", rewrites is not None), ("repeats", repeats != 1)) if bad]
            if changed:
                raise ValueError(f"suite {s.name} is frozen (seed {plan.seed}, its own rewrite bank, one base "
                                 f"request per case): {changed} "
                                 "cannot change; to test other settings, pass cases= with your own data")
    if not cs:
        raise ValueError("no cases selected")
    return cs, record, bank, plan, min_n


def _heartbeat(executor, stop, every=30.0):
    while not stop.wait(every):
        print(f"  jevbench: {executor.calls} requests sent, {executor.cache_hits} from cache", file=sys.stderr,
              flush=True)


def evaluate(model, suite="jevbench-mini", *, domains=None, cases=None, dimensions=None, groups=None,
             relations=None, diagnostics: bool = False, name: str | None = None, concurrency: int | None = None,
             cache=".jevbench-cache", seed: int = 0, repeats: int = 1, trials: int = 1, minimize: bool = False,
             max_requests: int | None = None, rewrites=None, tolerance: float = 0.05, min_n: int | None = None,
             bootstrap: int = 1000, progress: bool = False) -> Report:
    """Run the selected relations over the selected cases and score them.

    model        a backend (`systemone`, `from_callable`, `fake`) or a function
                 `(state, questions) -> answers`
    suite        a bundled suite name, a suite directory, or a `Suite`; ignored when `cases` is given.
                 Default jevbench-mini, the suite results are reported on; "jevbench-240" runs every test
    cases        your own cases: a JSONL path or a list of `Case`
    concurrency  requests in flight at once; default one per replica. Most Jev servers answer
                 one request at a time, so speed comes from replicas (several URLs), not from
                 more requests per server. A server that batches requests on the GPU (vLLM)
                 can return different answers under concurrency than sequentially.
    cache        request cache directory (`None`: no cache; `":memory:"`: this run only)
    repeats      requests of each case's questions for the source output: 1. With your own cases, more
                 repeats measure the model's repeat noise (the source output is then their mean)
    min_n        tests a relation needs to be scored; default the suite's (5; 1 for the examples demo)
    minimize     also rerun each violated test on the batch reduced to its targets (a diagnostic reported in
                 the coherence card, not in any score; it adds requests that depend on the model)
    """
    backend = _as_backend(model)
    concurrency = concurrency or getattr(backend, "slots", 1)
    cs, record, bank, plan, suite_min_n = _cases_and_bank(suite, cases, domains, rewrites, seed, trials, repeats)
    names = select_relations(dimensions, groups, relations, diagnostics)
    if cache not in (None, ":memory:") and not getattr(backend, "cacheable", True):
        warnings.warn(f"{backend.name} has no name, so its answers are cached for this run only; "
                      "pass from_callable(fn, name=...) to reuse them across runs", stacklevel=2)
        cache = ":memory:"
    executor = Executor(backend, cache_dir=cache)
    if cs and max_requests != 0:
        _first_request(executor, cs[0])   # a model that cannot answer stops here, with what to fix
    stop = threading.Event()
    if progress:
        threading.Thread(target=_heartbeat, args=(executor, stop), daemon=True).start()
    try:
        result = run(cs, executor, relations=names, seed=seed, repeats=repeats, trials=trials, minimize=minimize,
                     max_requests=max_requests, rewrites=bank, concurrency=concurrency, plan=plan)
    finally:
        stop.set()
    result["suite"] = record
    result["case_domains"] = {c.id: c.meta.get("domain", "") for c in cs}
    result["selection"] = {"domains": domains, "dimensions": dimensions, "groups": groups, "relations": relations,
                           "diagnostics": diagnostics}
    return Report(result, name=name or backend.name, tolerance=tolerance,
                  min_n=suite_min_n if min_n is None else min_n, bootstrap=bootstrap)


def _first_request(executor, case):
    """Send the first case's base request (a run sends it anyway, and the cache keeps it). A model whose
    answers are not in the standard Jev format raises AnswerFormatError, and one that cannot answer at all
    raises ModelError, each saying what to fix, instead of a run whose every request fails."""
    name = executor.backend.name
    try:
        executor.ask(case.state, case.questions)
    except AnswerFormatError:
        raise
    except Refused as e:
        raise ModelError(f"{name} refused the first request of case {case.id!r}: {e}. A Jev server answers "
                         f"POST /v1/systemone with {{'answers': ...}}; see {FORMAT_URL}") from None
    except Exception as e:  # noqa: BLE001 - whatever stops the model from answering, say so before the run
        raise ModelError(f"{name} could not answer the first request (case {case.id!r}): {type(e).__name__}: {e}. "
                         "A server must be running at the URL and answer POST /v1/systemone; a function given to "
                         f"from_callable must take (state, questions) and return the answers object. See {FORMAT_URL}") from e


def check(model, suite: str = "examples") -> dict:
    """Check that a model works with JevBench: send it one request (the first case of `suite`, by default
    the one-case demo with all three question types) and read every answer in the standard Jev format.

    Returns {"model", "questions" (by type), "seconds"}; raises AnswerFormatError (an answer is not in the
    standard format: the message names the question, shows the answer and states the format) or ModelError
    (the model could not answer). Sends one request and caches nothing."""
    import time

    backend = _as_backend(model)
    case = load_suite(suite).cases[0]
    start = time.perf_counter()
    _first_request(Executor(backend, cache_dir=None), case)
    types = {}
    for q in case.questions.values():
        types[q["type"]] = types.get(q["type"], 0) + 1
    return {"model": backend.name, "questions": types, "seconds": round(time.perf_counter() - start, 3)}


def estimate(suite="jevbench-mini", *, domains=None, cases=None, dimensions=None, groups=None, relations=None,
             diagnostics: bool = False, repeats: int = 1, trials: int = 1, rewrites=None,
             seconds_per_request: float | None = None, concurrency: int = 1) -> dict:
    """How many distinct requests a run sends, counted by a dry run against a toy model.

    With a bundled suite the count is exact: its frozen plan fixes every request (the suite's manifest
    lists the same number). With your own cases it is exact too, as trials never depend on answers.
    Minimization (off by default) would add requests that depend on the model; they are not counted.
    """
    cs, _, bank, plan, _ = _cases_and_bank(suite, cases, domains, rewrites, 0, trials, repeats)
    names = select_relations(dimensions, groups, relations, diagnostics)
    executor = Executor(FakeCoherent(), cache_dir=":memory:")
    result = run(cs, executor, relations=names, seed=0, repeats=repeats, trials=trials, minimize=False,
                 rewrites=bank, plan=plan)
    out = {"cases": len(cs), "relations": len(names), "requests": executor.calls,
           "trials": len({o["trial_id"] for o in result["outcomes"]})}
    if seconds_per_request:
        out["hours"] = round(executor.calls * seconds_per_request / max(1, concurrency) / 3600, 2)
    return out


def compare(reports, level: str = "group") -> str:
    """A side-by-side table of several reports (a list, or {name: report}); level "dimension", "group" or
    "relation"."""
    from jevbench.render import format_scores

    named = reports if isinstance(reports, dict) else {r.name: r for r in reports}
    if not named:
        raise ValueError("compare needs at least one report")
    return format_scores({n: r.scores for n, r in named.items()}, level=level)


def radar(reports, path, level: str = "group", title: str = "JevBench coherence") -> Path:
    """One SVG radar with every report overlaid; `level` is "group" or "dimension"."""
    from jevbench.render import radar_svg

    named = reports if isinstance(reports, dict) else {r.name: r for r in (reports if isinstance(reports, list)
                                                                             else [reports])}
    path = Path(path)
    path.write_text(radar_svg({n: r.scores for n, r in named.items()},
                              level="group" if level == "group" else "pillar", title=title), encoding="utf-8")
    return path


__all__ = ["AnswerFormatError", "Case", "ModelError", "Report", "check", "compare", "describe", "estimate", "evaluate", "fake", "from_callable",
           "list_dimensions", "list_groups", "list_relations", "load_cases", "load_suite", "radar",
           "select_relations", "systemone"]
