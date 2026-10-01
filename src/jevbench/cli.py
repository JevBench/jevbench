"""Command line. `jevbench eval` is the Python API's `evaluate`; `jevbench run` is the low-level engine run."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from jevbench.backends import Executor, make_backend
from jevbench.engine import run
from jevbench.relations import REGISTRY
from jevbench.render import format_card
from jevbench.results import card
from jevbench import taxonomy
from jevbench.rewrite import ChatClient, RewriteBank, build_bank
from jevbench.schema import load_cases


def _run(args):
    cases = load_cases(args.cases)
    if args.max_cases:
        cases = cases[: args.max_cases]
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    backend = make_backend(args.backend, url=args.url, api_key=api_key, min_interval=args.min_interval)
    executor = Executor(backend, cache_dir=None if args.no_cache else args.cache_dir)
    relations = "all" if args.relations == "all" else [r.strip() for r in args.relations.split(",")]
    rewrites = RewriteBank.load(args.rewrites, audited_only=args.audited_only) if args.rewrites else None

    def progress(case, name):
        if args.verbose:
            print(f"  {case.id}: {name} done ({executor.calls} requests)", file=sys.stderr, flush=True)

    result = run(cases, executor, relations=relations, seed=args.seed, repeats=args.repeats, trials=args.trials,
                 minimize=args.minimize, noise_multiplier=args.noise_multiplier,
                 noise_floor=args.noise_floor, max_requests=args.max_requests, progress=progress,
                 rewrites=rewrites, concurrency=args.concurrency)
    result["rewrites"] = args.rewrites
    result["card"] = card(result)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(format_card(result))
    print(f"wrote {out}")


def _csv(v):
    return [x.strip() for x in v.split(",") if x.strip()] if v else None


def _model(args):
    import jevbench as jb

    if args.url:
        if not args.model:
            raise SystemExit("give --model, the model name the server expects")
        return jb.systemone(args.url, args.model, api_key_env=args.api_key_env,
                            min_interval=args.min_interval, revision=args.revision)
    if args.backend.startswith("fake"):
        return jb.fake(args.backend.partition(":")[2] or "coherent")
    raise SystemExit("give --url (a System One endpoint), or --backend fake:coherent | fake:biased to try the "
                     "tool; a model in a Python process is tested with jevbench.from_callable")


def _selection(args):
    return dict(domains=_csv(args.domains), dimensions=_csv(args.dimensions), groups=_csv(args.groups),
                relations=_csv(args.relations), diagnostics=args.diagnostics)


def _check(args):
    import jevbench as jb

    try:
        r = jb.check(_model(args))
    except (jb.AnswerFormatError, jb.ModelError) as e:
        raise SystemExit(f"jevbench check: FAILED\n{e}")
    qs = ", ".join(f"{n} {t}" for t, n in r["questions"].items())
    print(f"jevbench check: OK. {r['model']} answered one request ({qs}) in the standard Jev format "
          f"in {r['seconds']}s; run `jevbench eval` next")


def _eval(args):
    import jevbench as jb

    try:
        report = _evaluate(args)
    except (jb.AnswerFormatError, jb.ModelError) as e:
        raise SystemExit(f"jevbench eval: stopped before the run\n{e}")
    _print_eval(args, report)


def _evaluate(args):
    import jevbench as jb

    return jb.evaluate(_model(args), suite=args.suite, cases=args.cases, **_selection(args), name=args.name,
                       concurrency=args.concurrency, cache=None if args.no_cache else args.cache_dir,
                       seed=args.seed, repeats=args.repeats, minimize=args.minimize,
                       max_requests=args.max_requests, rewrites=args.rewrites, tolerance=args.tolerance,
                       progress=args.verbose)


def _print_eval(args, report):
    for level in ("dimension", "group"):
        print(report.table(level))
    if args.out:
        print(f"wrote {report.save(args.out)}")
    if report.result.get("backend_down"):
        print(f"stopped: the model server is down: {report.result['backend_down']}", file=sys.stderr)
    if report.errors:
        print(f"{len(report.errors)} errors (refused or invalid answers); see the report file", file=sys.stderr)
    if report.errors or report.result.get("backend_down"):
        sys.exit(1)


def _estimate(args):
    import jevbench as jb

    print(json.dumps(jb.estimate(args.suite, cases=args.cases, **_selection(args), repeats=args.repeats,
                                 seconds_per_request=args.seconds_per_request, concurrency=args.concurrency)))


def _suites(args):
    from jevbench.suites import list_suites, load_suite

    for name in list_suites():
        s = load_suite(name)
        print(f"{s.name} v{s.version}: {len(s.cases)} cases, {len(s.domains)} domains"
              f"{', rewrite bank' if s.rewrites else ''}\n  {s.description}")


def _report(args):
    """Saved reports or raw `jevbench run` results: tables, the coherence card, JSON, radars."""
    import jevbench as jb
    from jevbench.render import format_card, radar_grid_svg, radar_svg

    names = args.names.split(",") if args.names else [None] * len(args.reports)
    if len(names) != len(args.reports):
        raise SystemExit(f"--names gives {len(names)} names for {len(args.reports)} files")
    tol = "run" if args.per_run_tolerance else args.tolerance
    reports = [jb.Report.load(p, tolerance=tol, min_n=args.min_n, bootstrap=args.bootstrap) for p in args.reports]
    for r, n in zip(reports, names):
        if n:
            r.name = n
    if args.card:
        for r in reports:
            print(format_card(r.result, tolerance="run" if args.per_run_tolerance else "fixed", fixed=args.tolerance))
    elif len(reports) == 1:
        print(reports[0].table(args.level))
    else:
        print(jb.compare(reports, level="group" if args.level == "domain" else args.level))
    named = {r.name: r.scores for r in reports}
    family = json.loads(Path(args.families).read_text(encoding="utf-8")) if args.families else {}
    axes = "group" if args.level in ("group", "relation", "domain") else "pillar"

    def write(path, text):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
        print(f"wrote {path}")

    if args.json:
        write(args.json, json.dumps(named, indent=1))
    if args.radar:
        write(args.radar, radar_svg(named, level=axes, title=args.title, metric=args.metric))
    if args.grid:
        write(args.grid, radar_grid_svg(named, level=axes, metric=args.metric, family=family,
                                        title=f"{args.title} by model"))
    if args.family_dir:
        if not family:
            raise SystemExit("--family-dir needs --families")
        for fam in sorted(set(family.values())):
            members = {n: sc for n, sc in named.items() if family.get(n) == fam}
            if members:
                slug = re.sub(r"[^a-z0-9]+", "-", fam.lower()).strip("-")
                write(Path(args.family_dir) / f"radar-{slug}.svg",
                      radar_svg(members, level=axes, metric=args.metric, title=f"{args.title}: {fam}"))


def _plan(args):
    from jevbench.suites import freeze

    print(json.dumps(freeze(args.suite_dir, seed=args.seed, full_out=args.full_out)))


def _rewrite(args):
    from jevbench.suites import load_suite

    cases = load_cases(args.cases) if args.cases else load_suite(args.suite).cases
    if args.max_cases:
        cases = cases[: args.max_cases]
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    extra = json.loads(args.extra) if args.extra else None
    chat = ChatClient(args.chat_url, args.model, api_key=api_key, temperature=args.temperature, extra=extra)
    judge = None
    if args.judge_url or args.judge_model:
        judge = ChatClient(args.judge_url or args.chat_url, args.judge_model or args.model, api_key=api_key,
                           extra=json.loads(args.judge_extra) if args.judge_extra else extra)
    kinds = [k.strip() for k in args.kinds.split(",")]

    def progress(i, n, kind):
        if args.verbose or i == n or i % 25 == 0:
            print(f"  {i}/{n} sources ({kind})", file=sys.stderr, flush=True)

    build_bank(cases, kinds, chat, args.out, n=args.n, progress=progress, judge=judge,
               judge_tokens=args.judge_tokens, max_tokens=args.max_tokens, concurrency=args.concurrency)
    bank = RewriteBank.load(args.out)
    print(json.dumps(bank.stats()))
    print(f"wrote {args.out}")


def _relations(args):
    """Print the taxonomy tree; implemented relations with their expectation and source."""
    def show(e):
        mark = "*" if e.implemented else "o"
        tag = "  (exploratory)" if e.exploratory else ""
        print(f"    {mark} {e.name:<26}[{', '.join(e.edits) or '-'} | {e.law}]  {e.summary}{tag}")
        if e.implemented and args.verbose:
            rel = REGISTRY[e.name]
            print(f"        expects: {rel.expectation}\n        source:  {rel.source}")

    def groups(gs, pillar=None):
        for g in gs:
            if pillar is not None and g.pillar != pillar:
                continue
            print(f"  {g.id:<16}{g.title}: {g.question}")
            for e in taxonomy.IMPLEMENTED + taxonomy.DIAGNOSTICS + taxonomy.PLANNED:
                if e.group == g.id and (e.implemented or args.planned):
                    show(e)

    for p in taxonomy.PILLARS:
        print(f"{p.id}  {p.title}  [{p.oracle}]: {p.expects}")
        groups(taxonomy.GROUPS, p.id)
    print("DIAG  Diagnostics (not scored, run only when named)")
    groups(taxonomy.DIAGNOSTIC_GROUPS)
    if not args.planned:
        print(f"\n{len(taxonomy.PLANNED)} planned relations hidden; add --planned to show them.")


def _taxonomy(args):
    if args.write:
        changed = taxonomy.write_readme(args.write)
        print(f"{'updated' if changed else 'unchanged'}: {args.write}")
    else:
        print(taxonomy.markdown())


def _datagen(args):
    from jevbench.datagen import freeze as fz, text
    from jevbench.datagen.domains import DOMAINS
    from jevbench.datagen.sample import plan_domain

    def chat():
        extra = json.loads(args.extra) if args.extra else None
        key = os.environ.get(args.api_key_env) if args.api_key_env else None
        return ChatClient(args.chat_url, args.model, api_key=key, temperature=args.temperature, extra=extra)

    def progress(i, n):
        if i == n or i % 10 == 0:
            print(f"  {i}/{n}", file=sys.stderr, flush=True)

    if args.step == "plan":
        names = [d.strip() for d in args.domains.split(",")]
        unknown = [d for d in names if d not in DOMAINS]
        if unknown:
            raise SystemExit(f"unknown domains {unknown}; known: {sorted(DOMAINS)}")
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for name in names:
                for plan in plan_domain(DOMAINS[name], args.n, seed=args.seed, pool=args.pool):
                    f.write(json.dumps(plan, ensure_ascii=False) + "\n")
        print(f"wrote {out}: {args.n} plans per domain for {names}")
    elif args.step == "write":
        n = text.write_states(args.plans, args.out, chat(), progress=progress, redo=args.redo)
        print(f"wrote {args.out}: {n} drafts")
    elif args.step == "verify":
        text.verify_states(args.plans, args.drafts, args.out, chat(), progress=progress)
        rows = list(text._latest(text._jsonl(args.out)).values())
        print(f"wrote {args.out}: {sum(r['passed'] for r in rows)}/{len(rows)} passed")
    else:
        res = fz.freeze(args.plans, args.drafts, args.verified, args.out_dir, args.per_domain, args.source,
                        tokenizer=args.tokenizer, tokenizer_subfolder=args.tokenizer_subfolder,
                        max_tokens=args.max_state_tokens)
        print(json.dumps(res))



def main(argv=None):
    p = argparse.ArgumentParser(prog="jevbench", description="Metamorphic tests for Jev-compatible typed decision models.")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run relations over a JSONL file of cases")
    r.add_argument("--cases", required=True, help="JSONL of {id, state, questions}")
    r.add_argument("--backend", required=True,
                   help="systemone:<model> | fake:coherent | fake:biased (a model in a Python process: the API's "
                   "jevbench.from_callable)")
    r.add_argument("--url", help="System One endpoint, e.g. http://127.0.0.1:8080/v1/systemone; several "
                   "comma-separated replicas of the same model are used in turn")
    r.add_argument("--concurrency", type=int, default=1,
                   help="requests in flight at once (default 1); one per replica keeps answers identical to a "
                   "sequential run, more can change them on servers that batch on the GPU")
    r.add_argument("--api-key-env", default="JEVBENCH_API_KEY", help="environment variable holding the bearer token")
    r.add_argument("--relations", default="all", help="'all' (every scored relation), 'diagnostics', or a comma-separated list mixing both "
                   "with relation names")
    r.add_argument("--repeats", type=int, default=1, help="requests of each case's questions for the source "
                   "output (more also measure repeat noise)")
    r.add_argument("--trials", type=int, default=1, help="random draws per randomized relation and target")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--noise-multiplier", type=float, default=2.0)
    r.add_argument("--noise-floor", type=float, default=0.05)
    r.add_argument("--max-requests", type=int, help="stop after this many uncached requests")
    r.add_argument("--max-cases", type=int)
    r.add_argument("--min-interval", type=float, default=0.0, help="seconds between HTTP requests")
    r.add_argument("--cache-dir", default=".jevbench-cache")
    r.add_argument("--no-cache", action="store_true")
    r.add_argument("--minimize", action="store_true", help="diagnostic: rerun violations without the batch")
    r.add_argument("--rewrites", help="JSONL bank from `jevbench rewrite`, enables natural-rewrite relations")
    r.add_argument("--audited-only", action="store_true", help="use only rewrites a human marked audited: true")
    r.add_argument("--out", required=True)
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(func=_run)

    def selection(sp):
        sp.add_argument("--suite", default="jevbench-mini", help="a bundled suite (see `jevbench suites`) or a "
                        "suite directory; default jevbench-mini (jevbench-240: every test)")
        sp.add_argument("--cases", help="your own JSONL of cases instead of a suite")
        sp.add_argument("--domains", help="comma-separated domains (cases)")
        sp.add_argument("--dimensions", help="comma-separated dimensions, e.g. MEA,CHO")
        sp.add_argument("--groups", help="comma-separated groups, e.g. CHO.conditioning")
        sp.add_argument("--relations", help="comma-separated relation names")
        sp.add_argument("--diagnostics", action="store_true", help="also run the diagnostic relations")
        sp.add_argument("--repeats", type=int, default=1, help="base requests per case (bundled suites: 1)")
        sp.add_argument("--concurrency", type=int, help="requests in flight (default: one per replica URL)")

    c = sub.add_parser("check", help="check that a model works with JevBench: one request, every answer read")
    c.add_argument("--url", help="System One endpoint")
    c.add_argument("--model", help='the "model" field sent to the server')
    c.add_argument("--revision")
    c.add_argument("--backend", default="", help="instead of --url: fake:coherent | fake:biased (toy models)")
    c.add_argument("--api-key-env", default="JEVBENCH_API_KEY")
    c.add_argument("--min-interval", type=float, default=0.0)
    c.set_defaults(func=_check)

    e = sub.add_parser("eval", help="evaluate a model on a suite, by domain, dimension, group or relation")
    e.add_argument("--url", help="System One endpoint; comma-separated replicas are used in turn")
    e.add_argument("--model", help='the "model" field sent to the server')
    e.add_argument("--revision", help="the model's version, kept apart in the request cache")
    e.add_argument("--backend", default="", help="instead of --url: fake:coherent | fake:biased (toy models)")
    e.add_argument("--api-key-env", default="JEVBENCH_API_KEY")
    e.add_argument("--min-interval", type=float, default=0.0)
    selection(e)
    e.add_argument("--name", help="the model's name in reports")
    e.add_argument("--seed", type=int, default=0)
    e.add_argument("--minimize", action="store_true", help="diagnostic: rerun violations without the batch "
                   "(not scored; adds model-dependent requests)")
    e.add_argument("--max-requests", type=int)
    e.add_argument("--rewrites", help="a rewrite bank to use instead of the suite's")
    e.add_argument("--tolerance", type=float, default=0.05)
    e.add_argument("--cache-dir", default=".jevbench-cache")
    e.add_argument("--no-cache", action="store_true")
    e.add_argument("--out", help="write the report (JSON) here")
    e.add_argument("-v", "--verbose", action="store_true", help="print progress every 30 s")
    e.set_defaults(func=_eval)

    es = sub.add_parser("estimate", help="count the requests an evaluation would send")
    selection(es)
    es.add_argument("--seconds-per-request", type=float)
    es.set_defaults(func=_estimate)

    pl = sub.add_parser("plan", help="freeze a suite directory's test plan (every trial) and refresh its manifest")
    pl.add_argument("suite_dir")
    pl.add_argument("--seed", type=int, default=0)
    pl.add_argument("--full-out", help="also write the plan of every trial here (outside the suite), for analysis")
    pl.set_defaults(func=_plan)

    su = sub.add_parser("suites", help="list the bundled test suites")
    su.set_defaults(func=_suites)

    rp = sub.add_parser("report", help="show saved reports (or raw run results): tables, comparison, card, radars")
    rp.add_argument("reports", nargs="+", help="report files from `eval --out`, or result files from `run --out`")
    rp.add_argument("--names", help="comma-separated display names, one per file")
    rp.add_argument("--level", default="group", choices=["dimension", "group", "relation", "domain"],
                    help="table of one report; radar axes: dimensions, or else groups")
    rp.add_argument("--card", action="store_true", help="the coherence card: violation rates per check, worst cases")
    rp.add_argument("--tolerance", type=float, default=0.05, help="the fixed tolerance every model is judged with")
    rp.add_argument("--per-run-tolerance", action="store_true", help="judge with each run's own noise tolerance")
    rp.add_argument("--min-n", type=int, default=5, help="relations with fewer tests are left out of the means")
    rp.add_argument("--bootstrap", type=int, default=1000, help="bootstrap draws over cases (0: no intervals)")
    rp.add_argument("--json", help="write {name: scores} as JSON")
    rp.add_argument("--radar", help="write one SVG radar with every report overlaid")
    rp.add_argument("--grid", help="write an SVG grid of small radars, one per report")
    rp.add_argument("--families", help='JSON {"name": "family"} to label the grid and group --family-dir')
    rp.add_argument("--family-dir", help="write one overlaid radar per family into this directory")
    rp.add_argument("--metric", choices=["binary", "graded"], default="binary", help="what the radars plot")
    rp.add_argument("--title", default="JevBench coherence")
    rp.set_defaults(func=_report)

    w = sub.add_parser("rewrite", help="generate and judge natural rewrites into a frozen JSONL bank")
    w.add_argument("--cases", help="a JSONL of cases (default: the --suite's cases)")
    w.add_argument("--suite", default="jevbench-240")
    w.add_argument("--kinds", default="paraphrase,negation,description,translate:zh",
                   help="comma-separated: paraphrase, negation, description, translate:<lang>")
    w.add_argument("--chat-url", required=True, help="OpenAI-compatible /v1/chat/completions URL")
    w.add_argument("--model", required=True)
    w.add_argument("--api-key-env", default="JEVBENCH_API_KEY")
    w.add_argument("--n", type=int, default=3, help="candidates per source")
    w.add_argument("--temperature", type=float, default=0.0)
    w.add_argument("--extra", help='JSON merged into every chat request, e.g. \'{"reasoning_effort": "low"}\'')
    w.add_argument("--max-tokens", type=int, default=800, help="for a generation (reasoning models need more)")
    w.add_argument("--judge-url", help="judge with another model (default: the generator)")
    w.add_argument("--judge-model")
    w.add_argument("--judge-extra")
    w.add_argument("--judge-tokens", type=int, default=5, help="for a verdict (reasoning models need more)")
    w.add_argument("--concurrency", type=int, default=1, help="sources worked on at once")
    w.add_argument("--max-cases", type=int)
    w.add_argument("--out", required=True)
    w.add_argument("-v", "--verbose", action="store_true")
    w.set_defaults(func=_rewrite)

    rel = sub.add_parser("relations", help="print the relation taxonomy")
    rel.add_argument("--planned", action="store_true", help="also list planned relations")
    rel.add_argument("-v", "--verbose", action="store_true", help="add each relation's expectation and source")
    rel.set_defaults(func=_relations)
    tx = sub.add_parser("taxonomy", help="print the taxonomy as Markdown, or update a README section")
    tx.add_argument("--write", metavar="README", help="replace the section between the taxonomy markers")
    tx.set_defaults(func=_taxonomy)
    g = sub.add_parser("datagen", help="fact-first synthetic cases: plan | write | verify | freeze")
    g.add_argument("step", choices=["plan", "write", "verify", "freeze"])
    g.add_argument("--domains", default="customer_support,security_ops")
    g.add_argument("--n", type=int, default=30, help="plans per domain (plan more than you keep)")
    g.add_argument("--pool", type=int, default=3000, help="candidates sampled per domain before balancing")
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--plans")
    g.add_argument("--drafts")
    g.add_argument("--verified")
    g.add_argument("--redo", help="write: rewrite, with a new seed, the plans whose latest draft failed in this "
                   "verified.jsonl")
    g.add_argument("--out")
    g.add_argument("--out-dir")
    g.add_argument("--per-domain", type=int, default=20)
    g.add_argument("--tokenizer", help="freeze: also cap states' length in this Hugging Face tokenizer's tokens")
    g.add_argument("--tokenizer-subfolder")
    g.add_argument("--max-state-tokens", type=int, default=480)
    g.add_argument("--source", default="synthetic, fact-first (JevBench datagen)")
    g.add_argument("--chat-url")
    g.add_argument("--model")
    g.add_argument("--temperature", type=float, default=0.0)
    g.add_argument("--extra", help='JSON merged into every chat request, e.g. \'{"reasoning_effort": "low"}\'')
    g.add_argument("--api-key-env", default=None)
    g.set_defaults(func=_datagen)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
