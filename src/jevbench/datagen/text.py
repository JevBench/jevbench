"""Write states from planned facts, verify them by extraction, and freeze accepted cases.

write   A writer model turns each plan's facts into a state in the planned style and
        length. It is told how each fact is mentioned and never sees the questions.
verify  A verifier model from another family reads only the state and reports each
        planned fact's value, or "not stated". A draft is accepted only if every
        explicit and implied fact comes back with its planned value and every absent
        fact comes back "not stated". A rejected draft may be rewritten with a new seed
        (`write --redo verified.jsonl`); the latest attempt of each plan counts.
freeze  Accepted drafts that pass length, token and near-duplicate checks become
        cases.jsonl (what the engine reads), gold.jsonl and facts.jsonl (kept apart
        so the engine never sees them), plus a balance report and a review page.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from jevbench.datagen.domains import DOMAINS
from jevbench.rewrite import _json_block

MENTION_RULE = {
    "explicit": "state this plainly",
    "implied": "make this clear from context, without stating it directly",
}


def _value_text(fact, value) -> str:
    """The value as the verifier answers it."""
    if fact.kind == "bool":
        return "yes" if value else "no"
    return str(value).replace("_", " ")


def _writer_text(fact, value) -> str:
    """The fact as the writer reads it."""
    if fact.kind == "cat" and fact.labels:
        return f"{fact.topic or fact.describe}: {fact.labels[value]}"
    return f"{fact.topic or fact.describe}: {_value_text(fact, value)}"


def writer_prompt(plan: dict) -> str:
    d = DOMAINS[plan["domain"]]
    arche = next(a for a in d.archetypes if a.name == plan["archetype"])
    shown, hidden = [], []
    for name, value in plan["facts"].items():
        f = d.fact_index[name]
        level = plan["mention"][name]
        if level == "absent":
            hidden.append(f"- {f.topic or f.describe}" + (f" ({f.absent_note})" if f.absent_note else ""))
        else:
            shown.append(f"- {_writer_text(f, value)} ({MENTION_RULE[level]})")
    lo, hi = plan["length_words"]
    parts = [
        f"You are writing realistic test data for a {d.title.lower()} system. Write one {plan['style']} about "
        f"this situation: {arche.description}.",
        "",
        "The text must convey exactly these facts:",
        *shown,
    ]
    if hidden:
        parts += ["", "The text must not mention, hint at or let anyone infer the following, in any direction:",
                  *hidden]
    parts += ["", "Leave everything that is not listed above unmentioned. Do not write that something did not "
              "happen, was not found, is absent or is unknown: such sentences state a fact too."]
    parts += [
        "",
        "You may add realistic details (names, dates, product names, small talk) as long as they do not change or "
        "add to the facts above.",
        f"Length: {lo} to {hi} words. Write in English. Output only the text itself, with no title, labels, notes "
        "or explanation.",
    ]
    return "\n".join(parts)


def verifier_prompt(plan: dict, state: str) -> str:
    d = DOMAINS[plan["domain"]]
    lines = []
    for name in plan["facts"]:
        f = d.fact_index[name]
        if f.kind == "bool":
            allowed = '"yes", "no" or "not stated"'
        elif f.kind == "cat" and f.labels:  # the same meaning of each value that the writer was given
            allowed = ", ".join(f'"{v}" ({f.labels[v]})' for v in f.values) + ' or "not stated"'
        elif f.kind == "cat":
            allowed = ", ".join(f'"{v}"' for v in f.values) + ' or "not stated"'
        else:
            allowed = 'a whole number or "not stated"'
        lines.append(f'- "{name}": {f.describe}. Answer {allowed}.')
    return "\n".join([
        "Read the text and report what it says about each item. Use only the allowed answers. Answer \"not "
        "stated\" when the text neither says nor clearly implies it.",
        "", "Text:", state, "", "Items:", *lines, "",
        "Return only a JSON object mapping each item name to its answer.",
    ])


def _expected(fact, value, level):
    if level == "absent":
        return "not stated"
    return _value_text(fact, value) if fact.kind != "int" else value


def _normalize(fact, answer):
    if isinstance(answer, str):
        a = answer.strip().lower().replace("_", " ")
        if a in ("not stated", "not mentioned", "unknown", "none stated", "n/a"):
            return "not stated"
        if fact.kind == "int":
            m = re.search(r"-?\d[\d,]*", a)
            return int(m.group().replace(",", "")) if m else a
        if fact.kind == "bool":
            return {"true": "yes", "false": "no"}.get(a, a)
        return a
    if isinstance(answer, bool):
        return "yes" if answer else "no"
    if isinstance(answer, (int, float)) and fact.kind == "int":
        return int(answer)
    return answer


def check(plan: dict, extracted: dict) -> dict:
    d = DOMAINS[plan["domain"]]
    mismatches = {}
    for name, value in plan["facts"].items():
        f = d.fact_index[name]
        want = _expected(f, value, plan["mention"][name])
        got = _normalize(f, extracted.get(name, "missing"))
        if isinstance(want, str) and f.kind == "cat":
            want = want.lower()
        if f.speech_act and want == "not stated" and got == "no":
            continue  # an unsaid speech act ("does the customer ask for a refund?") is correctly read as "no"
        if got != want:
            mismatches[name] = {"planned": want, "extracted": got, "mention": plan["mention"][name]}
    return mismatches


def _jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _latest(rows):
    """The last record for each id: a rewrite replaces an earlier attempt."""
    return {r["id"]: r for r in rows}


def write_states(plans_path, out_path, chat, max_tokens=4000, progress=None, redo=None):
    """Write a draft for every plan that has none. With `redo` (a verified.jsonl), write a new attempt,
    with a new seed, for every plan whose latest draft was verified and failed."""
    plans = _jsonl(plans_path)
    out = Path(out_path)
    drafts = _latest(_jsonl(out)) if out.exists() else {}
    failed = set()
    if redo:
        failed = {i for i, v in _latest(_jsonl(redo)).items()
                  if not v["passed"] and v.get("attempt", 1) == drafts.get(i, {}).get("attempt", 1)}
    todo = [p for p in plans if p["id"] not in drafts or p["id"] in failed]
    with out.open("a", encoding="utf-8") as f:
        for i, p in enumerate(todo):
            attempt = drafts[p["id"]].get("attempt", 1) + 1 if p["id"] in drafts else 1
            key = p["id"] if attempt == 1 else f"{p['id']}#{attempt}"
            text = chat(writer_prompt(p), max_tokens, seed=int.from_bytes(key.encode(), "big") % 2**31).strip()
            f.write(json.dumps({"id": p["id"], "attempt": attempt, "state": text, "writer": chat.name},
                               ensure_ascii=False) + "\n")
            f.flush()
            if progress:
                progress(i + 1, len(todo))
    return len(todo)


def verify_states(plans_path, drafts_path, out_path, chat, progress=None):
    """Verify the latest draft of every plan that has not been verified in that attempt."""
    plans = {p["id"]: p for p in _jsonl(plans_path)}
    drafts = list(_latest(_jsonl(drafts_path)).values())
    out = Path(out_path)
    done = {(r["id"], r.get("attempt", 1)) for r in _jsonl(out)} if out.exists() else set()
    todo = [d for d in drafts if (d["id"], d.get("attempt", 1)) not in done]
    with out.open("a", encoding="utf-8") as f:
        for i, dr in enumerate(todo):
            p = plans[dr["id"]]
            extracted = {}
            for seed in (None, 1):  # an unreadable answer is asked once more, sampled
                kw = {} if seed is None else {"seed": seed, "temperature": 0.7}
                try:
                    extracted = _json_block(chat(verifier_prompt(p, dr["state"]), 1500, **kw))
                except (ValueError, json.JSONDecodeError):
                    extracted = {}
                if isinstance(extracted, dict) and extracted:
                    break
            if not isinstance(extracted, dict):
                extracted = {}
            mism = check(p, extracted)
            f.write(json.dumps({"id": dr["id"], "attempt": dr.get("attempt", 1), "extracted": extracted,
                                "mismatches": mism, "passed": not mism and bool(extracted),
                                "verifier": chat.name}, ensure_ascii=False) + "\n")
            f.flush()
            if progress:
                progress(i + 1, len(todo))
