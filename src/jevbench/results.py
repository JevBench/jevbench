"""`Report`: a run's outcomes and its scores, by dimension, group, relation and domain; and the
coherence card, the per-check violation rates of one run with their worst examples."""

from __future__ import annotations

import gzip
import json
import math
from collections import defaultdict
from functools import cached_property
from pathlib import Path
from statistics import mean, median

from jevbench import taxonomy
from jevbench.relations import REGISTRY
from jevbench.taxonomy import order_key

FORMAT = 1


# ------------------------------------------------------------------ coherence card

def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def _by_variant(outcomes):
    """Violation rate per variant (template or rewrite index), when there is more than one."""
    groups = defaultdict(list)
    for o in outcomes:
        groups[o.get("variant", 0)].append(o["violated"])
    if len(groups) < 2:
        return None
    return {str(v): {"n": len(x), "violation_rate": sum(x) / len(x)} for v, x in sorted(groups.items())}


def card(result: dict, worst: int = 3, tolerance="fixed", fixed: float = 0.05) -> list[dict]:
    """Violation rate per check, judged exactly as the scores are (the same tolerance rule)."""
    from jevbench.score import _judge

    groups = defaultdict(list)
    for o in result["outcomes"]:
        if o["relation"] in REGISTRY:  # older result files may hold relations since removed
            groups[(o["relation"], o["check"])].append(o)
    rows = []
    for (rel, check), os_ in sorted(groups.items(), key=lambda kv: (order_key(kv[0][0]), kv[0][1])):
        n, k = len(os_), sum(_judge(o, result, tolerance, fixed)[0] for o in os_)
        flips = [o["flip"] for o in os_ if o["flip"] is not None]
        minimized = [o["persists_without_batch"] for o in os_ if o.get("persists_without_batch") is not None]
        devs = sorted(o["deviation"] for o in os_)
        rows.append({
            "relation": rel, "check": check, "group": REGISTRY[rel].group,
            "n": n, "violations": k, "violation_rate": k / n, "violation_rate_95ci": wilson(k, n),
            "mean_deviation": mean(devs), "median_deviation": median(devs),
            "p90_deviation": devs[min(n - 1, int(0.9 * n))],
            "flip_rate": (sum(flips) / len(flips)) if flips else None,
            "persists_without_batch_rate": (sum(minimized) / len(minimized)) if minimized else None,
            "by_variant": _by_variant(os_),
            "worst": sorted(os_, key=lambda o: -o["deviation"])[:worst],
        })
    return rows


def _pct(v):
    return "-" if v is None else f"{100 * v:.1f}"


class Report:
    """Scores are fractions in [0, 1]; 1 means no violation. The run itself is `report.result`."""

    def __init__(self, result: dict, name: str | None = None, tolerance: float = 0.05, min_n: int = 5,
                 bootstrap: int = 1000, min_coverage: float = 0.95):
        self.result, self.name = result, name or result.get("backend", "model")
        self.settings = {"tolerance": tolerance, "min_n": min_n, "bootstrap": bootstrap, "min_coverage": min_coverage}

    # ---------------------------------------------------------------- scores

    @cached_property
    def scores(self) -> dict:
        from jevbench.score import scores

        s = self.settings
        cov = s.get("min_coverage", 0.95)
        if s["tolerance"] == "run":  # each run's own noise tolerance instead of one for every model
            return scores(self.result, tolerance="run", min_n=s["min_n"], bootstrap=s["bootstrap"], min_coverage=cov)
        return scores(self.result, fixed=s["tolerance"], min_n=s["min_n"], bootstrap=s["bootstrap"], min_coverage=cov)

    @property
    def overall(self):
        """Mean of the five dimensions; None unless every dimension was tested."""
        return self.scores["overall"]

    @property
    def dimensions(self) -> dict:
        return self.scores["pillars"]

    @property
    def groups(self) -> dict:
        return self.scores["groups"]

    @property
    def relations(self) -> dict:
        return self.scores["relations"]

    @property
    def interval(self):
        """95% bootstrap interval of the overall score, over cases."""
        return self.scores["ci"].get("overall")

    @property
    def errors(self) -> list:
        return self.result["errors"]

    def by_domain(self) -> dict[str, dict]:
        """The scores computed separately on each domain's cases."""
        from jevbench.score import scores

        doms = self.result.get("case_domains") or {}
        out = {}
        for dom in dict.fromkeys(doms.values()):
            ids = {c for c, d in doms.items() if d == dom}
            sub = dict(self.result, outcomes=[o for o in self.result["outcomes"] if o["case_id"] in ids],
                       bases={c: b for c, b in self.result["bases"].items() if c in ids})
            s = self.settings
            tol = {"tolerance": "run"} if s["tolerance"] == "run" else {"fixed": s["tolerance"]}
            sub.pop("planned_tests", None)   # coverage is judged on the whole run
            out[dom] = scores(sub, min_n=s["min_n"], bootstrap=0, min_coverage=0.0, **tol)
        return out

    # ---------------------------------------------------------------- views

    def table(self, level: str = "dimension") -> str:
        """A text table: level "dimension", "group", "relation" or "domain"."""
        s = self.scores
        ci = self.interval
        head = [f"{self.name}: overall {_pct(self.overall)}" + (f" [{100 * ci[0]:.0f}-{100 * ci[1]:.0f}]" if ci else "")
                + f"  ({s['n_cases']} cases, {s['n_checks']} scored relations, tolerance {self.settings['tolerance']})"]
        rows = []
        if level == "dimension":
            rows = [(p.id, p.title, self.dimensions[p.id]) for p in taxonomy.PILLARS]
        elif level == "group":
            rows = [(g.id, g.title, self.groups[g.id]) for g in taxonomy.GROUPS]
        elif level == "relation":
            rows = [(n, taxonomy.entry(n).group, v) for n, v in
                    sorted(self.relations.items(), key=lambda kv: taxonomy.order_key(kv[0]))]
        elif level == "domain":
            rows = [(d, " ".join(f"{k} {_pct(v)}" for k, v in x["pillars"].items()), x["overall"])
                    for d, x in self.by_domain().items()]
        else:
            raise ValueError('level is "dimension", "group", "relation" or "domain"')
        w = max([len(r[0]) for r in rows] + [8])
        lines = head + [f"  {a:<{w}}  {_pct(v):>6}  {b}" for a, b, v in rows]
        excluded = s["excluded"]["low_n"]
        if excluded and level != "domain":
            lines.append(f"  fewer than {self.settings['min_n']} tests, not scored: {', '.join(excluded)}")
        if s.get("incomplete"):
            cov = {k.split("/")[0]: v.get("coverage") for k, v in s["checks"].items()}
            lines.append("  INCOMPLETE, not scored (requests refused or invalid): " +
                         ", ".join(f"{r} ({cov.get(r, 0):.0%} of tests)" for r in s["incomplete"]) +
                         "; their dimensions and the overall score are not reported")
        if self.errors:
            first = self.errors[0]
            where = ", ".join(f"{k} {first[k]}" for k in ("case", "relation", "target") if first.get(k))
            lines.append(f"  {len(self.errors)} requests failed or were refused; the first ({where}): "
                         f"{str(first.get('error'))[:400]}")
        return "\n".join(lines)

    def __repr__(self):
        dims = ", ".join(f"{k} {_pct(v)}" for k, v in self.dimensions.items())
        failed = f"; {len(self.errors)} requests failed" if self.errors else ""
        return f"<Report {self.name}: overall {_pct(self.overall)}; {dims}{failed}>"

    def radar(self, path, level: str = "group"):
        from jevbench.api import radar

        return radar([self], path, level=level, title=f"JevBench: {self.name}")

    # ---------------------------------------------------------------- files

    def save(self, path) -> Path:
        """Write the report as JSON; a path ending in .gz is written compressed (and compact)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"jevbench_report": FORMAT, "name": self.name, "settings": self.settings, "scores": self.scores,
                "result": self.result}
        if path.suffix == ".gz":
            with gzip.open(path, "wt", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path, **settings) -> "Report":
        """A saved report (.json or .json.gz), or a raw `jevbench run` result file; `settings` override the
        saved scoring."""
        path = Path(path)
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
        if "jevbench_report" in data:
            return cls(data["result"], name=data.get("name"), **{**data.get("settings", {}), **settings})
        return cls(data, name=path.name.split(".")[0], **settings)
