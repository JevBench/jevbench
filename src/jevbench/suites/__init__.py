"""Test suites shipped with the package: fixed cases, a rewrite bank and one frozen test plan each.

    >>> from jevbench.suites import load_suite, list_suites
    >>> list_suites()
    ['examples', 'jevbench-240', 'jevbench-mini']
    >>> suite = load_suite("jevbench-240")
    >>> len(suite.cases), suite.domains[:2]
    (240, ['customer_support', 'content_moderation'])

A suite is a directory with `cases.jsonl`, an optional `rewrites.jsonl`, its frozen
test plan `tests.jsonl.gz` (see jevbench.plan) and a `manifest.json` that records
its version and the SHA-256 of every file. The plan tests each relation exactly
once per case; it is the one version of the suite, so every run of it sends the
same requests and draws no random numbers.

    jevbench-mini  the default, and the suite results are reported on: the 240 cases of jevbench-240,
                   each relation tested on 2 cases per domain (24 tests per relation, 5 relations per
                   case), about a ninth of the requests; every test is jevbench-240's own. On 17
                   models its overall scores agree with jevbench-240's (Spearman 0.98, at most 2.2
                   points apart), with intervals about 2.5 times as wide
    jevbench-240   the full benchmark: 240 cases in 12 domains, 240 tests per relation; optional,
                   for narrower intervals and per-domain analysis
    examples       one hand-written case, to check in seconds that the tool works with
                   your model; it scores relations from one test each (manifest
                   `min_n` 1), so its numbers are a demonstration, never a result

A suite whose manifest names a `base` suite takes its cases and rewrite bank from it (their hashes
are checked too) and stores only its own plan. `load_suite` also takes a suite directory, for suites
of your own (`jevbench plan`).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from jevbench.schema import Case, load_cases

PLAN = "tests.jsonl.gz"


def _hashes(path: Path) -> dict:
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(path.iterdir()) if f.name.endswith((".jsonl", ".jsonl.gz"))}


@dataclass
class Suite:
    name: str
    version: str
    description: str
    cases: list[Case]
    rewrites: object | None = None          # a RewriteBank, or None when the suite has none
    files: dict = field(default_factory=dict)  # file name -> SHA-256
    path: Path | None = None
    min_n: int = 5                         # tests a relation needs to be scored (the demo suite sets 1)
    _plan: object = field(default=None, repr=False)

    @property
    def plan(self):
        """The frozen test plan (loaded on first use), or None when the suite has none."""
        if self._plan is None and self.path is not None and (self.path / PLAN).is_file():
            from jevbench.plan import load_plan

            self._plan = load_plan(self.path / PLAN)
        return self._plan

    @property
    def domains(self) -> list[str]:
        return list(dict.fromkeys(c.meta.get("domain", "") for c in self.cases))

    def select(self, domains=None, ids=None) -> list[Case]:
        """The suite's cases in the given domains and/or with the given ids (all when both are None)."""
        if domains is not None:
            unknown = sorted(set(domains) - set(self.domains))
            if unknown:
                raise ValueError(f"{self.name}: unknown domains {unknown}; known: {self.domains}")
        return [c for c in self.cases
                if (domains is None or c.meta.get("domain") in domains) and (ids is None or c.id in ids)]

    def record(self) -> dict:
        return {"name": self.name, "version": self.version, "files": self.files}


def _root():
    return resources.files(__name__)


def list_suites() -> list[str]:
    return sorted(p.name for p in _root().iterdir() if p.is_dir() and (p / "manifest.json").is_file())


def load_suite(name: str = "jevbench-240", audited_only: bool = False) -> Suite:
    """A bundled suite by name, or a suite directory on disk (with the same layout)."""
    from jevbench.rewrite import RewriteBank

    # a bundled suite's name always means the bundled suite; a directory is given as a path ("./x", "/a/x")
    explicit = "/" in str(name) or os.sep in str(name) or str(name).startswith(".")
    if not explicit and name in list_suites():
        path = Path(str(_root() / name))
    else:
        path = Path(name)
        if not (path / "manifest.json").is_file():
            raise ValueError(f"unknown suite {name!r}: not bundled ({list_suites()}) and no suite directory there")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    files = _hashes(path)
    changed = sorted(f for f in set(files) | set(manifest.get("files", {})) if files.get(f) != manifest["files"].get(f))
    if changed:
        raise ValueError(f"suite {manifest['name']}: {changed} differ from the manifest; the suite was modified")
    if manifest.get("base"):
        base = load_suite(manifest["base"], audited_only=audited_only)
        if base.files != manifest.get("base_files"):
            raise ValueError(f"suite {manifest['name']}: its base {base.name} is not the one it was frozen from")
        return Suite(name=manifest["name"], version=str(manifest["version"]),
                     description=manifest.get("description", ""), cases=base.cases, rewrites=base.rewrites,
                     files={**files, **{f"{base.name}/{k}": v for k, v in base.files.items()}}, path=path,
                     min_n=int(manifest.get("min_n", 5)))
    bank = path / "rewrites.jsonl"
    return Suite(name=manifest["name"], version=str(manifest["version"]), description=manifest.get("description", ""),
                 cases=load_cases(path / "cases.jsonl"),
                 rewrites=RewriteBank.load(bank, audited_only=audited_only) if bank.is_file() else None,
                 files=files, path=path, min_n=int(manifest.get("min_n", 5)))


def freeze(path, seed: int = 0, trials: int = 1, full_out=None) -> dict:
    """Write the suite directory's frozen test plan (each relation once per case) and refresh its manifest.

    For suite authors: run it after changing the cases, the rewrite bank or any relation. It fails if a
    relation reads model outputs while building a trial (jevbench.plan.ModelDependent). `full_out`, a path
    outside the suite, also writes the plan of every trial the plan was chosen from, for local analysis;
    it is not part of the suite."""
    from jevbench import __version__, taxonomy
    from jevbench.plan import build_plan, standard_plan, write_plan
    from jevbench.rewrite import RewriteBank

    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("base"):
        return _freeze_sample(path, manifest)
    cases = load_cases(path / "cases.jsonl")
    bank = RewriteBank.load(path / "rewrites.jsonl") if (path / "rewrites.jsonl").is_file() else None
    full = build_plan(cases, taxonomy.scored(), rewrites=bank, seed=seed, trials=trials)
    plan = standard_plan(full, cases)
    write_plan(plan, path / PLAN)
    for old in ("plans", "default_plan"):
        manifest.pop(old, None)
    manifest["plan"] = {"file": PLAN, "selection": "each relation tested once per case, one variant per test",
                        "trials": len(plan["rows"]),
                        "tests": len({(r["relation"], r["case"], r["key"]) for r in plan["rows"]}),
                        "relations": len(plan["relations"]), "seed": seed, "trials_per_target": trials,
                        "chosen_from_trials": len(full["rows"]), "requests": _requests(cases, plan)}
    if full_out:
        write_plan(full, full_out)
        manifest["plan"]["full_plan_sha256"] = hashlib.sha256(Path(full_out).read_bytes()).hexdigest()
    manifest["built_with"] = f"jevbench {__version__}"
    manifest["files"] = _hashes(path)
    (path / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest["plan"]


def _freeze_sample(path: Path, manifest: dict) -> dict:
    """A suite drawn from its base suite's plan: each relation on `per_domain` cases of each domain."""
    from jevbench import __version__
    from jevbench.plan import relation_sample, write_plan

    base = load_suite(manifest["base"])
    per_domain = int(manifest.get("per_domain", 2))
    plan = relation_sample(base.plan, base.cases, per_domain=per_domain)
    write_plan(plan, path / PLAN)
    tests = {(r["relation"], r["case"], r["key"]) for r in plan["rows"]}
    manifest["plan"] = {"file": PLAN, "selection": plan["selection"] + ", one variant per test",
                        "trials": len(plan["rows"]), "tests": len(tests), "relations": len(plan["relations"]),
                        "seed": plan["seed"], "trials_per_target": plan["trials"],
                        "drawn_from": f"{base.name} v{base.version}", "requests": _requests(base.cases, plan)}
    manifest["per_domain"] = per_domain
    manifest["base_files"] = base.files
    manifest["built_with"] = f"jevbench {__version__}"
    manifest["files"] = _hashes(path)
    (path / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest["plan"]


def _requests(cases, plan: dict) -> int:
    """Requests a run of the plan sends: one base request per case plus every distinct trial request
    (relations that share requests send them once). Exact: no minimization, which is off by default."""
    from jevbench.plan import decode_requests

    by_id = {c.id: c for c in cases}
    seen = {(c.id, json.dumps(c.questions, ensure_ascii=False)) for c in cases}
    for row in plan["rows"]:
        for qs in decode_requests(by_id[row["case"]], row["requests"]).values():
            seen.add((row["case"], json.dumps(qs, ensure_ascii=False)))
    return len(seen)
