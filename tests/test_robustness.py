"""Robustness: invalid answers, broken caches, flaky servers, buggy relations, and the CLI's contracts."""

import json
import math

import httpx
import pytest

import jevbench as jb
from jevbench.backends import Executor, FakeCoherent, Refused, SystemOneHTTP, retry_after
from jevbench.engine import run
from jevbench.relations import REGISTRY
from jevbench.schema import Case, SchemaError, read_distribution

from _data import FOUR, FOUR_CASES  # noqa: E402

NOUL = {"type": "noul", "instructions": "?"}
CHOICE = {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}


# ------------------------------------------------------------------ answers

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_probabilities_are_errors(bad):
    with pytest.raises(SchemaError):
        read_distribution({"noul": bad}, NOUL)
    with pytest.raises(SchemaError):
        read_distribution({"probabilities": {"a": bad, "b": 0.5}}, CHOICE)
    with pytest.raises(SchemaError):
        read_distribution({"probabilities": {"0": bad, "1": 0.5}}, {"type": "score", "instructions": "?",
                                                                      "criteria": ["lo", "hi"]})


def test_a_model_answering_nan_never_passes():
    def nan_answers(questions):
        return {k: ({"noul": 0.5} if q["type"] == "noul" else
                    {"probabilities": {o: float("nan") for o in (q["criteria"] if q["type"] == "choice"
                                                                  else map(str, range(len(q["criteria"]))))}})
                for k, q in questions.items()}

    # from the first request: the run stops before it starts, saying the answer is not finite
    with pytest.raises(jb.AnswerFormatError, match="not finite"):
        jb.evaluate(jb.from_callable(lambda s, qs: nan_answers(qs), name="nan"), suite="examples", cache=None,
                    bootstrap=0)

    # later in the run: the NaN answers are errors and leave the run incomplete, not perfect
    coherent, calls = jb.fake("coherent"), {"n": 0}

    def nan_later(state, questions):
        calls["n"] += 1
        return coherent.ask(state, questions) if calls["n"] <= 2 else nan_answers(questions)

    r = jb.evaluate(jb.from_callable(nan_later, name="nan-later"), suite="examples", cache=None, bootstrap=0)
    assert r.errors and r.overall is None


def test_rounding_slack_is_clipped_and_real_excess_is_an_error():
    assert read_distribution({"noul": 1 + 1e-9}, NOUL)["true"] == 1.0
    assert read_distribution({"noul": -1e-12}, NOUL)["true"] == 0.0
    with pytest.raises(SchemaError):
        read_distribution({"noul": 1.1}, NOUL)


def test_numeric_score_levels_are_read_by_one_key_scheme():
    q = {"type": "score", "instructions": "?", "criteria": ["1", "2", "3", "4", "5"]}
    p = [0.1, 0.2, 0.3, 0.3, 0.1]
    by_text = read_distribution({"probabilities": {str(i + 1): v for i, v in enumerate(p)}}, q)
    by_index = read_distribution({"probabilities": {str(i): v for i, v in enumerate(p)}}, q)
    assert [round(by_text[str(i)], 6) for i in range(5)] == p == [round(by_index[str(i)], 6) for i in range(5)]
    with pytest.raises(SchemaError):  # every index and every text: ambiguous
        read_distribution({"probabilities": {str(i): 0.2 for i in range(6)}}, q)


def test_a_missing_option_is_named():
    with pytest.raises(SchemaError, match="missing options"):
        read_distribution({"probabilities": {"a": 1.0}}, CHOICE)


# ------------------------------------------------------------------ relations and engine

def test_merging_never_overwrites_an_existing_option():
    import random

    from jevbench.plan import sealed_context

    q = {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B", "a_or_b": "C", "d": "D"}}
    case = Case(id="c", state="s", questions={"q": q})
    for seed in range(20):
        trial = REGISTRY["option_merge"].build(case, "q", random.Random(seed), sealed_context(None))
        crit = trial.requests["variant"]["q"]["criteria"]
        assert len(crit) == 3 and trial.params["merged"] in crit
        kept = [o for o in q["criteria"] if o not in trial.params["parts"]]
        assert all(o in crit and crit[o] == q["criteria"][o] for o in kept)


def test_a_relation_that_raises_does_not_stop_the_run(monkeypatch):
    def boom(self, case, key, ctx):
        raise RuntimeError("bug")

    monkeypatch.setattr(type(REGISTRY["option_permutation"]), "applicable", boom)
    res = run(FOUR_CASES, Executor(FakeCoherent()), relations=["option_permutation", "batch_order"])
    assert any(e.get("stage") == "applicable" for e in res["errors"])
    assert any(o["relation"] == "batch_order" for o in res["outcomes"])


def test_a_plan_row_naming_a_missing_question_is_an_error_not_a_crash():
    suite = jb.load_suite(FOUR)
    case = suite.cases[0]
    rows = suite.plan.by[(case.id, "option_permutation")]
    rows[0]["requests"] = {"variant": [["nope", {"@": "no_such_question"}]]}
    res = run([case], Executor(FakeCoherent()), relations=["option_permutation"], plan=suite.plan,
              rewrites=suite.rewrites)
    assert any(e.get("stage") == "plan" for e in res["errors"])


def test_progress_is_reported_while_the_run_goes_on():
    seen = []
    res = run(FOUR_CASES, Executor(FakeCoherent()), relations=["option_permutation", "batch_order"],
              progress=lambda case, name: seen.append((case.id, name, len(seen))))
    assert len(seen) == len(FOUR_CASES) * 2 and res["outcomes"]


def test_card_and_scores_agree_at_any_tolerance():
    from jevbench.results import card

    r = jb.evaluate(jb.fake("biased"), suite="examples", cache=None, bootstrap=0, tolerance=0.2)
    rows = {c["relation"]: c for c in card(r.result, fixed=0.2)}
    for rel, score in r.relations.items():
        assert abs((1 - rows[rel]["violation_rate"]) - score) < 1e-9, rel


# ------------------------------------------------------------------ cache

def test_a_truncated_cache_file_is_a_miss(tmp_path):
    ex = Executor(FakeCoherent(), cache_dir=tmp_path)
    qs = {"q": NOUL}
    first = ex.ask("s", qs)
    next(tmp_path.iterdir()).write_text('{"q": {"noul"')
    assert ex.ask("s", qs) == first
    assert not list(tmp_path.glob(".*.tmp"))          # written whole: no temporary file left behind


def test_an_invalid_answer_is_never_cached(tmp_path):
    ex = Executor(jb.from_callable(lambda s, q: {"q": {"noul": 7}}, name="bad"), cache_dir=tmp_path)
    with pytest.raises(SchemaError):
        ex.ask("s", {"q": NOUL})
    assert not list(tmp_path.iterdir())


def test_a_revision_keeps_cached_answers_apart():
    a, b = jb.systemone("http://x/v1/systemone", "m"), jb.systemone("http://x/v1/systemone", "m", revision="r2")
    assert a.name != b.name and b.name.endswith("#r2")


# ------------------------------------------------------------------ HTTP

def _server(handler):
    return SystemOneHTTP("http://a/v1/systemone", "m", transport=httpx.MockTransport(handler))


def test_transport_errors_are_retried(monkeypatch):
    monkeypatch.setattr("jevbench.backends.time.sleep", lambda s: None)
    n = {"k": 0}

    def handle(req):
        n["k"] += 1
        if n["k"] < 3:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"answers": {"q": {"noul": 0.5}}})

    assert _server(handle).ask("s", {"q": NOUL})["q"]["noul"] == 0.5 and n["k"] == 3


def test_retry_after_in_seconds_or_as_a_date():
    assert retry_after("3", 0) == 3.0
    assert retry_after("Wed, 21 Oct 2015 07:28:00 GMT", 0) == 0.0     # in the past
    assert retry_after("not a date", 2) == 4.0 and retry_after(None, 10) == 60.0


def test_a_refusal_is_reported_and_does_not_count_as_the_server_down(monkeypatch):
    b = _server(lambda req: httpx.Response(422, json={"detail": "Too many questions"}))
    with pytest.raises(Refused, match="Too many questions"):
        b.ask("s", {"q": NOUL})
    ex = Executor(b, max_failures=3)
    for _ in range(5):
        with pytest.raises(Refused):
            ex.ask("s", {"q": NOUL})
    assert ex.down is None


def test_a_200_without_answers_is_a_clear_error():
    with pytest.raises(RuntimeError, match="without an 'answers' object"):
        _server(lambda req: httpx.Response(200, json={"oops": 1})).ask("s", {"q": NOUL})


# ------------------------------------------------------------------ rewrite parsing

def test_json_block_and_verdicts():
    from jevbench.rewrite import _json_block, _yes

    assert _json_block('Here: ["a"] and later ["b"]') == ["a"]
    assert _json_block('```json\n{"x": [1, {"y": 2}]}\n```') == {"x": [1, {"y": 2}]}
    assert _json_block("<think>[not json</think> [1, 2]") == [1, 2]
    assert _yes("Let me check. Yes.") and not _yes("No, because yes would be wrong") and not _yes("<think>yes</think>No")


def test_a_bank_resumes_past_a_half_written_line(tmp_path):
    from jevbench.rewrite import build_bank

    out = tmp_path / "bank.jsonl"
    out.write_text(json.dumps({"kind": "paraphrase", "source": "x", "rewrite": "y", "accepted": True}) + "\n" +
                   '{"kind": "paraphrase", "sou')

    class Chat:
        name = "c"

        def __call__(self, prompt, max_tokens=800, **kw):
            return "yes" if "Answer only yes or no" in prompt else '["a rewrite"]'

    build_bank(FOUR_CASES[:1], ["paraphrase"], Chat(), out)
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert rows and all(isinstance(r, dict) for r in rows)


# ------------------------------------------------------------------ CLI and API

def test_eval_exits_non_zero_when_answers_fail(monkeypatch, tmp_path):
    from jevbench import cli

    coherent = jb.fake("coherent")

    def refusing(state, questions):
        if len(questions) > 8:
            raise Refused("HTTP 422: too many questions")
        return coherent.ask(state, questions)

    monkeypatch.setattr(cli, "_model", lambda args: jb.from_callable(refusing, name="refusing"))
    with pytest.raises(SystemExit) as e:
        cli.main(["eval", "--backend", "fake:coherent", "--suite", "examples", "--no-cache"])
    assert e.value.code == 1


def test_report_names_must_match_the_files(tmp_path):
    from jevbench import cli

    r = jb.evaluate(jb.fake(), suite="examples", relations=["option_permutation"], cache=None, bootstrap=0)
    f = r.save(tmp_path / "r.json")
    with pytest.raises(SystemExit, match="names"):
        cli.main(["report", str(f), str(f), "--names", "only-one"])


def test_compare_and_selection_contracts():
    with pytest.raises(ValueError):
        jb.compare([])
    assert jb.select_relations(relations=["diagnostics"]) == ["confidence_consistency", "routing_stability"]
    assert len(jb.select_relations(relations=["all"])) == 50
    r = jb.evaluate(jb.fake(), suite="examples", cache=None, bootstrap=0)
    assert "REP.invariance" not in jb.compare([r], level="dimension")
    assert "option_permutation" in jb.compare([r], level="relation")


def test_coverage_below_the_threshold_leaves_the_run_unscored():
    coherent = jb.fake("coherent")

    def refuse_thresholds(state, questions):     # refuses threshold_sweep's probes only
        if any(q["instructions"].startswith("According to the text, were there more than") for q in questions.values()):
            raise Refused("HTTP 422")
        return coherent.ask(state, questions)

    r = jb.evaluate(jb.from_callable(refuse_thresholds, name="refuse-thresholds"), suite=FOUR, cache=None,
                    bootstrap=0)
    assert r.scores["incomplete"] == ["threshold_sweep"] and r.overall is None
    assert r.dimensions["LOG"] is None and r.dimensions["REP"] is not None
    assert r.scores["checks"]["threshold_sweep/monotonicity"]["coverage"] == 0.0


def test_a_case_whose_base_fails_counts_against_coverage():
    coherent = jb.fake("coherent")
    last = FOUR_CASES[-1].state   # the first case's refusal would stop the run before it starts

    def refuse_one_case(state, questions):
        if state == last:
            raise Refused("HTTP 422")
        return coherent.ask(state, questions)

    r = jb.evaluate(jb.from_callable(refuse_one_case, name="refuse-one-case"), suite=FOUR, cache=None, bootstrap=0)
    assert r.overall is None and len(r.scores["incomplete"]) == 50      # every relation lost a quarter of its tests
