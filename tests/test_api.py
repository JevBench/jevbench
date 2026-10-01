"""The public API: suites, selection, evaluate, reports, estimate and the eval command."""

import json
import shutil

import pytest

import jevbench as jb
from jevbench.cli import main
from jevbench.suites import load_suite

from _data import FOUR  # noqa: E402


def test_the_examples_suite_is_a_quick_demo():
    s = load_suite("examples")
    assert len(s.cases) == 1 and s.domains == ["customer_support"] and s.min_n == 1
    r = jb.evaluate(jb.fake("biased"), suite="examples", cache=None, bootstrap=0)
    assert r.overall is not None and len(r.relations) == 50 and r.settings["min_n"] == 1


def test_bundled_suites_load_and_are_intact():
    assert jb.list_suites() == ["examples", "jevbench-240", "jevbench-mini"]
    s = load_suite("jevbench-240")
    assert len(s.cases) == 240 and len(s.domains) == 12
    assert all(sum(c.meta["domain"] == d for c in s.cases) == 20 for d in s.domains)
    assert s.record()["files"]["cases.jsonl"]


def test_the_default_suite_is_mini():
    assert jb.estimate() == {"cases": 240, "relations": 50, "requests": 1248, "trials": 1200}


def test_a_modified_suite_is_refused(tmp_path):
    src = load_suite(FOUR)
    d = tmp_path / "examples"
    shutil.copytree(str(load_suite(FOUR).path), d)
    (d / "cases.jsonl").write_text((d / "cases.jsonl").read_text() + "\n")  # any change at all
    with pytest.raises(ValueError, match="modified"):
        load_suite(str(d))
    assert src.cases


def test_selection_is_the_union_in_taxonomy_order():
    bat = jb.select_relations(dimensions=["BAT"])
    assert bat and all(jb.describe(n)["dimension"] == "BAT" for n in bat)
    mixed = jb.select_relations(groups=["CHO.conditioning"], relations=["de_morgan"])
    assert mixed[0] == "de_morgan" and set(mixed[1:]) == {r["name"] for r in jb.list_relations(group="CHO.conditioning")}
    assert jb.select_relations() == [r["name"] for r in jb.list_relations()]
    assert len(jb.select_relations()) == 50
    with pytest.raises(ValueError, match="unknown groups"):
        jb.select_relations(groups=["CHO.nope"])


def test_evaluate_scores_and_round_trips(tmp_path):
    r = jb.evaluate(jb.fake("biased"), suite=FOUR, cache=None, bootstrap=50)
    assert 0 < r.overall < 1 and set(r.dimensions) == {"REP", "BAT", "MEA", "LOG", "CHO"}
    assert r.result["suite"]["name"] == "test-four" and r.result["suite"]["plan"] == "tests.jsonl.gz"
    assert not r.errors
    back = jb.Report.load(r.save(tmp_path / "r.json"))
    assert back.overall == r.overall and back.name == "fake:biased"
    assert "MEA.partition" in r.table("group") and "MEA.partition" in jb.compare({"a": r, "b": back})


def test_a_partial_evaluation_has_no_overall_score():
    r = jb.evaluate(jb.fake("coherent"), suite=FOUR, dimensions=["CHO"], cache=None, bootstrap=0)
    assert r.overall is None and r.dimensions["CHO"] is not None and r.dimensions["MEA"] is None


def test_domains_select_cases_and_reports_split_by_domain():
    r = jb.evaluate(jb.fake("coherent"), "jevbench-240", domains=["finance_ops", "logistics"],
                    relations=["option_permutation"], repeats=1, cache=":memory:", bootstrap=0)
    assert set(r.result["case_domains"].values()) == {"finance_ops", "logistics"}
    assert len(r.result["cases"]) == 40 and set(r.by_domain()) == {"finance_ops", "logistics"}
    with pytest.raises(ValueError, match="unknown domains"):
        jb.evaluate(jb.fake(), domains=["nope"])


def test_any_function_is_a_model():
    coherent = jb.fake("coherent")
    r = jb.evaluate(lambda state, questions: coherent.ask(state, questions), suite=FOUR,
                    relations=["option_permutation"], cache=None, bootstrap=0)
    assert r.relations["option_permutation"] == 1.0 and r.name.startswith("callable:")


def test_estimate_counts_requests():
    est = jb.estimate(FOUR)
    assert est["cases"] == 4 and est["relations"] == 50 and est["requests"] > est["cases"] * 3


def test_eval_command(tmp_path, capsys):
    out = tmp_path / "r.json"
    main(["eval", "--backend", "fake:coherent", "--suite", FOUR, "--dimensions", "BAT", "--no-cache",
          "--out", str(out)])
    assert "BAT.isolation" in capsys.readouterr().out
    assert json.loads(out.read_text())["jevbench_report"] == 1


def test_callable_replicas_are_each_called_by_one_thread_at_a_time():
    import threading
    import time

    coherent = jb.fake("coherent")
    inside, peak, used, lock = {}, {}, set(), threading.Lock()

    def replica(i):
        def ask(state, questions):
            with lock:
                inside[i] = inside.get(i, 0) + 1
                peak[i] = max(peak.get(i, 0), inside[i])
                used.add(i)
            time.sleep(0.001)
            out = coherent.ask(state, questions)
            with lock:
                inside[i] -= 1
            return out
        return ask

    model = jb.from_callable([replica(i) for i in range(3)], name="coherent-x3")
    assert model.slots == 3 and model.concurrent
    r = jb.evaluate(model, suite=FOUR, relations=["option_permutation", "batch_order"], cache=None,
                    bootstrap=0)
    one = jb.evaluate(jb.fake("coherent"), suite=FOUR, relations=["option_permutation", "batch_order"],
                      cache=None, bootstrap=0)
    assert used == {0, 1, 2} and max(peak.values()) == 1
    assert r.result["outcomes"] == one.result["outcomes"]


def test_an_unnamed_callable_is_cached_for_the_run_only(tmp_path):
    coherent = jb.fake("coherent")
    fn = lambda state, questions: coherent.ask(state, questions)  # noqa: E731
    with pytest.warns(UserWarning, match="no name"):
        jb.evaluate(jb.from_callable(fn), suite=FOUR, relations=["option_permutation"],
                    cache=tmp_path / "c", bootstrap=0)
    assert not (tmp_path / "c").exists()
    jb.evaluate(jb.from_callable(fn, name="coherent-v1"), suite=FOUR, relations=["option_permutation"],
                cache=tmp_path / "c", bootstrap=0)
    assert any((tmp_path / "c").iterdir())


def test_reports_save_and_load_compressed(tmp_path):
    r = jb.evaluate(jb.fake("coherent"), suite="examples", cache=None, bootstrap=0)
    back = jb.Report.load(r.save(tmp_path / "r.json.gz"))
    assert back.overall == r.overall and back.name == r.name
    assert (tmp_path / "r.json.gz").stat().st_size < r.save(tmp_path / "r.json").stat().st_size
