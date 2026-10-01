"""Concurrent runs give the same outcomes as sequential ones, and send each request once."""

import threading
import time

import pytest

from jevbench.backends import Executor, FakeBiased, FakeCoherent, SystemOneHTTP
from jevbench.engine import run
from jevbench.rewrite import RewriteBank
from jevbench.schema import load_cases

from _data import BANK, FOUR_CASES  # noqa: E402
SAME = ("outcomes", "bases", "errors", "relations", "cases")


class Slow(FakeBiased):
    """Answers late, so that many requests really are in flight at once."""

    name = "fake:slow"

    def ask(self, state, questions):
        time.sleep(0.002)
        return super().ask(state, questions)


class NotThreadSafe(FakeCoherent):
    name = "fake:single"
    concurrent = False

    def __init__(self):
        self.inside = 0

    def ask(self, state, questions):
        self.inside += 1
        assert self.inside == 1, "called from two threads at once"
        time.sleep(0.001)
        out = super().ask(state, questions)
        self.inside -= 1
        return out


def _run(backend, cache, concurrency, **kw):
    ex = Executor(backend, cache_dir=cache)
    return run(FOUR_CASES, ex, seed=3, rewrites=BANK, concurrency=concurrency, **kw)


@pytest.mark.parametrize("cached", [True, False])
def test_outcomes_do_not_depend_on_concurrency(tmp_path, cached):
    one = _run(Slow(), tmp_path / "a" if cached else None, 1)
    many = _run(Slow(), tmp_path / "b" if cached else None, 16)
    for field in SAME:
        assert one[field] == many[field], field
    assert one["outcomes"] and not one["errors"]
    # identical requests in flight together are sent once, as the cache would do sequentially
    assert (one["requests"], one["cache_hits"]) == (many["requests"], many["cache_hits"])


def test_a_backend_that_is_not_thread_safe_is_called_one_at_a_time():
    res = _run(NotThreadSafe(), None, 8, relations=["option_permutation", "batch_order"])
    assert res["outcomes"] and not res["errors"]


def test_budget_caps_uncached_requests(tmp_path):
    res = _run(FakeBiased(), tmp_path, 8, max_requests=40)
    assert res["truncated_by_budget"] and res["requests"] <= 40


def _counting_server(delays):
    """A mock of several replicas that records the most requests any one of them had at once."""
    import httpx

    busy, peak, lock = {}, {}, threading.Lock()

    def handle(request):
        host = request.url.host
        with lock:
            busy[host] = busy.get(host, 0) + 1
            peak[host] = max(peak.get(host, 0), busy[host])
        time.sleep(delays.get(host, 0.001))
        with lock:
            busy[host] -= 1
        qs = __import__("json").loads(request.content)["questions"]
        return httpx.Response(200, json={"answers": {k: {"type": "noul", "noul": 0.5} for k in qs}})

    return httpx.MockTransport(handle), peak


@pytest.mark.parametrize("per_replica", [1, 2])
def test_no_replica_gets_more_than_its_share_and_all_are_used(per_replica):
    from concurrent.futures import ThreadPoolExecutor

    transport, peak = _counting_server({"a": 0.02, "b": 0.001, "c": 0.005})  # one slow replica
    b = SystemOneHTTP("http://a/v1/systemone,http://b/v1/systemone,http://c/v1/systemone", "m",
                      per_replica=per_replica, transport=transport)
    assert b.slots == 3 * per_replica and b.name == "systemone:m@http://a/v1/systemone"
    q = {"q": {"type": "noul", "instructions": "x"}}
    with ThreadPoolExecutor(max_workers=b.slots * 3) as pool:  # more threads than slots
        list(pool.map(lambda i: b.ask(f"s{i}", q), range(90)))
    assert set(peak) == {"a", "b", "c"} and max(peak.values()) == per_replica


def test_the_default_concurrency_fills_every_replica_slot():
    import jevbench as jb

    assert jb.systemone("http://a/x,http://b/x", "m").slots == 2
    assert jb.systemone(["http://a/x", "http://b/x"], "m", per_replica=2).slots == 4


def test_a_run_stops_when_the_backend_is_down():
    class Down:
        name, concurrent, calls = "down", True, 0

        def ask(self, state, questions):
            Down.calls += 1
            raise RuntimeError("HTTP 500: CUDA error")

    ex = Executor(Down(), max_failures=3)   # each case's base fails first, so its trials never start
    res = run(FOUR_CASES * 3, ex, concurrency=1)
    assert res["backend_down"] and "3 requests in a row failed" in res["backend_down"]
    assert Down.calls == 3 and not res["truncated_by_budget"] and not res["outcomes"]
