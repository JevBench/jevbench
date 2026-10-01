"""Natural rewrites, generated once, judged, and frozen as a JSONL bank.

Templates are auditable but are only one wording each. Natural rewrites test
what users actually write. To stay reproducible, JevBench never paraphrases at
test time: `jevbench rewrite` asks a chat model for candidates, asks a judge
(the same model unless another is given) to judge each one (both directions
where the relation is symmetric),
and writes every candidate with its verdict to a bank file. `jevbench run
--rewrites bank.jsonl` then uses only accepted, frozen entries. Entries carry
an `audited` field for human review; `--audited-only` restricts runs to them.

Kinds:
  paraphrase     question instructions -> same question, other words
  negation       Noul instructions -> a question whose answer is always the opposite
  description    one option description -> same meaning, other words
  translate:<l>  a whole question (instructions and criteria texts) -> language <l>
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from jevbench.schema import Case

LANGUAGES = {"zh": "Simplified Chinese", "es": "Spanish", "de": "German", "fr": "French", "ja": "Japanese"}


class ChatClient:
    """OpenAI-compatible /v1/chat/completions; temperature 0 unless set.

    `extra` is merged into every request body (for example {"reasoning_effort": "low"}
    for a reasoning model on vLLM); per-call keyword arguments override it (for example seed=...).
    """

    def __init__(self, url: str, model: str, api_key: str | None = None, timeout: float = 180.0,
                 temperature: float = 0.0, extra: dict | None = None):
        import httpx

        self.client = httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {api_key}"} if api_key else {})
        self.url, self.model = url, model
        self.temperature, self.extra = temperature, dict(extra or {})
        self.name = f"chat:{model}@{url}"

    def __call__(self, prompt: str, max_tokens: int = 800, **overrides) -> str:
        import time

        import httpx

        from jevbench.backends import retry_after

        body = {"model": self.model, "temperature": self.temperature, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}], **self.extra, **overrides}
        last = None
        for attempt in range(8):
            try:
                r = self.client.post(self.url, json=body)
            except httpx.TransportError as e:  # connection refused or reset, timeout: try again
                last = f"{type(e).__name__}: {e}"
                time.sleep(retry_after(None, attempt))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                time.sleep(retry_after(r.headers.get("retry-after"), attempt))
                continue
            r.raise_for_status()
            try:
                return r.json()["choices"][0]["message"]["content"] or ""
            except (ValueError, KeyError, IndexError, TypeError):
                raise RuntimeError(f"{self.name}: unexpected response: {r.text[:300]}") from None
        raise RuntimeError(f"{self.name}: no answer after 8 attempts; last: {last}")


def _json_block(text: str):
    """The first JSON value (object or list) in a model's output: code fences and text around it are ignored."""
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S)
    dec = json.JSONDecoder()
    for m in re.finditer(r"[\[{]", text):
        try:
            value, _ = dec.raw_decode(text, m.start())
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError(f"no JSON in model output: {text[:200]!r}")


def _yes(text: str) -> bool:
    """A judge's verdict: its first word if that is yes or no, else the last yes or no it says
    ("Let me check. Yes." -> yes; "No, because ..." -> no). Reasoning in <think> blocks is ignored."""
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S)
    words = re.findall(r"[a-z]+", text.lower())
    if words and words[0] in ("yes", "no"):
        return words[0] == "yes"
    verdicts = [w for w in words if w in ("yes", "no")]
    return bool(verdicts) and verdicts[-1] == "yes"


GENERATE = {
    "paraphrase": ("Rewrite the question below in {n} different ways. Each rewrite must ask exactly the same "
                   "thing, so that for any text a careful reader gives the same answer, but use different words "
                   "and sentence structure. Keep every condition and exception. Return only a JSON list of "
                   "{n} strings.\nQuestion: {source}"),
    "negation": ("Rewrite the yes/no question below in {n} different ways so that, for any text, the correct "
                 "answer to each rewrite is always the opposite (yes becomes no, no becomes yes). Use natural "
                 "wording, such as antonyms or rephrasing, not a mechanical 'is it false that'. Keep every "
                 "condition and exception. Return only a JSON list of {n} strings.\nQuestion: {source}"),
    "description": ("Rewrite the answer-option description below in {n} different ways with exactly the same "
                    "meaning and scope, in different words. Return only a JSON list of {n} strings.\n"
                    "Description: {source}"),
    "translate": ("Translate this question object into {language}. Translate the values of 'instructions' and "
                  "every criteria text; keep the JSON structure and any criteria keys unchanged. Return only the "
                  "translated JSON object.\n{source}"),
}

JUDGE = {
    "paraphrase": ("Question A: {a}\nQuestion B: {b}\nFor every possible text, would a careful reader give the same "
                   "answer to A and to B? Answer only yes or no."),
    "negation": ("Question A: {a}\nQuestion B: {b}\nFor every possible text, is the correct answer to B always the "
                 "opposite of the correct answer to A (yes versus no)? Answer only yes or no."),
    "description": ("Description A: {a}\nDescription B: {b}\nDo A and B describe exactly the same answer, with the "
                    "same meaning and scope? Answer only yes or no."),
    "translate": ("Original (English): {a}\nTranslation ({language}): {b}\nIs the translation faithful, with the "
                  "same meaning and structure and nothing added or removed? Answer only yes or no."),
}


def _source(kind: str, case: Case, key: str, option: str | None = None):
    q = case.questions[key]
    if kind.startswith("translate"):
        return json.dumps({"instructions": q["instructions"], "criteria": q.get("criteria")}, ensure_ascii=False)
    if kind == "description":
        return q["criteria"][option]
    return q["instructions"]


def sources(cases, kinds):
    """Yield (kind, source text) pairs, deduplicated, in case order."""
    seen = set()
    for case in cases:
        for key, q in case.questions.items():
            for kind in kinds:
                if kind == "negation" and q["type"] != "noul":
                    continue
                if kind == "description":
                    if q["type"] != "choice":
                        continue
                    items = [_source(kind, case, key, o) for o in q["criteria"]]
                else:
                    items = [_source(kind, case, key)]
                for s in items:
                    if (kind, s) not in seen:
                        seen.add((kind, s))
                        yield kind, s


def _valid_translation(source: str, rewrite) -> bool:
    src = json.loads(source)
    if not isinstance(rewrite, dict) or not isinstance(rewrite.get("instructions"), str):
        return False
    a, b = src.get("criteria"), rewrite.get("criteria")
    if a is None:
        return b in (None, {})
    if isinstance(a, dict):
        return isinstance(b, dict) and list(b) == list(a) and all(isinstance(v, str) for v in b.values())
    return isinstance(b, list) and len(b) == len(a) and all(isinstance(v, str) for v in b)


def generate(chat: ChatClient, kind: str, source: str, n: int, judge: ChatClient | None = None,
             judge_tokens: int = 5, max_tokens: int = 800) -> list[dict]:
    """Candidates from `chat`, each judged by `judge` (default: `chat`). A reasoning model spends
    tokens before its verdict: give it a larger `judge_tokens`."""
    judge = judge or chat
    base, _, lang = kind.partition(":")
    language = LANGUAGES.get(lang, lang)
    if base == "translate":
        try:
            candidates = [_json_block(chat(GENERATE["translate"].format(language=language, source=source),
                                           max_tokens))]
        except ValueError:
            candidates = []
    else:
        try:
            candidates = _json_block(chat(GENERATE[base].format(n=n, source=source), max_tokens))
        except ValueError:
            candidates = []
        if not isinstance(candidates, list):
            candidates = []
        candidates = [c.strip() for c in candidates if isinstance(c, str) and c.strip()]
        candidates = [c for i, c in enumerate(candidates) if c != source and c not in candidates[:i]][:n]
    entries = []
    for c in candidates:
        if base == "translate":
            ok = _valid_translation(source, c)
            votes = [_yes(judge(JUDGE["translate"].format(a=source, b=json.dumps(c, ensure_ascii=False),
                                                          language=language), judge_tokens))] if ok else []
            accepted = ok and all(votes)
        else:
            votes = [_yes(judge(JUDGE[base].format(a=source, b=c), judge_tokens)),
                     _yes(judge(JUDGE[base].format(a=c, b=source), judge_tokens))]
            accepted = all(votes)
        entries.append({"kind": kind, "source": source, "rewrite": c, "accepted": accepted, "votes": votes,
                        "generator": chat.name, "judge": judge.name, "audited": None})
    return entries


def build_bank(cases, kinds, chat: ChatClient, out: str | Path, n: int = 3, progress=None,
               judge: ChatClient | None = None, judge_tokens: int = 5, max_tokens: int = 800,
               concurrency: int = 1):
    """Append new entries to `out`; sources already present are skipped (resumable).

    Up to `concurrency` sources are worked on at once; entries are written in source order."""
    from concurrent.futures import ThreadPoolExecutor

    out = Path(out)
    done = set()
    if out.exists():
        good = []
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:   # a line half written when a run was killed: drop it, redo its source
                    continue
                good.append(line)
                done.add((e["kind"], e["source"]))
        out.write_text("".join(g + "\n" for g in good), encoding="utf-8")
    todo = [(k, s) for k, s in sources(cases, kinds) if (k, s) not in done]
    out.parent.mkdir(parents=True, exist_ok=True)

    def one(item):
        kind, source = item
        entries = generate(chat, kind, source, n, judge=judge, judge_tokens=judge_tokens, max_tokens=max_tokens)
        if not entries:  # record the attempt so a rerun does not retry forever
            entries = [{"kind": kind, "source": source, "rewrite": None, "accepted": False, "votes": [],
                        "generator": chat.name, "judge": (judge or chat).name, "audited": None}]
        return kind, entries

    with out.open("a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for i, (kind, entries) in enumerate(pool.map(one, todo)):
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            f.flush()
            if progress:
                progress(i + 1, len(todo), kind)
    return out


@dataclass
class RewriteBank:
    entries: list[dict]
    audited_only: bool = False

    @classmethod
    def load(cls, path, audited_only=False):
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
        return cls(rows, audited_only)

    def get(self, kind: str, source: str) -> list:
        out = []
        for e in self.entries:
            if e["kind"] != kind or e["source"] != source or not e["accepted"] or e["rewrite"] is None:
                continue
            if self.audited_only and e.get("audited") is not True:
                continue
            if e.get("audited") is False:  # a human rejected it
                continue
            out.append(e["rewrite"])
        return out

    def languages(self, source: str) -> list[str]:
        kinds = sorted({e["kind"] for e in self.entries if e["kind"].startswith("translate:")})
        return [k for k in kinds if self.get(k, source)]

    def stats(self):
        by = {}
        for e in self.entries:
            s = by.setdefault(e["kind"], {"candidates": 0, "accepted": 0})
            s["candidates"] += e["rewrite"] is not None
            s["accepted"] += bool(e["accepted"])
        return by


def question_source(case: Case, key: str, kind: str, option: str | None = None) -> str:
    return _source(kind, case, key, option)
