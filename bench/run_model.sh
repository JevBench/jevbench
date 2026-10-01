#!/bin/bash
# Serve one Jev-compatible model on this machine, evaluate it with JevBench, stop it.
#
#   bench/run_model.sh <name> [extra bench/evaluate.py args...]
#
#   SUITE="..."   bundled suites to run, in order (default jevbench-mini); "jevbench-mini jevbench-240"
#                 runs both, and the second takes the requests the first already sent from the cache
#   REPLICAS=N    start N servers of the model, spread over the machine's GPUs in turn, on ports PORT,
#                 PORT+1, ... (each sees only its GPU); JevBench keeps one request in flight per replica
#
# bench/models/<name>.sh defines NAME, SERVED (the "model" field to send), PORT,
# PYTHON (uv Python version), and the functions setup() and serve(). setup()
# installs the model into $ENV (one venv per model, reused across runs); serve()
# starts its server in the foreground. Weights go to $HF_HOME. The evaluation
# runs in the Python of $JEVBENCH_PYTHON (default python3), which must have
# jevbench installed. Reports go to runs/<suite>/<name>.json.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
name="${1:?model name}"; shift
spec="$here/models/$name.sh"
[ -f "$spec" ] || { echo "no $spec"; exit 2; }

# Model environments, caches and weights are large: point JEVBENCH_ROOT and HF_HOME at a large disk.
export JEVBENCH_ROOT="${JEVBENCH_ROOT:-$HOME/.cache/jevbench}"
export JEVBENCH_ENVS="${JEVBENCH_ENVS:-$JEVBENCH_ROOT/envs}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$JEVBENCH_ROOT/cache/uv}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$JEVBENCH_ROOT/cache/pip}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$JEVBENCH_ROOT/cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$JEVBENCH_ROOT/cache/python}"
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export ENV="$JEVBENCH_ENVS/$name"
export PATH="$HOME/.local/bin:$PATH"
PYTHON=3.11
READY_TIMEOUT="${READY_TIMEOUT:-1800}"
# shellcheck source=/dev/null
. "$spec"
mkdir -p "$JEVBENCH_ENVS" "$root/runs"
log="$root/runs/serve-$name.log"

echo "== $name: setup ($ENV)"
if [ ! -f "$ENV/.jevbench-ready" ]; then
    # not `( set -e; setup ) || ...`: bash ignores set -e inside a command tested by ||,
    # which would mark a failed install as ready
    ( set -e; setup )
    rc=$?
    [ $rc -eq 0 ] || { echo "setup failed (exit $rc)"; exit 3; }
    touch "$ENV/.jevbench-ready"
fi

# the server's own packages decide its answers; keep them next to the result
( . "$ENV/bin/activate" && uv pip freeze ) > "$root/runs/env-$name.txt" 2>/dev/null
echo "== $name: $(grep -c . "$root/runs/env-$name.txt") packages recorded in runs/env-$name.txt"

echo "== $name: serve on :$PORT (log $log)"
REPLICAS="${REPLICAS:-1}"
ngpu=$(nvidia-smi -L 2>/dev/null | grep -c "^GPU" || true); [ "${ngpu:-0}" -gt 0 ] || ngpu=1
gpus=(${CUDA_VISIBLE_DEVICES//,/ }); [ ${#gpus[@]} -gt 0 ] || gpus=($(seq 0 $(( ngpu - 1 ))))
base_port=$PORT servers=() urls=()
for i in $(seq 0 $(( REPLICAS - 1 ))); do
    rlog="$log"; [ "$REPLICAS" -gt 1 ] && rlog="${log%.log}-r$i.log"
    ( export REPLICA=$i PORT=$(( base_port + i )) CUDA_VISIBLE_DEVICES=${gpus[$(( i % ${#gpus[@]} ))]}; serve ) > "$rlog" 2>&1 &
    servers+=($!); urls+=("http://127.0.0.1:$(( base_port + i ))/v1/systemone")
done
trap 'for s in "${servers[@]}"; do kill $s 2>/dev/null; done; sleep 2; for s in "${servers[@]}"; do kill -9 $s 2>/dev/null; pkill -P $s 2>/dev/null; done' EXIT
echo "== $name: $REPLICAS replica(s) on GPU(s) ${gpus[*]}"

probe='{"model":"'"$SERVED"'","state":"I was charged twice this month.","questions":{"q":{"type":"noul","instructions":"Is this a billing issue?"}}}'
start=$(date +%s)
for i in "${!urls[@]}"; do
    until curl -sf -m 60 "${urls[$i]}" -H 'Content-Type: application/json' -d "$probe" > "$root/runs/probe-$name.json"; do
        if ! kill -0 "${servers[$i]}" 2>/dev/null; then echo "server $i exited"; tail -40 "$log"*; exit 4; fi
        if [ $(( $(date +%s) - start )) -gt "$READY_TIMEOUT" ]; then echo "not ready after ${READY_TIMEOUT}s"; exit 5; fi
        sleep 10
    done
done
url=$(IFS=,; echo "${urls[*]}")
echo "== $name: ready after $(( $(date +%s) - start ))s; probe: $(cat "$root/runs/probe-$name.json")"

cd "$root" && PY="${JEVBENCH_PYTHON:-python3}"
"$PY" -c "import jevbench" 2>/dev/null || { echo "no jevbench in $PY: pip install jevbench"; exit 6; }
rc=0
for suite in ${SUITE:-jevbench-mini}; do
    mkdir -p "$root/runs/$suite"
    "$PY" "$root/bench/evaluate.py" --url "$url" --model "$SERVED" --suite "$suite" --name "$name" \
        --cache-dir "${CACHE_DIR:-$root/.jevbench-cache}" --out "$root/runs/$suite/$name.json" "$@"
    r=$?
    echo "== $name: $suite exit $r"
    [ "$r" -eq 0 ] || rc=$r
done
exit $rc
