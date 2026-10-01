"""The engine is reproducible, respects its budget, and reads the wire format."""

import json

import pytest

from jevbench.backends import Executor, FakeBiased, FakeCoherent
from jevbench.engine import run
from jevbench.schema import Case, SchemaError, load_cases, read_distribution

from _data import FOUR_CASES  # noqa: E402


def test_same_seed_same_outcomes(tmp_path):
    cases = FOUR_CASES[:1]
    a = run(cases, Executor(FakeBiased(), cache_dir=tmp_path), seed=3)
    b = run(cases, Executor(FakeBiased(), cache_dir=tmp_path), seed=3)
    assert json.dumps(a["outcomes"]) == json.dumps(b["outcomes"])
    assert b["requests"] == 0 and b["cache_hits"] > 0


def test_budget_truncates_cleanly():
    result = run(FOUR_CASES, Executor(FakeCoherent()), max_requests=10)
    assert result["truncated_by_budget"] and result["requests"] == 10


def test_schema_validation_and_reading():
    with pytest.raises(SchemaError):
        Case(id="x", state="s", questions={"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A"}}})
    q = {"type": "score", "instructions": "?", "criteria": ["lo", "hi"]}
    assert read_distribution({"probabilities": {"0": 1, "1": 3}}, q) == {"0": 0.25, "1": 0.75}
