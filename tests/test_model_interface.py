"""Connecting a model: the standard Jev format is read, anything else stops with a message that says what to fix."""

import httpx
import pytest

import jevbench as jb
from jevbench.backends import SystemOneHTTP


def _levels(q):
    return list(q["criteria"]) if q["type"] == "choice" else [str(i) for i in range(len(q["criteria"]))]


def standard(state, questions):
    out = {}
    for k, q in questions.items():
        if q["type"] == "noul":
            out[k] = {"type": "noul", "noul": 0.7}
        else:
            ks = _levels(q)
            out[k] = {"type": q["type"], "probabilities": {x: 1 / len(ks) for x in ks}}
    return out


def _with(change):
    """The standard answers with one kind of answer changed."""
    def fn(state, questions):
        out = standard(state, questions)
        for k, q in questions.items():
            new = change(q, out[k])
            if new is not None:
                out[k] = new
        return out
    return fn


def test_check_accepts_the_standard_format():
    r = jb.check(jb.from_callable(standard, name="standard"))
    assert r["model"] == "standard" and set(r["questions"]) == {"noul", "choice", "score"}
    assert jb.check(jb.fake())["questions"]


@pytest.mark.parametrize("change, says", [
    (lambda q, a: 0.7 if q["type"] == "noul" else None, "(noul)"),
    (lambda q, a: {"probabilities": {"true": 0.7, "false": 0.3}} if q["type"] == "noul" else None, "no 'noul'"),
    (lambda q, a: {"probabilities": list(a["probabilities"].values())} if q["type"] == "choice" else None,
     "no probabilities"),
    (lambda q, a: {"probabilities": dict(list(a["probabilities"].items())[:1])} if q["type"] == "choice" else None,
     "missing options"),
    (lambda q, a: {"probabilities": {int(k): v for k, v in a["probabilities"].items()}} if q["type"] == "score"
     else None, "missing levels"),
    (lambda q, a: {"noul": 70} if q["type"] == "noul" else None, "out of range"),
])
def test_a_nonstandard_answer_names_the_question_and_the_format(change, says):
    with pytest.raises(jb.AnswerFormatError) as e:
        jb.check(jb.from_callable(_with(change)))
    msg = str(e.value)
    assert says in msg and "question '" in msg and "standard Jev answer format" in msg and "got " in msg


def test_returning_the_whole_response_is_named():
    with pytest.raises(jb.AnswerFormatError, match="whole response"):
        jb.check(jb.from_callable(lambda s, qs: {"model": "m", "answers": standard(s, qs)}))


def test_evaluate_stops_before_the_run_when_the_format_is_wrong():
    with pytest.raises(jb.AnswerFormatError):
        jb.evaluate(jb.from_callable(_with(lambda q, a: 0.5)), suite="examples", cache=None, bootstrap=0)


@pytest.mark.parametrize("fn, says", [
    (lambda questions: {}, "(state, questions)"),
    (lambda s, qs: 1 / 0, "ZeroDivisionError"),
])
def test_a_model_that_cannot_answer_raises_model_error(fn, says):
    with pytest.raises(jb.ModelError, match=r"could not answer the first request") as e:
        jb.evaluate(jb.from_callable(fn), suite="examples", cache=None, bootstrap=0)
    assert says in str(e.value)


def test_a_server_that_refuses_or_breaks_the_wire_format_raises_model_error():
    refuse = SystemOneHTTP("http://a/v1/systemone", "m",
                           transport=httpx.MockTransport(lambda r: httpx.Response(422, json={"detail": "no"})))
    with pytest.raises(jb.ModelError, match="refused the first request"):
        jb.check(refuse)
    no_answers = SystemOneHTTP("http://a/v1/systemone", "m",
                               transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"result": 1})))
    with pytest.raises(jb.ModelError, match="without an 'answers' object"):
        jb.check(no_answers)


def test_failures_during_a_run_are_shown_in_the_report():
    calls = {"n": 0}

    def flaky(state, questions):
        calls["n"] += 1
        if calls["n"] > 3:
            raise RuntimeError("server overloaded")
        return standard(state, questions)

    r = jb.evaluate(jb.from_callable(flaky), suite="examples", cache=None, bootstrap=0)
    assert r.errors and "requests failed" in repr(r)
    assert "server overloaded" in r.table("dimension")


def test_check_command(capsys):
    from jevbench.cli import main

    main(["check", "--backend", "fake:coherent"])
    assert "jevbench check: OK" in capsys.readouterr().out


def test_no_server_at_the_url_is_reported_at_once():
    import time

    def refuse(request):
        raise httpx.ConnectError("Connection refused", request=request)

    start = time.perf_counter()
    with pytest.raises(jb.ModelError, match="nothing is listening at"):
        jb.check(SystemOneHTTP("http://a/v1/systemone", "m", transport=httpx.MockTransport(refuse)))
    assert time.perf_counter() - start < 5
