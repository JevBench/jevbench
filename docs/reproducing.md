# Reproducing the evaluation

The results on the [JevBench website](https://jevbench.github.io) come from the bundled suites, the
21 models listed there, and the scripts in [`bench/`](../bench). Every report is published with all
its answers, so the scores can be recomputed without running any model.

## Recompute the scores from the published reports

```bash
pip install jevbench
git clone https://github.com/JevBench/JevBench.github.io
python -c "import jevbench as jb; print(jb.Report.load('JevBench.github.io/data/results/jevbench-mini/open-jev-9b.json.gz').table('group'))"
python bench/analysis/site_data.py --results JevBench.github.io/data/results --out site-data
```

`site_data.py` writes the leaderboard (scores, intervals, rank ranges, accuracy), the agreement of
jevbench-mini with jevbench-240, and the model table that the website shows.

## Run a model again

Each model has a spec in [`bench/models/<name>.sh`](../bench/models): the release it was installed from
(a pinned commit or revision), how its environment is built, how its server is started, and notes on
anything its documentation left open. [`bench/run_model.sh`](../bench/run_model.sh) installs the model
(once), starts its server, waits until it answers, evaluates it and stops it:

```bash
pip install jevbench                     # the Python that runs the evaluation (JEVBENCH_PYTHON)
bench/run_model.sh open-jev-9b           # jevbench-mini -> runs/jevbench-mini/open-jev-9b.json
SUITE="jevbench-mini jevbench-240" REPLICAS=4 bench/run_model.sh open-jev-9b
```

It needs `uv`, `curl` and, for most models, an NVIDIA GPU (we used one A100 40GB per replica; the two
jevhome models run on CPU). Model environments and weights are large: set `JEVBENCH_ROOT` and `HF_HOME`
to a disk with room. A gated model (Llama, for the data verifier) needs a Hugging Face login.

No self-hosted model we ran varied across three repeated requests, so a rerun of the same release should
return the same answers. `bench/serving.json` lists the two models not served by their developers' own server, and
`bench/timings.json` the time each took.

## The reference models

```bash
python bench/baselines.py --out runs/reference      # uniform, random and the two toy scorers
```

They need no GPU and take a few minutes.

## The data

How the cases and the rewrite bank were generated, and the generation records, are described in
[datagen.md](datagen.md).
