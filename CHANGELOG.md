# Changelog

## 0.1.0

First release.

- 50 metamorphic relations in five dimensions (REP, BAT, MEA, LOG, CHO), each one law of probability or
  choice, with violation measures in probability units and one fixed tolerance.
- Bundled suites: `jevbench-mini` (the reported suite, 1,200 tests), `jevbench-240` (240 synthetic cases
  in 12 domains, 12,000 tests) and `examples` (one case, to check that a model works).
- Frozen test plans: every request fixed in advance, no random numbers in a run.
- Models: any server implementing the Jev interface (`jb.systemone`) or a Python function
  (`jb.from_callable`), with replicas and a request cache; `jb.check` and `jevbench check` to test a
  model's connection before a run.
- Fact-first data generation (`jevbench datagen`) and natural-rewrite banks (`jevbench rewrite`).
