<p align="center">
  <img src="https://jevbench.github.io/assets/logo.svg" width="88" alt="JevBench">
</p>

<h1 align="center">JevBench</h1>

<p align="center">
  <b>Metamorphic coherence testing for typed probabilistic decision models</b><br>
  Do a model's probabilities fit together? 50 laws of probability and choice, no gold labels.
</p>

<p align="center">
  <a href="https://pypi.org/project/jevbench/"><img src="https://img.shields.io/pypi/v/jevbench?color=16213A&label=PyPI" alt="PyPI"></a>
  <a href="https://pypi.org/project/jevbench/"><img src="https://img.shields.io/pypi/pyversions/jevbench?color=16213A" alt="Python"></a>
  <a href="https://github.com/JevBench/jevbench/actions/workflows/tests.yml"><img src="https://github.com/JevBench/jevbench/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/JevBench/jevbench/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-16213A" alt="License"></a>
  <a href="https://jevbench.github.io"><img src="https://img.shields.io/badge/leaderboard-jevbench.github.io-E8603F" alt="Leaderboard"></a>
  <a href="https://jevbench.github.io/report/JevBench-technical-report.pdf"><img src="https://img.shields.io/badge/technical%20report-PDF-E8603F" alt="Technical report"></a>
</p>

---

Typed probabilistic decision models answer questions about a fixed input with probability distributions over
declared answers: yes or no (a **Noul**), one of several options (a **Choice**), or a level on an ordered scale
(a **Score**). Beyond the robustness expected of any language model, these classification-like outputs raise a
further question: **do their probabilities stay coherent?**

- A question and its negation should sum to one.
- Merging two options should merge their probabilities.
- A conjunction should never be more probable than either conjunct.
- Removing an irrelevant option should leave the others' relative probabilities unchanged.
- An answer should not depend on which other questions are asked with it.

JevBench turns such laws into **50 metamorphic relations**. Every test edits only the question side, never the
input, so no correct answer is needed; and every request is frozen in advance, so every model answers exactly
the same tests.

| 50 relations | 240 cases | 12,000 frozen tests | 21 open models |
|:---:|:---:|:---:|:---:|
| in 5 dimensions | in 12 decision domains | 1,200 in the reported suite | 48M to 9.7B parameters |

## Five dimensions

| | Dimension | What changes | Example law | Relations |
|---|---|---|---|---|
| **REP** | Representation consistency | the description of the same events | options reordered: the probabilities follow the options | 15 |
| **BAT** | Batch independence | the other questions of the request | batch reversed: every answer stays the same | 5 |
| **MEA** | Probability measure coherence | the events of one probability measure | a question and its negation sum to one | 17 |
| **LOG** | Logical coherence | propositions ordered by entailment | P(A and B) ≤ min{P(A), P(B)} | 10 |
| **CHO** | Choice-set coherence | the menu a Choice is conditioned on | an option removed: the rest keep their proportions | 3 |

Each dimension is the mean of its relations' pass rates, and the overall score is the mean of the five
dimensions. A test passes when its law holds within 0.05 in probability.

## Leaderboard

<p align="center">
  <img src="https://raw.githubusercontent.com/JevBench/jevbench/main/docs/assets/dimensions.png" width="640"
       alt="Dimension scores of the 21 models on JevBench-mini">
</p>
<p align="center"><sub>Dimension scores of the 21 models on JevBench-mini. Probability-measure coherence (MEA)
is the weakest dimension of every model.</sub></p>

Top 10 of 21 openly released models on JevBench-mini (snapshot of release 0.1.0):

| # | Model | Readout | Size | Coherence | Accuracy |
|---:|---|---|---:|---:|---:|
| 1 | [Open-Jev-9B](https://github.com/Zefan-Cai/Open-Jev) | decoder · scorer head | 9.7B | **83.9** | 88.4% |
| 2 | [JevAny-Gemma-4B (pointer)](https://github.com/SimpleJev/JevAny) | decoder · pointer head | E4B | **81.2** | 87.6% |
| 3 | [JevAny-Qwen-4B (pointer)](https://github.com/SimpleJev/JevAny) | decoder · pointer head | 4B | **79.4** | 88.8% |
| 4 | [decider-4b v2.1](https://github.com/Mapika/decider) | decoder · letter logits | 4.2B | **78.4** | 88.6% |
| 5 | [JevAny-Qwen-4B (direct token)](https://github.com/SimpleJev/JevAny) | decoder · letter logits | 4B | **77.8** | 88.6% |
| 6 | [TinyJev-4B](https://github.com/ankit-aglawe/tinyjev) | decoder · pointer head | 4.0B | **77.3** | 86.6% |
| 7 | [Jebadiah 9B v2](https://github.com/getainode/jebadiah) | decoder · letter logits | 9.65B | **76.9** | 89.1% |
| 8 | [Von 1.3](https://github.com/wfzyx/von) | encoder · option markers | 395M | **75.9** | 72.2% |
| 9 | [JevK5 v0.3](https://github.com/allebee/jevk5) | decoder · letter logits | 4.2B | **72.8** | 88.1% |
| 10 | [OneJev-4B](https://github.com/OmniJev/OneJev) | decoder · letter logits | 5.2B | **72.5** | 89.2% |
| – | *Uniform reference (ignores its input)* | reference | – | *89.4* | *39.8%* |

> **Reading the scores.** Coherence is not correctness: a model that ignores its input and answers uniformly
> scores 89.4 at chance accuracy, so read every score beside accuracy. Models a few points apart are ties
> (their 95% intervals overlap). The full leaderboard, the scores by dimension and group, and every model's
> complete report are on **[jevbench.github.io](https://jevbench.github.io)**.

**Key findings.** Additivity is the weak spot: a templated negation sums to one with its question in only 7% of
tests on average. Batch independence mostly holds (19 of 21 models keep every batch law). Among decoders,
accuracy sits in a narrow 82–89% band while coherence ranges from 64 to 84.

## Quick start

```bash
pip install jevbench                                     # Python 3.10+, depends only on httpx
jevbench eval --backend fake:coherent --suite examples   # a few seconds: check the installation
```

```python
import jevbench as jb

model = jb.systemone("http://127.0.0.1:8000/v1/systemone", model="my-model")
jb.check(model)                    # one request: is every answer in the standard format?
report = jb.evaluate(model)        # JevBench-mini, the reported suite (1,248 requests)
print(report.table("dimension"))   # also "group" and "relation"
report.save("runs/my-model.json")
```

The same from the shell:

```bash
jevbench check --url http://127.0.0.1:8000/v1/systemone --model my-model
jevbench eval  --url http://127.0.0.1:8000/v1/systemone --model my-model --out runs/my-model.json
```

- **Suites.** `jevbench-mini` (default, the one results are reported on), `jevbench-240` (every test, narrower
  intervals) and `examples` (one case, to check that a model works).
- **Speed.** Requests are cached. Pass several comma-separated URLs to use replicas of one model; JevBench keeps
  one request in flight per replica, which reproduces the sequential answers.
- **In-process models.** `jb.from_callable(fn, name="my-model-v1")` tests any Python function
  `fn(state, questions) -> answers`.
- **Your own data.** `jb.evaluate(model, cases="my-cases.jsonl")`; generate cases for a new domain with
  `jevbench datagen` ([docs/datagen.md](https://github.com/JevBench/jevbench/blob/main/docs/datagen.md)).

## Connecting your model

JevBench reads the standard Jev format and nothing else: a model that returns another format is asked to adapt,
with a message that says how. Check a model before a full run with `jevbench check` or `jb.check(model)`.

**What the model receives.** A `state` (the input to decide about: text or JSON, never changed by JevBench) and a
batch of typed `questions`, keyed by question id:

```json
{
  "model": "my-model",
  "state": "Customer writes: Our nightly export has failed three nights in a row...",
  "questions": {
    "export_failing": {"type": "noul", "instructions": "Is a scheduled data export currently failing?"},
    "primary_team":   {"type": "choice", "instructions": "Which team should own the primary issue?",
                       "criteria": {"engineering": "Fixes broken product functionality",
                                    "billing": "Handles invoices, charges and refunds"}},
    "frustration":    {"type": "score", "instructions": "How frustrated does the customer sound?",
                       "criteria": ["Calm", "Mildly annoyed", "Clearly frustrated", "Angry"]}
  }
}
```

A Noul is a yes/no question and has no criteria. A Choice names its options, each with a description. A Score
lists ordered levels, lowest first. Question ids, option ids and the number of questions per request vary from
test to test: a model must answer whatever it is asked.

**What the model returns.** One answer per question, under the same id:

```json
{
  "answers": {
    "export_failing": {"type": "noul", "noul": 0.93},
    "primary_team":   {"type": "choice", "probabilities": {"engineering": 0.88, "billing": 0.12}},
    "frustration":    {"type": "score", "probabilities": {"0": 0.05, "1": 0.25, "2": 0.6, "3": 0.1}}
  }
}
```

| Type | Answer | Rules |
|---|---|---|
| Noul | `{"type": "noul", "noul": p}` | `p` is the probability of yes, a number in [0, 1] |
| Choice | `{"type": "choice", "probabilities": {...}}` | a probability for **every** option id of the question |
| Score | `{"type": "score", "probabilities": {...}}` | a probability for every level, keyed `"0"` ... `"n-1"` (or by level text) |

Probabilities are finite and non-negative; those of a Choice or Score should sum to 1 (JevBench renormalises
them). Other fields of an answer are ignored.

**As a server.** Answer `POST /v1/systemone` with the request above and return `{"answers": {...}}` as JSON. An
HTTP 4xx response counts as a refused request; 429 and 5xx responses are retried. A bearer token, if the server
needs one, is read from `JEVBENCH_API_KEY`.

**As a Python function.** Return the `answers` object itself:

```python
def my_model(state, questions):
    answers = {}
    for key, q in questions.items():
        if q["type"] == "noul":
            answers[key] = {"type": "noul", "noul": prob_yes(state, q)}
        elif q["type"] == "choice":
            answers[key] = {"type": "choice", "probabilities": {o: prob_option(state, q, o) for o in q["criteria"]}}
        else:   # score: q["criteria"] lists the levels, lowest first
            answers[key] = {"type": "score",
                            "probabilities": {str(i): prob_level(state, q, i) for i in range(len(q["criteria"]))}}
    return answers

model = jb.from_callable(my_model, name="my-model-v1")
```

**When something is wrong.** `jb.evaluate` sends the first request before the run and stops with
`AnswerFormatError` (an answer is not in the format above; the message names the question and shows what came
back) or `ModelError` (the model did not answer at all). Failures later in a run are recorded, and the relations
they affect are left unscored rather than scored on fewer tests.

## Documentation

| | |
|---|---|
| [Technical report](https://jevbench.github.io/report/JevBench-technical-report.pdf) | the method, the 50 relations, the data and all results |
| [Leaderboard](https://jevbench.github.io) | every model's scores, profiles and full report |
| [docs/reproducing.md](https://github.com/JevBench/jevbench/blob/main/docs/reproducing.md) | recompute every score from the published reports, or rerun any model |
| [docs/datagen.md](https://github.com/JevBench/jevbench/blob/main/docs/datagen.md) | how the cases and the rewrite bank were generated |
| [archived/taxonomy.md](https://github.com/JevBench/jevbench/blob/main/archived/taxonomy.md) | the full relation taxonomy, generated from the code |
| [archived/README-detailed.md](https://github.com/JevBench/jevbench/blob/main/archived/README-detailed.md) | the detailed reference: case format, how a run works, scoring, templates and rewrites |

## Citation

```bibtex
@misc{feng2026jevbench,
  title        = {JevBench: Metamorphic Coherence Testing for Typed Probabilistic Decision Models},
  author       = {Feng, Chen},
  year         = {2026},
  howpublished = {\url{https://jevbench.github.io}},
  note         = {Technical report. ML Lab, Queen's University Belfast}
}
```

## Authors

JevBench is developed by [Chen Feng](https://mrchenfeng.github.io/) at the
[ML Lab, Queen's University Belfast](https://qub-ml.github.io/)
([c.feng@qub.ac.uk](mailto:c.feng@qub.ac.uk)). Issues and contributions:
https://github.com/JevBench/jevbench.

## License

Apache-2.0. See the LICENSE and NOTICE files shipped with the package. JevBench is not affiliated with or endorsed
by TypeSafe AI; "Jev" names the wire interface (`POST /v1/systemone`) that JevBench speaks.
