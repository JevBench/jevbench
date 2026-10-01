"""Natural rewrites: generation keeps judged, distinct candidates; banks drive the natural relations;
building a bank concurrently matches a sequential build, resumes, and can use a separate judge."""

import json

from jevbench.backends import Executor, FakeCoherent
from jevbench.engine import run
from jevbench.rewrite import RewriteBank, build_bank, generate
from jevbench.schema import load_cases
from jevbench.suites import load_suite


from _data import FOUR, FOUR_CASES  # noqa: E402


class FakeChat:
    name = "chat:fake"

    def __init__(self, generations, verdict="yes"):
        self.generations, self.verdict = generations, verdict

    def __call__(self, prompt, max_tokens=800):
        if prompt.rstrip().endswith("Answer only yes or no."):
            return self.verdict
        return self.generations


def test_generate_keeps_only_judged_distinct_rewrites():
    chat = FakeChat(json.dumps(["Is it late?", "Is it late?", "Was it delayed?", "Is delivery late?"]))
    entries = generate(chat, "paraphrase", "Is delivery late?", n=3)
    assert [e["rewrite"] for e in entries] == ["Is it late?", "Was it delayed?"]
    assert all(e["accepted"] and e["votes"] == [True, True] for e in entries)
    assert not any(e["accepted"] for e in generate(FakeChat(json.dumps(["Is it late?"]), "no"),
                                                  "paraphrase", "Is delivery late?", 3))


def test_translation_must_keep_structure():
    src = json.dumps({"instructions": "Which team?", "criteria": {"a": "Billing", "b": "Tech"}})
    good = FakeChat(json.dumps({"instructions": "哪个团队？", "criteria": {"a": "账单", "b": "技术"}}))
    bad = FakeChat(json.dumps({"instructions": "哪个团队？", "criteria": {"x": "账单", "b": "技术"}}))
    assert generate(good, "translate:zh", src, 1)[0]["accepted"]
    assert not generate(bad, "translate:zh", src, 1)[0]["accepted"]


def test_bank_drives_natural_relations(tmp_path):
    case = FOUR_CASES[0]
    key = next(k for k, q in case.questions.items() if q["type"] == "noul")
    q = case.questions[key]
    bank = tmp_path / "bank.jsonl"
    rows = [
        {"kind": "paraphrase", "source": q["instructions"], "rewrite": "Is an export job failing?", "accepted": True},
        {"kind": "paraphrase", "source": q["instructions"], "rewrite": "rejected one", "accepted": False},
        {"kind": "negation", "source": q["instructions"], "rewrite": "Are all exports succeeding?", "accepted": True},
        {"kind": "negation", "source": q["instructions"], "rewrite": "human says no", "accepted": True,
         "audited": False},
    ]
    bank.write_text("\n".join(json.dumps(r) for r in rows))
    result = run([case], Executor(FakeCoherent()), relations=["instruction_paraphrase", "natural_negation"],
                 repeats=1, rewrites=RewriteBank.load(bank))
    got = [(o["relation"], o["targets"][0], o["detail"]["rewrite"]) for o in result["outcomes"]]
    assert got == [("instruction_paraphrase", key, "Is an export job failing?"),
                   ("natural_negation", key, "Are all exports succeeding?")]


class Chat:
    def __init__(self, name, verdict="yes"):
        self.name, self.verdict, self.calls = name, verdict, 0

    def __call__(self, prompt, max_tokens=800, **kw):
        self.calls += 1
        if "Answer only yes or no" in prompt:
            return self.verdict
        if "Translate" in prompt:
            src = json.loads(prompt.split("\n", 1)[1])
            crit = src["criteria"]
            return json.dumps({"instructions": "译:" + src["instructions"],
                               "criteria": ({k: "译:" + v for k, v in crit.items()} if isinstance(crit, dict)
                                            else None if crit is None else ["译:" + v for v in crit])})
        source = prompt.rsplit(": ", 1)[1]
        return json.dumps([f"{source} (v{i})" for i in range(3)])


def test_concurrent_build_matches_sequential_and_resumes(tmp_path):
    cases = load_suite(FOUR).cases
    kinds = ["paraphrase", "negation", "description", "translate:zh"]
    seq, par = tmp_path / "seq.jsonl", tmp_path / "par.jsonl"
    build_bank(cases, kinds, Chat("gen"), seq, concurrency=1)
    build_bank(cases, kinds, Chat("gen"), par, concurrency=16)
    assert seq.read_text() == par.read_text()
    again = Chat("gen")
    build_bank(cases, kinds, again, par, concurrency=16)
    assert again.calls == 0  # every source is already in the bank


def test_a_separate_judge_decides(tmp_path):
    cases = load_suite(FOUR).cases[:1]
    out = tmp_path / "b.jsonl"
    build_bank(cases, ["paraphrase"], Chat("gen"), out, judge=Chat("strict", verdict="no"))
    bank = RewriteBank.load(out)
    assert bank.entries and all(e["judge"] == "strict" and not e["accepted"] for e in bank.entries)
