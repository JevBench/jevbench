"""Freeze verified drafts into a dataset: cases, gold, facts, a balance report and a review page."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from jevbench.datagen.domains import DOMAINS
from jevbench.datagen.sample import balance_report
from jevbench.datagen.text import _jsonl



def _shingles(text, k=3):
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {tuple(words[i:i + k]) for i in range(max(0, len(words) - k + 1))}


def _tokenizer(name: str | None, subfolder: str | None = None):
    """A Hugging Face tokenizer from the local cache (`pip install jevbench[datagen]`), or None when not asked for.

    Only the states' length is checked, for suites meant for models with a short context: the tool
    itself has no preferred tokenizer or model."""
    if not name:
        return None
    from transformers import AutoTokenizer

    kw = {"subfolder": subfolder} if subfolder else {}
    return AutoTokenizer.from_pretrained(name, local_files_only=True, **kw)


def _rebalance(plans, drafts, verified):
    """Accepted plans first, in the balancer's greedy order over the accepted set; the rest keep plan order."""
    from collections import defaultdict

    from jevbench.datagen.sample import _cost, _features

    ok = [p for p in plans if p["id"] in drafts and verified.get(p["id"], {}).get("passed")]
    rest = [p for p in plans if p not in ok]
    ordered = []
    for dom in dict.fromkeys(p["domain"] for p in ok):
        pool = [p for p in ok if p["domain"] == dom]
        counts = defaultdict(Counter)
        while pool:
            best = min(range(len(pool)), key=lambda i: _cost(counts, pool[i]))
            p = pool.pop(best)
            for feat, val in _features(p):
                counts[feat][val] += 1
            ordered.append(p)
    return ordered + rest


def freeze(plans_path, drafts_path, verified_path, out_dir, per_domain: int, source: str,
           tokenizer: str | None = None, tokenizer_subfolder: str | None = None, max_tokens: int = 480):
    """`tokenizer` (a Hugging Face id) with `max_tokens` also rejects states longer than that in its tokens."""
    plans = _jsonl(plans_path)
    drafts = {d["id"]: d for d in _jsonl(drafts_path)}  # latest attempt
    # a verification counts only for the attempt it read
    verified = {v["id"]: v for v in _jsonl(verified_path)
                if v["id"] in drafts and v.get("attempt", 1) == drafts[v["id"]].get("attempt", 1)}
    tok = _tokenizer(tokenizer, tokenizer_subfolder)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    kept, reasons, seen = [], Counter(), {}
    taken = Counter()
    # plans are over-generated; pick among the accepted ones so the kept set stays balanced
    plans = _rebalance(plans, drafts, verified)
    for p in plans:
        if taken[p["domain"]] >= per_domain:
            reasons["surplus (domain already full)"] += 1
            continue
        d, v = drafts.get(p["id"]), verified.get(p["id"])
        if d is None or v is None:
            reasons["not written or not verified"] += 1
            continue
        if not v["passed"]:
            reasons["verifier mismatch"] += 1
            continue
        words = len(d["state"].split())
        lo, hi = p["length_words"]
        if not 0.8 * lo <= words <= 1.2 * hi:
            reasons["length out of band"] += 1
            continue
        if tok is not None and len(tok(d["state"])["input_ids"]) > max_tokens:
            reasons["too many tokens"] += 1
            continue
        sh = _shingles(d["state"])
        if any(len(sh & other) / max(1, len(sh | other)) > 0.5 for other in seen.get(p["domain"], [])):
            reasons["near duplicate"] += 1
            continue
        seen.setdefault(p["domain"], []).append(sh)
        taken[p["domain"]] += 1
        kept.append((p, d, v, words))

    with (out / "cases.jsonl").open("w", encoding="utf-8") as fc, \
         (out / "gold.jsonl").open("w", encoding="utf-8") as fg, \
         (out / "facts.jsonl").open("w", encoding="utf-8") as ff:
        for p, d, v, words in kept:
            case = {"id": p["id"], "state": d["state"], "questions": p["questions"], "source": source,
                    "domain": p["domain"]}
            if p["thresholds"]:
                case["thresholds"] = p["thresholds"]
            if p.get("hierarchies"):
                case["hierarchies"] = p["hierarchies"]
            fc.write(json.dumps(case, ensure_ascii=False) + "\n")
            fg.write(json.dumps({"id": p["id"], "gold": p["gold"]}, ensure_ascii=False) + "\n")
            ff.write(json.dumps({"id": p["id"], "domain": p["domain"], "archetype": p["archetype"],
                                 "style": p["style"], "length_words": p["length_words"], "words": words,
                                 "facts": p["facts"], "mention": p["mention"], "writer": d["writer"],
                                 "verifier": v["verifier"]}, ensure_ascii=False) + "\n")

    final = [p for p, *_ in kept]
    rep = balance_report(final)
    lines = [f"# Balance report: {out.name}", "", f"Source: {source}", "",
             f"{len(final)} cases kept from {len(plans)} plans; {dict(taken)} per domain.", "",
             "Rejected plans: " + (", ".join(f"{k} {n}" for k, n in reasons.items()) or "none") + ".",
             f"Token check: {f'{tokenizer}, max {max_tokens} tokens' if tok else 'none (word count only)'}.",
             "", "| Dimension | Counts |", "|---|---|"]
    for key in ("archetype", "style", "length", "mention", "question_types"):
        lines.append(f"| {key} | {dict(rep[key])} |")
    lines += ["", "Questions whose answer is fixed by the scenario type (for example feature_failing, "
              "incident_type) follow the archetype balance, not an even answer split.",
              "", "| Question | Gold answers | Correct option position (Choice) |", "|---|---|---|"]
    for key, c in sorted(rep["gold"].items()):
        pos = dict(sorted(rep["choice_position"].get(key, {}).items()))
        lines.append(f"| {key} | {dict(sorted(c.items()))} | {pos or ''} |")
    mism = Counter()
    for v in verified.values():
        for name, m in v["mismatches"].items():
            mism[(name, m["mention"])] += 1
    if mism:
        lines += ["", "Verifier mismatches by fact and mention level (all drafts): " +
                  ", ".join(f"{n}/{lvl} {k}" for (n, lvl), k in mism.most_common())]
    (out / "BALANCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    review = [f"# Review: {out.name}", "",
              "Each case: the planned facts (with how the text should mention them), the state the writer produced, "
              "and the questions with their gold answers. Please flag anything wrong, unnatural or ambiguous.", ""]
    for p, d, v, words in kept:
        dom = DOMAINS[p["domain"]]
        review += [f"## {p['id']} — {dom.title} / {p['archetype']} / {p['style']} ({words} words)", "",
                   "| Fact | Value | Mention |", "|---|---|---|"]
        for name, value in p["facts"].items():
            review.append(f"| {name} | {value} | {p['mention'][name]} |")
        review += ["", "> " + d["state"].replace("\n", "\n> "), "", "| Question | Type | Gold |", "|---|---|---|"]
        for key, q in p["questions"].items():
            g = p["gold"][key]
            if q["type"] == "score" and g != "unknown":
                g = f"{g}: {q['criteria'][int(g)]}"
            review.append(f"| {q['instructions']} | {q['type']} | {g} |")
        review.append("")
    (out / "REVIEW.md").write_text("\n".join(review), encoding="utf-8")
    return {"kept": len(final), "per_domain": dict(taken), "rejected": dict(reasons)}
