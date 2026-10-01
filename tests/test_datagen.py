"""Fact-first data generation: planning, balance, gold rules, verification checks, freezing."""

import json
from collections import Counter

from jevbench.datagen.domains import DOMAINS
from jevbench.datagen.freeze import freeze
from jevbench.datagen.sample import balance_report, plan_domain
from jevbench.datagen.spec import UNKNOWN
from jevbench.datagen.text import check, verifier_prompt, writer_prompt
from jevbench.schema import load_cases


def test_plans_are_deterministic_and_valid():
    for d in DOMAINS.values():
        a, b = plan_domain(d, 12, seed=3, pool=400), plan_domain(d, 12, seed=3, pool=400)
        assert json.dumps(a) == json.dumps(b)
        for p in a:
            types = Counter(q["type"] for q in p["questions"].values())
            assert 8 <= len(p["questions"]) <= 12
            assert types["noul"] >= 4 and types["choice"] >= 2 and types["score"] >= 1
            assert set(p["gold"]) == set(p["questions"])
            for key, q in p["questions"].items():
                if q["type"] == "choice" and p["gold"][key] != "unknown":
                    assert p["gold"][key] in q["criteria"]


def test_balance_of_archetypes_answers_and_positions():
    for d in DOMAINS.values():
        rep = balance_report(plan_domain(d, 40, seed=0, pool=1500))
        arch = rep["archetype"].values()
        assert max(arch) - min(arch) <= 3
        for key, c in rep["choice_position"].items():
            assert max(c.values()) - min(c.values()) <= 1, key       # rotation makes positions exact
        by_archetype = {q.key for q in d.questions if set(q.depends) <= {"issue", "incident"}}
        for key, c in rep["gold"].items():
            if key in by_archetype:  # answer fixed by the scenario type, whose balance takes priority
                continue
            if set(c) <= {"True", "False", "unknown"} and c["True"] + c["False"] >= 10:
                assert abs(c["True"] - c["False"]) <= 0.35 * (c["True"] + c["False"]), key


def test_writer_never_sees_questions_and_speech_acts_stay_unsaid():
    d = DOMAINS["customer_support"]
    for p in plan_domain(d, 20, seed=1, pool=600):
        prompt = writer_prompt(p)
        assert not any(q["instructions"] in prompt for q in p["questions"].values())
        for name in ("refund_requested", "threatens_cancel", "mentions_competitor"):
            if p["facts"].get(name) is False:
                assert p["mention"][name] == "absent"


def test_mention_versus_truth_questions():
    q = {q.key: q for q in DOMAINS["customer_support"].questions}
    facts = {"issue": "outage", "refund_requested": True, "plan": "enterprise"}
    assert q["refund_asked"].answer(facts, {"refund_requested": "absent"}) is False     # not said -> no
    assert q["enterprise_plan"].answer(facts, {"plan": "absent"}) == UNKNOWN            # not known -> unknown
    assert q["enterprise_plan"].answer(facts, {"plan": "implied"}) is True


def test_check_matches_planned_facts():
    p = plan_domain(DOMAINS["security_ops"], 1, seed=0, pool=50)[0]
    d = DOMAINS["security_ops"]
    exact = {}
    for name, v in p["facts"].items():
        f = d.fact_index[name]
        if p["mention"][name] == "absent":
            exact[name] = "not stated"
        else:
            exact[name] = ("yes" if v else "no") if f.kind == "bool" else (v if f.kind == "int" else v)
    assert check(p, exact) == {}
    name = next(iter(p["facts"]))
    bad = dict(exact, **{name: "something else"})
    assert name in check(p, bad)
    assert all(f'"{n}"' in verifier_prompt(p, "text") for n in p["facts"])


def test_freeze_writes_engine_readable_cases(tmp_path):
    plans = plan_domain(DOMAINS["customer_support"], 3, seed=0, pool=200)
    (tmp_path / "plans.jsonl").write_text("\n".join(json.dumps(p) for p in plans))
    import random

    vocab = ("the customer said that our team would check the invoice and call back today about the order "
             "because a report was late and support needs more time to fix every export").split()

    def text(j, n):  # ordinary words, shuffled differently per draft so they are not near-duplicates
        rng = random.Random(j)
        return " ".join(rng.choice(vocab) for _ in range(n))

    drafts = [{"id": p["id"], "state": text(j, p["length_words"][0] + 10), "writer": "fake"}
              for j, p in enumerate(plans)]
    (tmp_path / "drafts.jsonl").write_text("\n".join(json.dumps(d) for d in drafts))
    verified = [{"id": p["id"], "passed": i != 1, "mismatches": {} if i != 1 else {"tone": {"mention": "implied"}},
                 "verifier": "fake"} for i, p in enumerate(plans)]
    (tmp_path / "verified.jsonl").write_text("\n".join(json.dumps(v) for v in verified))
    res = freeze(tmp_path / "plans.jsonl", tmp_path / "drafts.jsonl", tmp_path / "verified.jsonl",
                 tmp_path / "out", per_domain=5, source="test")
    assert res["kept"] == 2 and res["rejected"]["verifier mismatch"] == 1
    cases = load_cases(tmp_path / "out" / "cases.jsonl")
    assert {c.id for c in cases} == {plans[0]["id"], plans[2]["id"]}      # accepted ones, rebalanced
    assert all(c.meta.get("hierarchies") for c in cases) and all(c.meta.get("thresholds") for c in cases)
    gold = [json.loads(l) for l in (tmp_path / "out" / "gold.jsonl").read_text().splitlines()]
    assert all("gold" not in c.meta for c in cases) and len(gold) == 2
    assert (tmp_path / "out" / "BALANCE.md").exists() and (tmp_path / "out" / "REVIEW.md").exists()


def test_every_plan_states_a_count_and_declares_hierarchies():
    for d in DOMAINS.values():
        for p in plan_domain(d, 20, seed=2, pool=600):
            assert p["thresholds"], p["id"]                       # at least one explicit count
            for key, q in p["questions"].items():
                if q["type"] == "choice":
                    assert len(q["criteria"]) >= 4, key
                    for blocks in p["hierarchies"].get(key, []):
                        assert sorted(o for b in blocks.values() for o in b) == sorted(q["criteria"])


def test_tone_is_never_absent():
    for p in plan_domain(DOMAINS["customer_support"], 30, seed=4, pool=800):
        assert p["mention"]["tone"] in ("explicit", "implied")


def test_unsaid_speech_acts_may_be_read_as_no():
    p = plan_domain(DOMAINS["customer_support"], 1, seed=0, pool=100)[0]
    d = DOMAINS["customer_support"]
    exact = {}
    for name, v in p["facts"].items():
        f = d.fact_index[name]
        exact[name] = "not stated" if p["mention"][name] == "absent" else (
            ("yes" if v else "no") if f.kind == "bool" else v)
    unsaid = [n for n in p["facts"] if d.fact_index[n].speech_act and p["mention"][n] == "absent"]
    for n in unsaid:
        assert check(p, dict(exact, **{n: "no"})) == {}
    silent = [n for n in p["facts"] if not d.fact_index[n].speech_act and p["mention"][n] == "absent"
              and d.fact_index[n].kind == "bool"]
    for n in silent:                                               # a leaked "no" is still a mismatch
        assert n in check(p, dict(exact, **{n: "no"}))


def test_writer_is_told_not_to_state_absences():
    p = plan_domain(DOMAINS["security_ops"], 1, seed=0, pool=100)[0]
    assert "Do not write that something did not happen" in writer_prompt(p)


def test_rejected_drafts_are_rewritten_and_the_latest_attempt_counts(tmp_path):
    from jevbench.datagen.text import _jsonl, verify_states, write_states

    plans = plan_domain(DOMAINS["security_ops"], 2, seed=3)
    pp = tmp_path / "plans.jsonl"
    pp.write_text("".join(json.dumps(p) + "\n" for p in plans))
    drafts, verified = tmp_path / "drafts.jsonl", tmp_path / "verified.jsonl"

    class Chat:
        name = "fake"

        def __init__(self, reply):
            self.reply, self.calls = reply, 0

        def __call__(self, prompt, max_tokens=800, **kw):
            self.calls += 1
            return self.reply(prompt, self.calls)

    def truthful(p):
        from jevbench.datagen.text import _expected
        d = DOMAINS[p["domain"]]
        return json.dumps({k: _expected(d.fact_index[k], v, p["mention"][k]) for k, v in p["facts"].items()})

    assert write_states(pp, drafts, Chat(lambda pr, n: f"text {n}")) == 2
    # the first plan's verifier answer is unreadable twice (fails); the second plan's is truthful
    replies = {plans[0]["id"]: "no json", plans[1]["id"]: truthful(plans[1])}
    verifier = Chat(lambda pr, n: replies[plans[0]["id"] if "text 1" in pr else plans[1]["id"]])
    verify_states(pp, drafts, verified, verifier)
    assert verifier.calls == 3  # the unreadable answer was asked once more
    assert [v["passed"] for v in _jsonl(verified)] == [False, True]

    assert write_states(pp, drafts, Chat(lambda pr, n: "text 3"), redo=verified) == 1
    assert write_states(pp, drafts, Chat(lambda pr, n: "text 4"), redo=verified) == 0  # not yet verified
    replies[plans[0]["id"]] = truthful(plans[0])
    verifier = Chat(lambda pr, n: replies[plans[0]["id"]])
    verify_states(pp, drafts, verified, verifier)
    assert verifier.calls == 1
    latest = {v["id"]: v for v in _jsonl(verified)}
    assert latest[plans[0]["id"]]["attempt"] == 2 and all(v["passed"] for v in latest.values())
