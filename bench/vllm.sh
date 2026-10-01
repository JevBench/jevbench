# Serve a model with vLLM on this node and stop it again. Source this file; it needs
#   $VLLM_ENV  a venv with vllm (bench/models/clm.sh builds one)
#   $out       where the vLLM logs go
serve() {  # serve MODEL PORT [extra env...]; sets $vpid
    local model=$1 port=$2; shift 2
    # FlashInfer's sampler JIT-compiles with nvcc, which compute nodes do not have: use PyTorch sampling
    # own process group (setsid), so stop() can end vLLM's engine processes too, not only the launcher
    setsid bash -c '. "$0/bin/activate"; exec env VLLM_USE_FLASHINFER_SAMPLER=0 "$@"' "$VLLM_ENV" \
        "$@" vllm serve "$model" --port "$port" --host 127.0.0.1 --max-model-len 8192 --gpu-memory-utilization 0.85 \
        > "$out/vllm-$(basename "$model").log" 2>&1 &
    vpid=$!
    local t0; t0=$(date +%s)
    until curl -sf -m 5 "http://127.0.0.1:$port/health" >/dev/null; do
        kill -0 $vpid 2>/dev/null || { echo "vLLM for $model exited"; tail -30 "$out/vllm-$(basename "$model").log"; exit 4; }
        [ $(( $(date +%s) - t0 )) -gt 2400 ] && { echo "vLLM for $model not ready"; kill $vpid; exit 5; }
        sleep 10
    done
    echo "== $model ready after $(( $(date +%s) - t0 ))s"
}
stop() {  # end the whole process group, then wait until the GPU memory is actually free
    [ -n "${vpid:-}" ] || return 0
    kill -TERM -- "-$vpid" 2>/dev/null; sleep 10; kill -KILL -- "-$vpid" 2>/dev/null
    local t0; t0=$(date +%s)
    while [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)" -gt 2000 ]; do
        [ $(( $(date +%s) - t0 )) -gt 300 ] && { echo "GPU memory not released"; nvidia-smi; break; }
        sleep 5
    done
    vpid=""
}
