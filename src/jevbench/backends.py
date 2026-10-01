"""Backends that answer a (state, questions) request, plus a caching executor.

`SystemOneHTTP` speaks the `POST /v1/systemone` wire format of Jev-compatible
servers, self-hosted or hosted. `CallableBackend` wraps any
Python function (a model loaded in process). `fake:*` backends are deterministic toys for tests and demos.

A backend whose `concurrent` attribute is true may be called from several threads
at once; the executor serializes the calls of any other backend.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import re
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Protocol


class Backend(Protocol):
    name: str

    def ask(self, state: Any, questions: dict) -> dict:
        """Return the wire `answers` object: {key: {"noul": p} | {"probabilities": {...}}}."""


class Refused(RuntimeError):
    """The server answered, but refused the request (HTTP 4xx other than 429): the server is up."""


def retry_after(header, attempt: int) -> float:
    """Seconds to wait: a Retry-After header in seconds or as an HTTP date, else exponential backoff."""
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            from email.utils import parsedate_to_datetime

            try:
                return max(0.0, parsedate_to_datetime(header).timestamp() - time.time())
            except (TypeError, ValueError):
                pass
    return float(min(60, 2 ** attempt))


class SystemOneHTTP:
    """`url` is one endpoint or several replicas of the same model (a list, or comma-separated).
    Replicas must serve identical weights: they share one name and one cache.

    A request takes a free replica and holds it until its answer is back, so no replica ever has
    more than `per_replica` requests (default 1: exactly the answers of a sequential run, even on
    servers that batch on the GPU) and no request waits while another replica is idle."""

    concurrent = True

    def __init__(self, url, model: str, api_key: str | None = None, timeout: float = 180.0,
                 min_interval: float = 0.0, max_attempts: int = 8, per_replica: int = 1, transport=None,
                 revision: str | None = None):
        import httpx

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = httpx.Client(timeout=timeout, headers=headers, transport=transport,
                                   limits=httpx.Limits(max_connections=256, max_keepalive_connections=64))
        self.urls = [u.strip() for u in (url.split(",") if isinstance(url, str) else url) if u.strip()]
        if not self.urls:
            raise ValueError("no URL given")
        self.url, self.model = self.urls[0], model
        self.per_replica = max(1, per_replica)
        self._free = queue.Queue()
        for _ in range(self.per_replica):
            for u in self.urls:
                self._free.put(u)
        self.min_interval, self.max_attempts = min_interval, max_attempts
        self._last = 0.0
        self._lock = threading.Lock()
        # the name keys the request cache: a revision (weights, checkpoint) keeps versions apart
        self.name = f"systemone:{model}@{self.url}" + (f"#{revision}" if revision else "")
        self.replicas = len(self.urls)
        self.slots = self.replicas * self.per_replica  # the concurrency that keeps every replica busy
        self._answered = False   # until one request succeeds, a refused connection means no server at the URL

    def _pace(self):
        """Wait out `min_interval` since the previous request (for rate-limited hosted APIs)."""
        if self.min_interval <= 0:
            return
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def ask(self, state, questions):
        import httpx

        # Nouls carry "criteria": null internally; strict servers reject the null, and it means "absent"
        wire = {k: {f: v for f, v in q.items() if not (f == "criteria" and v is None)} for k, q in questions.items()}
        url = self._free.get()  # blocks until a replica is free
        try:
            last = None
            for attempt in range(self.max_attempts):
                self._pace()
                try:
                    r = self.client.post(url, json={"model": self.model, "state": state, "questions": wire})
                except httpx.TransportError as e:  # connection refused or reset, timeout: try again
                    last = f"{type(e).__name__}: {e}"
                    if isinstance(e, httpx.ConnectError) and not self._answered and attempt >= 2:
                        # nothing listens at the URL and nothing ever answered: say so now, not after minutes
                        raise RuntimeError(f"{self.name}: nothing is listening at {url} ({last}); start the "
                                           "server first, or check the URL and port") from None
                    time.sleep(retry_after(None, attempt))
                    continue
                if r.status_code == 429 or r.status_code >= 500:
                    last = f"HTTP {r.status_code}: {r.text[:200]}"
                    time.sleep(retry_after(r.headers.get("retry-after"), attempt))
                    continue
                if r.status_code >= 400:
                    raise Refused(f"{self.name}: HTTP {r.status_code}: {r.text[:500]}")
                try:
                    answers = r.json()["answers"]
                except (ValueError, KeyError, TypeError):
                    raise RuntimeError(f"{self.name}: HTTP {r.status_code} without an 'answers' object: "
                                       f"{r.text[:300]}") from None
                self._answered = True
                return answers
            raise RuntimeError(f"{self.name}: no answer after {self.max_attempts} attempts; last: {last}")
        finally:
            self._free.put(url)


class CallableBackend:
    """Wraps `fn(state, questions) -> answers` (the wire `answers` object) as a backend.

    `fn` may be a list of functions: replicas of one model (for example one per GPU). A request
    takes a free replica and holds it until it returns, so each function is called by one thread
    at a time. A single function is called by one thread at a time too, unless `concurrent`.

    `name` identifies the model in results and in the request cache. Without it the backend is
    not `cacheable`: two different models behind functions of the same name must never share
    cached answers."""

    def __init__(self, fn, name: str | None = None, concurrent: bool = False):
        fns = list(fn) if isinstance(fn, (list, tuple)) else [fn]
        if not fns or not all(callable(f) for f in fns):
            raise TypeError("from_callable needs a function (state, questions) -> answers, or a list of them")
        self.cacheable = bool(name)
        self.name = name or f"callable:{getattr(fns[0], '__qualname__', type(fns[0]).__name__)} (unnamed)"
        self.replicas = len(fns)
        self._free = queue.Queue()
        for f in fns:
            self._free.put(f)
        # several replicas are safe to call together (one thread each); one function only if it says so
        self.concurrent = self.replicas > 1 or concurrent
        self.slots = self.replicas

    def ask(self, state, questions):
        fn = self._free.get()
        try:
            return fn(state, questions)
        finally:
            self._free.put(fn)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _unit(*parts: str) -> float:
    h = hashlib.sha256("\x1f".join(parts).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


class FakeCoherent:
    """A Luce-type scorer: each option gets an independent score from its description.

    Invariant to option order, option ids, question keys and batching, and it
    satisfies IIA exactly. It knows nothing about negation or conjunction.
    """

    name = "fake:coherent"
    concurrent = True

    def _score(self, state, text):
        s, t = set(_tokens(str(state))), _tokens(text)
        overlap = sum(w in s for w in t) / max(1, len(t))
        return 4.0 * overlap + (_unit(str(state), text) - 0.5)

    def ask(self, state, questions):
        out = {}
        for key, q in questions.items():
            if q["type"] == "noul":
                z = self._score(state, q["instructions"]) - 1.0
                out[key] = {"type": "noul", "noul": 1.0 / (1.0 + math.exp(-z))}
            else:
                items = (list(q["criteria"].items()) if q["type"] == "choice"
                         else [(str(i), v) for i, v in enumerate(q["criteria"])])
                scores = {k: self._score(state, q["instructions"] + " " + d) for k, d in items}
                m = max(scores.values())
                z = sum(math.exp(v - m) for v in scores.values())
                out[key] = {"type": q["type"], "probabilities": {k: math.exp(v - m) / z for k, v in scores.items()}}
        return out


class FakeBiased(FakeCoherent):
    """FakeCoherent plus three defects: first-option bias, key-name reading, batch leakage."""

    name = "fake:biased"

    def ask(self, state, questions):
        n = len(questions)
        out = {}
        for key, q in questions.items():
            shift = 0.8 * _unit(key) + 0.1 * n
            if q["type"] == "noul":
                z = self._score(state, q["instructions"]) - 1.0 + shift
                out[key] = {"type": "noul", "noul": 1.0 / (1.0 + math.exp(-z))}
                continue
            items = (list(q["criteria"].items()) if q["type"] == "choice"
                     else [(str(i), v) for i, v in enumerate(q["criteria"])])
            scores = {k: self._score(state, q["instructions"] + " " + d) for k, d in items}
            first = items[0][0]
            scores[first] += 1.5
            m = max(scores.values())
            z = sum(math.exp(v - m) for v in scores.values())
            out[key] = {"type": q["type"], "probabilities": {k: math.exp(v - m) / z for k, v in scores.items()}}
        return out


def make_backend(spec: str, *, url: str | None = None, api_key: str | None = None,
                 min_interval: float = 0.0) -> Backend:
    """`systemone:<model>`, `fake:coherent` or `fake:biased` (for `jevbench run`)."""
    kind, _, arg = spec.partition(":")
    if kind == "systemone":
        if not url:
            raise ValueError("systemone backend needs --url")
        if not arg:
            raise ValueError('systemone backend needs the model name the server expects: "systemone:<model>"')
        return SystemOneHTTP(url, arg, api_key=api_key, min_interval=min_interval)
    if spec == "fake:coherent":
        return FakeCoherent()
    if spec == "fake:biased":
        return FakeBiased()
    raise ValueError(f"unknown backend {spec!r}")


def _short(x, n: int = 200) -> str:
    r = repr(x)
    return r if len(r) <= n else r[:n] + "..."


def _check_answers(answers, questions, name):
    """Every answer must be in the standard Jev format (jevbench.schema.read_distribution); otherwise an
    AnswerFormatError names the question, shows what came back and states the format."""
    from jevbench.schema import ANSWER_FORMAT, FORMAT_URL, AnswerFormatError, SchemaError, read_distribution

    def fail(msg):
        raise AnswerFormatError(f"{name}: {msg}. JevBench reads the standard Jev answer format: {ANSWER_FORMAT}. "
                                f"See {FORMAT_URL}") from None

    if not isinstance(answers, dict):
        fail(f"the answers must be an object {{question key: answer}}, got {type(answers).__name__} {_short(answers)}")
    if "answers" in answers and "answers" not in questions and isinstance(answers["answers"], dict):
        fail("got a whole response {'answers': ...}; a function given to from_callable returns the answers "
             "object itself")
    for key, q in questions.items():
        if key not in answers:
            fail(f"no answer for question {key!r} (the answers have the keys {_short(sorted(map(str, answers)), 120)})")
        try:
            read_distribution(answers[key], q)
        except SchemaError as e:
            fail(f"question {key!r} ({q['type']}): {e}; got {_short(answers[key])}")


class ModelError(RuntimeError):
    """The model could not answer at all (server unreachable, request refused, function failed): nothing to score."""


class Budget(Exception):
    """The request budget is spent: no further uncached request is sent."""


class BackendDown(Budget):
    """`max_failures` requests in a row failed: the backend is taken to be down and the run stops."""


class Executor:
    """Runs requests with an on-disk cache keyed by backend, request and repeat index.

    The request is hashed with insertion order preserved, so reordered options
    or questions are distinct requests. `repeat` separates deliberate reruns.

    Thread-safe. With a cache, identical requests in flight at the same time are
    sent once and share the answer, exactly as a sequential run reads the second
    one from the cache. `max_requests` caps the uncached requests sent.
    `cache_dir=":memory:"` keeps the cache in memory for this executor only.
    """

    def __init__(self, backend: Backend, cache_dir: str | Path | None = None, max_requests: int | None = None,
                 max_failures: int | None = 25):
        self.backend = backend
        self.max_failures, self._failures_in_a_row, self.down = max_failures, 0, None
        self._memory = {} if cache_dir == ":memory:" else None
        self.cache_dir = Path(cache_dir) if cache_dir and self._memory is None else None
        self.max_requests = max_requests
        self.calls = 0
        self.cache_hits = 0
        self.seconds = 0.0
        self._sent = 0
        self._lock = threading.Lock()
        self._inflight: dict = {}
        self._serial = None if getattr(backend, "concurrent", False) else threading.Lock()
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, state, questions, repeat):
        blob = json.dumps({"b": self.backend.name, "s": state, "q": questions, "r": repeat},
                          ensure_ascii=False, separators=(",", ":"))
        name = f"{hashlib.sha256(blob.encode()).hexdigest()}.json"
        return name if self._memory is not None else self.cache_dir / name

    def _cached(self, key):
        """The cached answers, or None (a miss) when absent or unreadable, e.g. half written by a killed job."""
        if self._memory is not None:
            hit = self._memory.get(key)
            return None if hit is None else json.loads(hit)
        try:
            return json.loads(key.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _store(self, key, answers):
        """Written whole or not at all: a temporary file in the same directory, then an atomic rename."""
        if self._memory is not None:
            self._memory[key] = json.dumps(answers)
            return
        tmp = key.with_name(f".{key.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(answers), encoding="utf-8")
        os.replace(tmp, key)

    def _reserve(self):
        if self.down:
            raise BackendDown(self.down)
        if self.max_requests is not None and self._sent >= self.max_requests:
            raise Budget()
        self._sent += 1

    def _call(self, state, questions) -> dict:
        start = time.perf_counter()
        try:
            if self._serial:
                with self._serial:
                    answers = self.backend.ask(state, questions)
            else:
                answers = self.backend.ask(state, questions)
        except Refused:
            with self._lock:
                self._failures_in_a_row = 0   # the server is up: it answered with a refusal
            raise
        except Exception as e:
            with self._lock:
                self._failures_in_a_row += 1
                if self.max_failures and self._failures_in_a_row >= self.max_failures and not self.down:
                    self.down = f"{self._failures_in_a_row} requests in a row failed; last: {e!r}"[:500]
            raise
        with self._lock:
            self.seconds += time.perf_counter() - start
            self.calls += 1
            self._failures_in_a_row = 0
        return answers

    def ask(self, state, questions, repeat: int = 0) -> dict:
        if self.cache_dir is None and self._memory is None:
            with self._lock:
                self._reserve()
            answers = self._call(state, questions)
            _check_answers(answers, questions, self.backend.name)
            return answers
        path = self._path(state, questions, repeat)
        with self._lock:
            pending = self._inflight.get(path)
            if pending is None:
                hit = self._cached(path)
                if hit is not None:
                    self.cache_hits += 1
                    return hit
                self._reserve()
                mine = self._inflight[path] = Future()
            else:
                self.cache_hits += 1
        if pending is not None:  # the same request is on its way: share its answer, as the cache would
            return json.loads(json.dumps(pending.result()))
        try:
            answers = self._call(state, questions)
            _check_answers(answers, questions, self.backend.name)   # never cache an answer that cannot be read
            self._store(path, answers)
            mine.set_result(answers)
            return answers
        except BaseException as e:
            mine.set_exception(e)
            raise
        finally:
            with self._lock:
                self._inflight.pop(path, None)
