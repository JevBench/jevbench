"""Test data: four cases of jevbench-240 (the first of four domains), its rewrite bank, and the same four
cases frozen as a small suite in a temporary directory. No test data is stored of its own."""

import atexit
import json
import shutil
import tempfile
from pathlib import Path

import jevbench as jb
from jevbench.suites import freeze

BENCH = jb.load_suite("jevbench-240")
DOMAINS = ("customer_support", "content_moderation", "finance_ops", "security_ops")
FOUR_CASES = [next(c for c in BENCH.cases if c.meta["domain"] == d) for d in DOMAINS]
BANK = BENCH.rewrites


def _four_suite() -> str:
    d = Path(tempfile.mkdtemp(prefix="jevbench-test-")) / "test-four"
    atexit.register(shutil.rmtree, d.parent, ignore_errors=True)
    d.mkdir()
    ids = {c.id for c in FOUR_CASES}
    lines = [line for line in (BENCH.path / "cases.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip() and json.loads(line)["id"] in ids]
    (d / "cases.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copy(BENCH.path / "rewrites.jsonl", d / "rewrites.jsonl")
    # four tests per relation: scored from one test each, like the examples demo
    (d / "manifest.json").write_text(json.dumps({"name": "test-four", "version": "1", "min_n": 1, "files": {}}),
                                     encoding="utf-8")
    freeze(d)
    return str(d)


FOUR = _four_suite()  # a suite directory: four cases, the bank, a frozen plan
