"""The taxonomy classifies every relation; archived/taxonomy.md and the README's dimension table are current."""

from pathlib import Path

import pytest

from jevbench import taxonomy
from jevbench.relations import REGISTRY
from _data import BANK, FOUR_CASES  # noqa: E402,F401


def test_every_registered_relation_is_classified_once():
    taxonomy.check_registry(REGISTRY)
    names = [e.name for e in taxonomy.IMPLEMENTED + taxonomy.DIAGNOSTICS + taxonomy.PLANNED]
    assert len(names) == len(set(names))


def test_operation_scheme_shape():
    assert [p.id for p in taxonomy.PILLARS] == ["REP", "BAT", "MEA", "LOG", "CHO"]
    per = {p.id: sum(e.group.startswith(p.id + ".") for e in taxonomy.IMPLEMENTED) for p in taxonomy.PILLARS}
    assert per == {"REP": 15, "BAT": 5, "MEA": 17, "LOG": 10, "CHO": 3}
    assert len(taxonomy.GROUPS) == 11 and all(e.diagnostic for e in taxonomy.DIAGNOSTICS)


def test_one_law_per_relation():
    for e in taxonomy.IMPLEMENTED:
        assert len(e.primary) == 1, e.name
        assert e.law in ("E", "I", "L"), e.name
    # LOG holds the inequalities, and only they
    assert all((e.law == "L") == e.group.startswith("LOG.") for e in taxonomy.IMPLEMENTED)
    assert not any(e.diagnostic for e in taxonomy.IMPLEMENTED)


def test_entries_use_known_groups_edits_and_laws():
    for e in taxonomy.IMPLEMENTED + taxonomy.DIAGNOSTICS + taxonomy.PLANNED:
        assert e.group in taxonomy.GROUP, e.name
        assert set(e.edits) <= set(taxonomy.EDITS), e.name
        assert e.law in taxonomy.LAWS, e.name
        assert e.diagnostic or e.group.split(".")[0] in taxonomy.PILLAR, e.name


def test_no_relation_edits_the_state():
    assert "state" not in taxonomy.EDITS
    for e in taxonomy.IMPLEMENTED + taxonomy.DIAGNOSTICS + taxonomy.PLANNED:
        assert "state" not in e.edits, e.name


def test_every_request_carries_the_cases_own_state():
    from jevbench.backends import Executor, FakeCoherent
    from jevbench.engine import run
    from jevbench.rewrite import RewriteBank
    from jevbench.schema import load_cases

    class Recorder(FakeCoherent):
        name = "recorder"
        seen = []

        def ask(self, state, questions):
            self.seen.append(state)
            return super().ask(state, questions)

    cases = FOUR_CASES
    rec = Recorder()
    result = run(cases, Executor(rec), repeats=1, rewrites=BANK,
                 relations=["all", "diagnostics"])
    assert set(result["relations"]) == set(REGISTRY)
    assert rec.seen and set(rec.seen) <= {c.state for c in cases}
    assert not [e for e in result["errors"] if "state" in e.get("error", "")]


def test_relation_objects_expose_their_classification():
    rel = REGISTRY["batch_solo"]
    assert (rel.group, rel.edits, rel.law) == ("BAT.isolation", ("batch",), "E")


def test_all_means_scored_relations_and_diagnostics_run_only_when_named():
    from jevbench.engine import resolve_relations

    assert set(resolve_relations("all")) == set(REGISTRY) - {"confidence_consistency", "routing_stability"}
    assert resolve_relations("diagnostics") == ["confidence_consistency", "routing_stability"]
    assert resolve_relations(["batch_solo", "routing_stability"]) == ["batch_solo", "routing_stability"]


def test_archived_taxonomy_is_current():
    doc = Path(__file__).resolve().parents[1] / "archived" / "taxonomy.md"
    if not doc.exists():
        pytest.skip("archived/taxonomy.md is not part of this distribution")
    text = doc.read_text(encoding="utf-8")
    section = text[text.index(taxonomy.START): text.index(taxonomy.END) + len(taxonomy.END)]
    assert section == taxonomy.markdown(), "run: jevbench taxonomy --write archived/taxonomy.md"


def test_readme_dimension_table_is_current():
    readme = Path(__file__).resolve().parents[1] / "README.md"
    if not readme.exists():
        pytest.skip("README.md is not part of this distribution")
    lines = readme.read_text(encoding="utf-8").splitlines()
    for p in taxonomy.PILLARS:
        n = sum(len(taxonomy._members(g.id)) for g in taxonomy.GROUPS if g.pillar == p.id)
        row = next((line for line in lines if line.startswith(f"| **{p.id}** |")), None)
        assert row is not None, f"the README's dimension table has no row for {p.id}"
        assert row.startswith(f"| **{p.id}** | {p.title} |") and row.rstrip().endswith(f"| {n} |"), \
            f"the README's row for {p.id} differs from jevbench.taxonomy ({p.title}, {n} relations)"


def test_markdown_tables_have_no_stray_pipes():
    for line in taxonomy.tables().splitlines():
        if line.startswith("| ") and not line.startswith("|---"):
            assert line.replace("\\|", "").count("|") == 8, line


def test_declared_checks_match_what_relations_emit():
    from jevbench.backends import Executor, FakeCoherent
    from jevbench.engine import run
    from jevbench.rewrite import RewriteBank
    from jevbench.schema import load_cases

    result = run(FOUR_CASES, Executor(FakeCoherent()), repeats=1,
                 rewrites=BANK, relations=["all", "diagnostics"])
    emitted = {}
    for o in result["outcomes"]:
        emitted.setdefault(o["relation"], set()).add(o["check"])
    for name, checks in emitted.items():
        e = taxonomy.entry(name)
        assert checks == set(e.primary), name
    for (rel, check) in taxonomy.CHECK_NOTES:
        assert check in taxonomy.entry(rel).primary
