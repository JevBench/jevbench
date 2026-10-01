#!/bin/bash
# Generate and judge a suite's natural-rewrite bank on one GPU with a vLLM-served chat model.
#
#   bench/rewrite_bank.sh [suite] [out.jsonl]
#
# The generator also judges (both directions for paraphrases, negations and descriptions). gpt-oss
# reasons before it answers, so its verdicts get a larger token budget than the 5 tokens a plain
# model needs. Resumable: sources already in the bank are skipped.
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
suite="${1:-jevbench-240}"
bank="${2:-runs/rewrites/$suite.jsonl}"
out="$(dirname "$bank")"
export JEVBENCH_ROOT="${JEVBENCH_ROOT:-$HOME/.cache/jevbench}"
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$JEVBENCH_ROOT/cache}"
VLLM_ENV="${VLLM_ENV:-$JEVBENCH_ROOT/envs/clm}"
MODEL="${MODEL:-openai/gpt-oss-20b}"
KINDS="${KINDS:-paraphrase,negation,description,translate:zh}"
PORT=$(( 9300 + (${SLURM_JOB_ID:-0} % 400) * 2 ))
cd "$root" && mkdir -p "$out"
. "$root/bench/vllm.sh"
trap stop EXIT

{ echo "model: $MODEL"; echo "suite: $suite"; echo "kinds: $KINDS"
  "$VLLM_ENV/bin/python" -c "import vllm; print('vllm', vllm.__version__)"
} > "$out/manifest-$suite.txt"

serve "$MODEL" $PORT
PY="${JEVBENCH_PYTHON:-python3}"   # a Python with jevbench installed (pip install "jevbench[datagen]")
"$PY" -m jevbench rewrite --suite "$suite" --kinds "$KINDS" --out "$bank" \
    --chat-url "http://127.0.0.1:$PORT/v1/chat/completions" --model "$MODEL" \
    --extra '{"reasoning_effort": "low"}' --max-tokens 3000 --judge-tokens 1500 --concurrency 32 || exit 6
stop
trap - EXIT
