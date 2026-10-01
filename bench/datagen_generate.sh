#!/bin/bash
# Data generation on one GPU: write states with gpt-oss-20b, verify them with Llama-3.1-8B.
#
#   bench/datagen_generate.sh [plans.jsonl] [out_dir]
#
# Writer and verifier are served in turn by vLLM from the CLM model env (bench/models/clm.sh).
# Weights live in $HF_HOME; Llama is gated on the Hugging Face Hub, so accept its licence and log in first.
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
plans="${1:-data/plans.jsonl}"
out="${2:-runs/datagen}"
export JEVBENCH_ROOT="${JEVBENCH_ROOT:-$HOME/.cache/jevbench}"
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$JEVBENCH_ROOT/cache}"
VLLM_ENV="${VLLM_ENV:-$JEVBENCH_ROOT/envs/clm}"
WRITER="${WRITER:-openai/gpt-oss-20b}"
VERIFIER="${VERIFIER:-meta-llama/Llama-3.1-8B-Instruct}"
cd "$root" && mkdir -p "$out"
# jobs can share a node: every job gets its own pair of ports
WPORT=$(( 9300 + (${SLURM_JOB_ID:-0} % 400) * 2 )); VPORT=$(( WPORT + 1 ))

. "$root/bench/vllm.sh"
trap stop EXIT

{ echo "writer: $WRITER"; echo "verifier: $VERIFIER"; echo "plans: $plans ($(sha256sum "$plans" | cut -c1-16))"
  "$VLLM_ENV/bin/python" -c "import vllm; print('vllm', vllm.__version__)"; nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
} > "$out/manifest.txt"

PY="${JEVBENCH_PYTHON:-python3}"   # a Python with jevbench installed (pip install "jevbench[datagen]")
if [ "$(wc -l < "$out/drafts.jsonl" 2>/dev/null || echo 0)" -lt "$(wc -l < "$plans")" ]; then
    serve "$WRITER" $WPORT
    "$PY" -m jevbench datagen write --plans "$plans" --out "$out/drafts.jsonl" \
        --chat-url http://127.0.0.1:$WPORT/v1/chat/completions --model "$WRITER" \
        --temperature 0.8 --extra '{"reasoning_effort": "low"}' || exit 6
    stop
else
    echo "== all drafts present; skipping the writer"
fi
verify() {
    serve "$VERIFIER" $VPORT HF_HUB_OFFLINE=1
    "$PY" -m jevbench datagen verify --plans "$plans" --drafts "$out/drafts.jsonl" --out "$out/verified.jsonl" \
        --chat-url http://127.0.0.1:$VPORT/v1/chat/completions --model "$VERIFIER" || exit 7
    stop
}
verify
# rejected drafts are rewritten with a new seed, up to $REWRITES more times; the latest attempt counts
for _ in $(seq "${REWRITES:-2}"); do
    serve "$WRITER" $WPORT
    "$PY" -m jevbench datagen write --plans "$plans" --out "$out/drafts.jsonl" --redo "$out/verified.jsonl" \
        --chat-url http://127.0.0.1:$WPORT/v1/chat/completions --model "$WRITER" \
        --temperature 0.8 --extra '{"reasoning_effort": "low"}' || exit 6
    stop
    verify
done
trap - EXIT
python3 - "$out" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1] + "/verified.jsonl")]
first = [r for r in rows if r.get("attempt", 1) == 1]
last = {r["id"]: r for r in rows}.values()
print(f"== done: first attempt {sum(r['passed'] for r in first)}/{len(first)} passed, "
      f"after rewrites {sum(r['passed'] for r in last)}/{len(last)}")
PY
