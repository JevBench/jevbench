"""Cases, questions and answer distributions in the System One wire format.

A case is one fixed `state` with a batch of typed `questions`, exactly as sent
to `POST /v1/systemone`. JevBench never edits the state; relations transform
question keys, instructions and criteria only.

Every answer is read as a distribution over *option ids*:
  noul   -> {"true": p, "false": 1 - p}
  choice -> {criterion key: p}
  score  -> {"0": p0, "1": p1, ...} in the question's level order
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

QUESTION_TYPES = ("noul", "choice", "score")


class SchemaError(ValueError):
    pass


FORMAT_URL = "https://github.com/JevBench/jevbench#connecting-your-model"
ANSWER_FORMAT = ('a Noul as {"type": "noul", "noul": p}; a Choice as {"type": "choice", "probabilities": '
                 '{option id: p, ...}} with every option id of the question; a Score as {"type": "score", '
                 '"probabilities": {"0": p, ..., "n-1": p}} keyed by level index (or by every level text)')


class AnswerFormatError(SchemaError):
    """A model's answer is not in the standard Jev format; the message says which question and what to change."""


def validate_question(key: str, q: dict) -> None:
    if not isinstance(q, dict) or q.get("type") not in QUESTION_TYPES:
        raise SchemaError(f"question {key!r}: type must be one of {QUESTION_TYPES}")
    if not isinstance(q.get("instructions"), str) or not q["instructions"].strip():
        raise SchemaError(f"question {key!r}: instructions must be a nonempty string")
    criteria = q.get("criteria")
    if q["type"] == "noul" and criteria not in (None, {}):
        raise SchemaError(f"question {key!r}: a noul takes no criteria")
    if q["type"] == "choice" and (not isinstance(criteria, dict) or len(criteria) < 2
                                  or not all(isinstance(v, str) for v in criteria.values())):
        raise SchemaError(f"question {key!r}: a choice needs at least two string criteria")
    if q["type"] == "score" and (not isinstance(criteria, list) or len(criteria) < 2
                                 or not all(isinstance(v, str) for v in criteria)):
        raise SchemaError(f"question {key!r}: a score needs at least two ordered string levels")


@dataclass(frozen=True)
class Case:
    id: str
    state: Any
    questions: dict
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.questions:
            raise SchemaError(f"case {self.id!r} has no questions")
        for key, q in self.questions.items():
            validate_question(key, q)


def load_cases(path: str | Path) -> list[Case]:
    """Read a JSONL file of {"id", "state", "questions", ...}; other fields go to meta."""
    cases = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        try:
            cases.append(Case(id=str(row["id"]), state=row["state"], questions=row["questions"],
                              meta={k: v for k, v in row.items() if k not in ("id", "state", "questions")}))
        except KeyError as e:
            raise SchemaError(f"{path}:{n}: missing field {e}") from None
    ids = [c.id for c in cases]
    if len(set(ids)) != len(ids):
        raise SchemaError(f"{path}: case ids must be unique")
    return cases


def option_ids(q: dict) -> list[str]:
    if q["type"] == "noul":
        return ["false", "true"]
    if q["type"] == "choice":
        return list(q["criteria"])
    return [str(i) for i in range(len(q["criteria"]))]


EPS = 1e-6  # rounding slack: probabilities this far outside [0, 1] are clipped, farther ones are errors


def _prob(x, what: str) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise SchemaError(f"{what} is not a number: {x!r}") from None
    if not math.isfinite(v):
        raise SchemaError(f"{what} is not finite: {v}")
    if v < -EPS:
        raise SchemaError(f"{what} is negative: {v}")
    return max(0.0, v)


def _score_keys(probs: dict, levels: list) -> list:
    """The keys the answer uses for the levels: all indices ("0", "1", ...) or all level texts, never mixed."""
    idx = [str(i) for i in range(len(levels))]
    texts = [str(t) for t in levels]
    has_idx, has_text = all(k in probs for k in idx), all(k in probs for k in texts)
    if has_idx and has_text and idx != texts:
        raise SchemaError("score answer is ambiguous: it has both every level index and every level text as keys")
    if has_idx:
        return idx
    if has_text:
        return texts
    missing = [k for k in idx if k not in probs]
    raise SchemaError(f"score answer is missing levels {missing} (keys must be all indices or all level texts)")


def read_distribution(answer: dict, q: dict) -> dict[str, float]:
    """Normalize one wire answer to {option id: probability} summing to 1.

    Probabilities must be finite; values within EPS of [0, 1] are clipped, others are errors."""
    if not isinstance(answer, dict):
        raise SchemaError(f"answer is not an object: {answer!r}"[:200])
    if q["type"] == "noul":
        if "noul" not in answer:
            raise SchemaError("noul answer has no 'noul' probability")
        p = _prob(answer["noul"], "noul probability")
        if p > 1.0 + EPS:
            raise SchemaError(f"noul probability out of range: {p}")
        p = min(1.0, p)
        return {"false": 1.0 - p, "true": p}
    probs = answer.get("probabilities")
    if not isinstance(probs, dict):
        raise SchemaError("choice/score answer has no probabilities")
    if q["type"] == "choice":
        missing = [k for k in q["criteria"] if k not in probs]
        if missing:
            raise SchemaError(f"choice answer is missing options {missing}")
        raw = {k: _prob(probs[k], f"probability of {k!r}") for k in q["criteria"]}
    else:
        keys = _score_keys(probs, q["criteria"])
        raw = {str(i): _prob(probs[k], f"probability of level {i}") for i, k in enumerate(keys)}
    total = sum(raw.values())
    if total <= 0:
        raise SchemaError("answer probabilities must have a positive sum")
    return {k: v / total for k, v in raw.items()}


def tv(a: dict[str, float], b: dict[str, float]) -> float:
    """Total variation distance over the union of option ids."""
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


def argmax(d: dict[str, float]) -> str:
    return max(d, key=d.get)


def renormalized(d: dict[str, float], keep) -> dict[str, float]:
    keep = list(keep)
    total = sum(d[k] for k in keep)
    return {k: (d[k] / total if total > 0 else 1.0 / len(keep)) for k in keep}
