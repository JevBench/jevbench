#!/bin/bash
# Merge several generation runs and freeze them into one dataset.
#
#   bench/datagen_freeze.sh OUT PER_DOMAIN PLANS:RUN_DIR [PLANS:RUN_DIR ...]
#
# Plan ids are unique across the inputs (domain-index), so plans, drafts and verifications are simply
# concatenated; the latest attempt of each plan counts. Writes OUT/{plans,drafts,verified}.jsonl and the
# frozen dataset in OUT/frozen.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out=$1 per=$2; shift 2
cd "$root" && mkdir -p "$out"
: > "$out/plans.jsonl"; : > "$out/drafts.jsonl"; : > "$out/verified.jsonl"
for pair in "$@"; do
    plans=${pair%%:*} run=${pair#*:}
    cat "$plans" >> "$out/plans.jsonl"
    cat "$run/drafts.jsonl" >> "$out/drafts.jsonl"
    cat "$run/verified.jsonl" >> "$out/verified.jsonl"
done
PY="${JEVBENCH_PYTHON:-python3}"   # a Python with jevbench installed (pip install "jevbench[datagen]")
"$PY" -m jevbench datagen freeze --plans "$out/plans.jsonl" --drafts "$out/drafts.jsonl" --verified "$out/verified.jsonl" \
    --out-dir "$out/frozen" --per-domain "$per" \
    --tokenizer convaiinnovations/laya --tokenizer-subfolder tokenizer --max-state-tokens 480
