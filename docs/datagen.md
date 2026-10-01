# How the cases were made

JevBench's cases are synthetic and generated *fact-first*: the facts of a case, how each is
mentioned and the answer to every question are fixed before any text is written. Every dataset is
therefore balanced by construction and carries gold answers, which JevBench uses only for the
accuracy it reports beside coherence (no relation refers to a correct answer).

`pip install "jevbench[datagen]"` adds what the pipeline needs; the writer and verifier models are
reached over an OpenAI-compatible chat endpoint (for example vLLM).

## Pipeline

```
1 domain spec      fact slots, scenario archetypes, question bank with answer rules, text styles
      |            (src/jevbench/datagen/domains/<domain>.py)
2 plan             sample facts and how each is mentioned; compute every gold answer;
      |            balance greedily over a large pool; rotate Choice options          (no model)
3 write            a writer model turns the facts into a state (style, length, mention levels);
      |            it never sees the questions                                          (gpt-oss-20b)
4 verify           a verifier model from another family reads only the state and reports each
      |            planned fact, or "not stated"; any mismatch rejects the draft      (Llama-3.1-8B)
5 freeze           length and near-duplicate checks; write cases.jsonl, gold.jsonl, facts.jsonl,
                   BALANCE.md (the balance achieved) and REVIEW.md (every case, for reading)
```

```bash
jevbench datagen plan   --domains customer_support,logistics --n 30 --out my-data/plans.jsonl
jevbench datagen write  --plans my-data/plans.jsonl --out my-data/drafts.jsonl \
                        --chat-url http://127.0.0.1:9000/v1/chat/completions --model openai/gpt-oss-20b
jevbench datagen verify --plans my-data/plans.jsonl --drafts my-data/drafts.jsonl --out my-data/verified.jsonl \
                        --chat-url http://127.0.0.1:9001/v1/chat/completions --model meta-llama/Llama-3.1-8B-Instruct
jevbench datagen freeze --plans my-data/plans.jsonl --drafts my-data/drafts.jsonl \
                        --verified my-data/verified.jsonl --per-domain 20 --out-dir my-data/frozen
jevbench plan my-suite/            # freeze a suite of your own: cases.jsonl + manifest.json
```

`bench/datagen_generate.sh` runs steps 3 and 4 on one GPU, serving the writer and the verifier in turn
with vLLM, and `bench/datagen_freeze.sh` merges several generation runs and freezes them.

## Design rules

- **Answers come from facts, not from the text.** Each question is a rule over the sampled facts and
  how they are mentioned, so gold answers and the logical links between questions are known before
  any text exists.
- **Mention levels.** A fact is *explicit* (stated), *implied* (clear from context, only for facts
  that allow it) or *absent* (not in the text at all). Questions of the form "does the text say X"
  are false when X is absent; questions of the form "is X true" have no answer when X is absent, and
  their gold is recorded as unknown. Facts that are speech acts ("the customer asks for a refund")
  are simply not said when false.
- **Balance.** Archetypes are even within a domain; each question's gold answers are spread evenly;
  Choice options are rotated so that the correct option falls evenly on every position; styles and
  three length bands (80-150, 150-250 and 250-350 words) are assigned in turn. Questions fixed by
  the scenario type (for example `feature_failing`) follow the archetype balance.
- **Model families.** Writer and verifier come from different families, and neither from a family
  under test. Every case records its source.
- **Kept apart.** A run reads only `cases.jsonl`. Gold answers and facts live in separate files, for
  accuracy and audit.
- **Synthetic, and labelled so.** Every case carries `source`; results on synthetic cases should be
  reported as such.

## JevBench-240

The bundled cases were generated this way: 375 plans over the twelve domains of
`src/jevbench/datagen/domains`, of which 240 were kept after verification and the length checks,
20 per domain. Their generation records are in [`data/`](../data):

| File | Content |
|---|---|
| `plans.jsonl` | every plan: domain, archetype, style, length band, facts and how each is mentioned |
| `facts.jsonl` | the facts of each kept case, with its word count |
| `gold.jsonl` | the gold answer of every question of each kept case (`"unknown"` when absent) |
| `BALANCE.md` | the balance achieved: archetypes, styles, lengths, mention levels, gold answers, option positions |
| `REVIEW.md` | every case with its facts and gold answers, for reading |

The natural rewrites four relations use (paraphrases, option descriptions, Chinese translations and
natural negations) were generated once by `jevbench rewrite` (`bench/rewrite_bank.sh`): a generator
proposed rewrites, a judge (the same model, two votes) kept those that preserve the meaning (or are
the exact opposite, for negations), and a second review by another model rejected more. The bank ships
with the suite (`src/jevbench/suites/jevbench-240/rewrites.jsonl`); rejected rewrites are kept in it,
marked, and never used.
