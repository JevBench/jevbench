"""The relation taxonomy: one source of truth for grouping, coverage and planned work.

Every relation is one metamorphic transformation with one law. Two axes
classify it.

1. The operation that links the two distributions its oracle compares
   (dimension, then group):
   REP  Representation consistency  bijection of answers        same events, another description
   BAT  Batch independence          identity                    the other questions of the request
   MEA  Probability measure         many-to-one map, identity   different events of one measure
   LOG  Logical coherence           order                       propositions ordered by entailment
   CHO  Choice-set coherence        restriction to a sub-menu   the menu a Choice is conditioned on

2. What the relation edits: the question key, its instructions, its criteria
   (options or levels), its answer type, or the rest of the batch. No relation
   edits the state: it is the outside input the model is asked about, fixed
   for every test (the engine enforces this).

Every law has one of three forms: (E) two distributions are equal, (I) an
identity holds, (L) an inequality holds. A law may be stated for every element
of an index fixed by the question (every template, option, level or pair); the
relation then holds for a question only if it holds for every element.

Checks on auxiliary response fields (confidence, routing) are diagnostics: they
test the output format rather than the distribution, so they sit outside the
dimensions, never enter a score and only run when named explicitly.

The full taxonomy in archived/taxonomy.md is generated from this module
(`jevbench taxonomy --write archived/taxonomy.md`) and a test keeps the two in sync.
"""

from __future__ import annotations

from dataclasses import dataclass

EDITS = ("key", "instructions", "criteria", "type", "batch")

LAWS = {
    "E": "distributional equality",
    "I": "identity",
    "L": "inequality",
    "field": "field agrees with probabilities",
}


@dataclass(frozen=True)
class Pillar:
    id: str
    title: str
    expects: str
    oracle: str


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    question: str

    @property
    def pillar(self) -> str:
        return self.id.split(".")[0]


@dataclass(frozen=True)
class Entry:
    name: str
    group: str
    edits: tuple
    law: str                  # form of the law: E, I or L (field for diagnostics)
    summary: str
    primary: tuple = ("tv",)  # the one check the relation emits
    implemented: bool = True
    exploratory: bool = False  # reported, but kept out of dimension and overall scores

    @property
    def diagnostic(self) -> bool:
        return self.group in DIAGNOSTIC_GROUP


PILLARS = (
    Pillar("REP", "Representation consistency", "two questions describe the same events",
           "bijection of answers: P′ = σ#P"),
    Pillar("BAT", "Batch independence", "the question is fixed and only its companions change",
           "identity: P_q|B′ = P_q|B"),
    Pillar("MEA", "Probability measure coherence", "the questions ask about different events of one measure",
           "many-to-one map of outcomes, or the additive identity it induces"),
    Pillar("LOG", "Logical coherence", "the questions are propositions ordered by entailment",
           "order: A ⊨ B ⇒ P(A) ≤ P(B), and the bounds of Boolean combinations"),
    Pillar("CHO", "Choice-set coherence", "the menu a Choice is conditioned on changes",
           "restriction to a sub-menu: P′|K = P|K"),
)

GROUPS = (
    Group("REP.invariance", "Invariance", "Does a meaning-preserving edit leave the answer unchanged?"),
    Group("REP.equivariance", "Equivariance", "Does relabelling the answers relabel the probabilities?"),
    Group("REP.binding", "Binding", "Do answers follow descriptions and instructions when ids or keys mislead?"),
    Group("REP.type", "Answer type", "Does asking the same thing as another answer type change the answer?"),
    Group("BAT.isolation", "Isolation", "Do the other questions in the request change the answer?"),
    Group("MEA.complement", "Complement", "Do a question and its negation sum to one?"),
    Group("MEA.partition", "Partition", "Do merged, split, duplicated and refined options keep their mass?"),
    Group("MEA.marginalisation", "Marginalisation", "Does a question derived from another receive the pushforward?"),
    Group("LOG.bounds", "Bounds", "Do conjunctions, disjunctions and counts respect their bounds?"),
    Group("LOG.monotonicity", "Monotonicity", "Do answers fall with stricter thresholds, claims and quantifiers?"),
    Group("CHO.conditioning", "Conditioning", "Does changing the menu renormalise the remaining options?"),
)

# not a dimension: never scored, run only when named
DIAGNOSTIC_GROUPS = (
    Group("DIAG.fields", "Response fields", "Do confidence and routing fields agree with the probabilities?"),
)
DIAGNOSTIC_GROUP = {g.id: g for g in DIAGNOSTIC_GROUPS}


def _e(name, group, edits, form, summary, check="tv", **kw):
    return Entry(name, group, edits, form, summary, primary=(check,), **kw)


IMPLEMENTED = (
    # REP.invariance
    _e("instruction_paraphrase", "REP.invariance", ("instructions",), "E", "judged paraphrase of the instructions"),
    _e("cross_lingual", "REP.invariance", ("instructions", "criteria"), "E", "question translated, state untouched"),
    _e("typo_noise", "REP.invariance", ("instructions",), "E", "typos, casing, punctuation"),
    _e("verbosity", "REP.invariance", ("instructions",), "E", "redundant clarification added"),
    _e("key_rename", "REP.invariance", ("key",), "E", "neutral question key"),
    _e("description_paraphrase", "REP.invariance", ("criteria",), "E", "judged paraphrase of one option"),
    _e("de_morgan", "REP.invariance", ("instructions", "batch"), "E", "not (A and B) equals not A or not B",
       check="nand_vs_or_not"),
    # REP.equivariance
    _e("option_permutation", "REP.equivariance", ("criteria",), "E", "options reordered, Score levels reversed"),
    _e("option_rename", "REP.equivariance", ("criteria",), "E", "neutral option ids, same descriptions"),
    _e("clone_symmetry", "REP.equivariance", ("criteria",), "E", "two identical options get equal probability",
       check="clone_symmetry"),
    # REP.binding
    _e("key_instruction_conflict", "REP.binding", ("key",), "E", "negated or swapped question keys"),
    _e("name_description_conflict", "REP.binding", ("criteria",), "E", "option ids exchanged, descriptions fixed"),
    _e("description_swap", "REP.binding", ("criteria",), "E", "descriptions exchanged, ids fixed"),
    # REP.type
    _e("noul_as_choice", "REP.type", ("type", "criteria"), "E", "Noul versus yes/no Choice", check="abs_diff"),
    _e("noul_as_score", "REP.type", ("type", "criteria"), "E", "Noul versus two-level Score", check="abs_diff"),
    # BAT.isolation
    _e("batch_solo", "BAT.isolation", ("batch",), "E", "asked alone versus in its batch"),
    _e("batch_order", "BAT.isolation", ("batch",), "E", "question order reversed"),
    _e("duplicate_question", "BAT.isolation", ("batch",), "E", "same question twice in one request",
       check="within_request_tv"),
    _e("batch_content", "BAT.isolation", ("batch",), "E", "other questions replaced, size fixed"),
    _e("batch_size_sweep", "BAT.isolation", ("batch",), "E", "batches of 2, 5 and 10 questions"),
    # MEA.complement
    _e("negation_wrapper", "MEA.complement", ("instructions", "batch"), "I", "P(Q) + P(not Q) = 1, templates",
       check="complement_gap"),
    _e("natural_negation", "MEA.complement", ("instructions", "batch"), "I", "P(Q) + P(Q') = 1, natural opposite",
       check="complement_gap"),
    _e("choice_complement", "MEA.complement", ("type", "instructions", "batch"), "I", "Noul 'not o' = 1 - P(o)",
       check="complement_gap"),
    _e("score_complement", "MEA.complement", ("type", "instructions", "batch"), "I",
       "Noul 'not level k' = 1 - P(k)", check="complement_gap"),
    _e("compound_negation", "MEA.complement", ("instructions", "batch"), "I", "P(not (A and B)) + P(A and B) = 1",
       check="complement_gap"),
    # MEA.partition
    _e("option_merge", "MEA.partition", ("criteria",), "E", "'a or b' gets P(a) + P(b)", check="tv_to_coarsened"),
    _e("option_split", "MEA.partition", ("criteria",), "E", "'o and X' + 'o and not X' = P(o)",
       check="tv_after_collapse"),
    _e("option_clone", "MEA.partition", ("criteria",), "E", "a clone and its original keep P(o)",
       check="tv_after_collapse"),
    _e("similarity_effect", "MEA.partition", ("criteria",), "E", "a near-duplicate and its original keep P(b)",
       check="tv_after_collapse"),
    _e("partition_hierarchy", "MEA.partition", ("criteria",), "E", "coarse blocks = sums of their options",
       check="tv_to_coarsened"),
    _e("score_granularity", "MEA.partition", ("criteria",), "E", "adjacent levels merged keep their sum",
       check="tv_to_coarsened"),
    _e("extreme_level", "MEA.partition", ("criteria",), "E", "a level beyond the top refines the top level",
       check="tv_after_collapse"),
    _e("option_closure", "MEA.partition", ("criteria",), "E", "each option in turn replaced by a catch-all",
       check="catch_all_tv"),
    # MEA.marginalisation
    _e("score_cumulative", "MEA.marginalisation", ("type", "instructions", "batch"), "I",
       "'level k or higher' = upper tail, every k", check="tail_gap_max"),
    _e("choice_indicator", "MEA.marginalisation", ("type", "instructions", "batch"), "I",
       "Noul 'is it o?' = P(o), every o", check="indicator_gap"),
    _e("pair_choice_marginals", "MEA.marginalisation", ("type", "instructions", "batch"), "I",
       "four-way pair Choice has the Nouls as marginals", check="marginal_gap"),
    _e("inclusion_exclusion", "MEA.marginalisation", ("instructions", "batch"), "I",
       "P(A and B) + P(A or B) = P(A) + P(B)", check="inclusion_exclusion"),
    # LOG.bounds
    _e("frechet_and_upper", "LOG.bounds", ("instructions", "batch"), "L", "P(A and B) <= min(P(A), P(B))",
       check="excess"),
    _e("nary_and_upper", "LOG.bounds", ("instructions", "batch"), "L", "P(all) <= min P(Ai)", check="excess"),
    _e("nary_and_lower", "LOG.bounds", ("instructions", "batch"), "L", "P(all) >= sum P(Ai) - (n - 1)",
       check="excess"),
    _e("nary_or_upper", "LOG.bounds", ("instructions", "batch"), "L", "P(any) <= min(1, sum P(Ai))", check="excess"),
    _e("nary_or_lower", "LOG.bounds", ("instructions", "batch"), "L", "P(any) >= max P(Ai)", check="excess"),
    _e("count_upper", "LOG.bounds", ("instructions", "batch"), "L", "P(at least two) <= sum P(Ai) / 2",
       check="excess"),
    _e("count_lower", "LOG.bounds", ("instructions", "batch"), "L", "P(at least two) >= (sum P(Ai) - 1) / (n - 1)",
       check="excess"),
    # LOG.monotonicity
    _e("threshold_sweep", "LOG.monotonicity", ("instructions", "batch"), "L", "'more than k' falls with k",
       check="monotonicity"),
    _e("entailment_strength", "LOG.monotonicity", ("instructions", "batch"), "L", "Q1 entails Q2 => P(Q1) <= P(Q2)",
       check="chain"),
    _e("quantifier_monotonicity", "LOG.monotonicity", ("instructions", "batch"), "L",
       "all <= at least two <= at least one", check="chain"),
    # CHO.conditioning
    _e("irrelevant_option", "CHO.conditioning", ("criteria",), "E", "off-topic option added", check="iia_tv"),
    _e("remove_option_iia", "CHO.conditioning", ("criteria",), "E", "each option in turn removed", check="iia_tv"),
    _e("pairwise_iia", "CHO.conditioning", ("criteria",), "E", "each pair of options asked alone", check="iia_tv"),
)

DIAGNOSTICS = (
    Entry("confidence_consistency", "DIAG.fields", (), "field", "confidence is a function of the probabilities",
          primary=("fits_definition",)),
    Entry("routing_stability", "DIAG.fields", (), "field", "0.8 routing survives key, order, batch edits",
          primary=("route_flip",)),
)

# checks that need a note wherever they are listed
CHECK_NOTES = {
    ("score_cumulative", "tail_gap_max"): "largest gap over the levels k; strict, so read it with the graded score",
}

PLANNED = ()  # nothing planned right now; add Entry(..., implemented=False)


ENTRIES = {e.name: e for e in IMPLEMENTED + DIAGNOSTICS + PLANNED}
GROUP = {g.id: g for g in GROUPS + DIAGNOSTIC_GROUPS}
PILLAR = {p.id: p for p in PILLARS}


def entry(name: str) -> Entry:
    return ENTRIES[name]


def order_key(name: str):
    """Sort relations by dimension, group, then taxonomy order; diagnostics last."""
    e = ENTRIES[name]
    names = list(ENTRIES)
    return ([g.id for g in GROUPS + DIAGNOSTIC_GROUPS].index(e.group), names.index(name))


def scored() -> list[str]:
    """Relations that `run(relations="all")` executes and scores count: every implemented, non-diagnostic one."""
    return [e.name for e in IMPLEMENTED]


def diagnostics() -> list[str]:
    return [e.name for e in DIAGNOSTICS]


def check_registry(registry) -> None:
    """Every registered relation must be classified, and nothing planned may be registered."""
    implemented = {e.name for e in IMPLEMENTED + DIAGNOSTICS}
    missing = set(registry) - implemented
    stale = implemented - set(registry)
    planned_but_registered = set(registry) & {e.name for e in PLANNED}
    if missing or stale or planned_but_registered:
        raise RuntimeError(f"taxonomy out of sync: unclassified {sorted(missing)}, not registered "
                           f"{sorted(stale)}, planned yet registered {sorted(planned_but_registered)}")


# ----------------------------------------------------------------- rendering

def _members(group_id, implemented=True):
    pool = (IMPLEMENTED + DIAGNOSTICS) if implemented else PLANNED
    return [e for e in pool if e.group == group_id]


def mermaid() -> str:
    lines = ["```mermaid", "flowchart LR", '    root(["JevBench relations"])']
    for p in PILLARS:
        lines.append(f'    {p.id}["<b>{p.id} · {p.title}</b><br/><i>{p.oracle}</i>"]')
        lines.append(f"    root --> {p.id}")
        for g in GROUPS:
            if g.pillar != p.id:
                continue
            node = g.id.replace(".", "_")
            items = [f"● {e.name}" + (" (exploratory)" if e.exploratory else "") for e in _members(g.id)]
            items += [f"○ {e.name}" for e in _members(g.id, False)]
            label = f"<b>{g.id} · {g.title}</b><br/>" + "<br/>".join(items)
            lines.append(f'    {node}["{label}"]')
            lines.append(f"    {p.id} --> {node}")
            if not _members(g.id):
                lines.append(f"    class {node} planned")
    lines += ["    classDef planned stroke-dasharray: 5 4,color:#777", "```"]
    return "\n".join(lines)


def coverage_matrix() -> str:
    head = "| Group | " + " | ".join(EDITS) + " |"
    rule = "|---|" + "---|" * len(EDITS)
    rows = [head, rule]
    for g in GROUPS:
        cells = []
        for edit in EDITS:
            done = sum(edit in e.edits for e in _members(g.id))
            todo = sum(edit in e.edits for e in _members(g.id, False))
            cells.append(("●" * done + "○" * todo) or "·")
        rows.append(f"| {g.id} {g.title} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _variants(name: str) -> str:
    """How a relation's variants are drawn, read from the registered class."""
    from jevbench.relations import REGISTRY  # late import: relations import this module

    rel = REGISTRY[name]
    if rel.templates:
        return f"{len(rel.templates)} templates"
    if rel.needs_rewrites:
        return "1 rewrite (bank)"
    if name == "threshold_sweep":
        return "declared or counted"
    if name in ("remove_option_iia", "option_closure"):
        return "every option"
    if name == "pairwise_iia":
        return "every pair"
    if name == "batch_size_sweep":
        return "every size"
    from jevbench.engine import is_deterministic

    return "fixed" if is_deterministic(rel) else "random"


def _checks(e):
    return " + ".join(f"`{c}`" + ("\\*" if (e.name, c) in CHECK_NOTES else "") for c in e.primary) or "-"


def _row(g, e):
    name = f"● `{e.name}`" if e.implemented else f"○ {e.name}"
    if e.exploratory:
        name += " (exploratory)"
    variants = _variants(e.name) if e.implemented else "planned"
    summary = e.summary.replace("|", "\\|")
    return (f"| {g.id} {g.title} | {name} | {', '.join(e.edits) or '-'} | {e.law} | {summary} | "
            f"{_checks(e)} | {variants} |")


def tables() -> str:
    out = []
    head = ["| Group | Relation | Edits | Form | Law | Check | Variants |",
            "|---|---|---|---|---|---|---|"]
    for p in PILLARS:
        out.append(f"#### {p.id} · {p.title}: `{p.oracle}`\n")
        out.append(p.expects[0].upper() + p.expects[1:] + ".\n")
        out += head
        for g in GROUPS:
            if g.pillar == p.id:
                out += [_row(g, e) for e in _members(g.id) + _members(g.id, False)]
        out.append("")
    out.append("#### Diagnostics (not scored)\n")
    out.append("Checks on auxiliary response fields. They test the output format, not the distribution, so "
               "they belong to no dimension, never enter a score and run only when named "
               "(`--relations diagnostics`).\n")
    out += head
    for g in DIAGNOSTIC_GROUPS:
        out += [_row(g, e) for e in _members(g.id)]
    out.append("")
    out.append("**Form**: (E) distributional equality, (I) identity, (L) inequality. **Check**: the one quantity "
               "the relation measures. **Variants**: a law stated for every template, option, pair or size holds "
               "for a question only if it holds for every variant; its measure is the largest.")
    out.append("")
    out += [f"\\* `{rel}/{c}`: {note}." for (rel, c), note in CHECK_NOTES.items()]
    return "\n".join(out).rstrip()


START, END = "<!-- taxonomy:start -->", "<!-- taxonomy:end -->"


def markdown() -> str:
    n_impl, n_plan = len(IMPLEMENTED), len(PLANNED)
    n_expl = sum(e.exploratory for e in IMPLEMENTED)
    oracles = "\n".join(f"| {p.id} | {p.title} | {p.expects} | `{p.oracle.replace('|', chr(92) + '|')}` | "
                         f"{sum(len(_members(g.id)) for g in GROUPS if g.pillar == p.id)} |" for p in PILLARS)
    return "\n\n".join([
        START,
        f"{n_impl} relations in {len(PILLARS)} dimensions and {len(GROUPS)} groups, plus "
        f"{len(DIAGNOSTICS)} unscored diagnostics. Each relation is one transformation with one law; each "
        "dimension is defined by the operation that links the two distributions its laws compare.",
        "| Dimension | Title | Compares | Operation | Relations |\n|---|---|---|---|---|\n" + oracles,
        mermaid(),
        "**Coverage by edited component.** Each mark is one relation that edits that part of the "
        "request. Empty cells (·) are combinations not yet tested. The state is not a column: no "
        "relation edits it.",
        coverage_matrix(),
        "**Forms of law:** " + "; ".join(f"`{k}` {v}" for k, v in LAWS.items()) + ".",
        tables(),
        END,
    ])


def write_readme(path) -> bool:
    """Replace the taxonomy section of a README; return True if it changed."""
    from pathlib import Path

    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise ValueError(f"{path} has no taxonomy markers")
    new = text[: text.index(START)] + markdown() + text[text.index(END) + len(END):]
    if new != text:
        p.write_text(new, encoding="utf-8")
        return True
    return False
