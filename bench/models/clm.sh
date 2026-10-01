# CLM v0.1 (Contrastive-LM): https://github.com/Contrastive-LM/CLM  weights: Contrastive-LM/CLM-v0.1-8B (Apache-2.0; encoder Qwen/Qwen3-8B Apache-2.0)  contrastive state/action projection heads (~20M params) over frozen Qwen3-8B last-token embeddings  8.2B encoder + 20M heads
# Sources checked: README.md ("Serve", architecture diagram), serve_qwen3_8b.sh, pyproject.toml (contrastive-lm 0.1.0),
# src/clm/server.py, src/clm/engine.py, src/clm/schema.py, src/clm/heads.py (repo main bb42c6c5), HF CLM-v0.1-8B.
# Two processes: vLLM pooling server for Qwen3-8B (GPU, OpenAI /v1/embeddings) + clm-serve (FastAPI, heads on cuda
# when available, CLM_DEVICE/--device override). clm-serve is pointed at vLLM with
#   --emb-url http://127.0.0.1:$VLLM_PORT/v1/embeddings --emb-model qwen3-8b   (env: CLM_EMB_URL / CLM_EMB_MODEL)
# and --emb-model must equal vLLM's --served-model-name.
# Wire format: native POST /v1/systemone. noul -> {"noul": P(true)}; choice -> probabilities by option key; score ->
# probabilities keyed "0".."n-1" + legend. "model" IS checked: "clm-latest" (default when omitted), "clm-raw", or a
# name added with --model/--ckpt-dir; anything else -> HTTP 422 "unknown model". Optional "temperature" field.
# States longer than --max-tokens (2048) are truncated.
NAME=clm
SERVED=clm-latest
PORT=8108
PYTHON=3.12
VLLM_PORT=9108
CLM_COMMIT=bb42c6c5bf914fd449bed2f6ca65be80602cb1f7   # repo main on 2026-09-29 (PyPI contrastive-lm 0.1.0)
CLM_HEAD_DIR="$HF_HOME/local/clm-v0.1-8b"
# serve_qwen3_8b.sh defaults to UTIL=0.35 ("lean settings so it coexists with other GPU work"), which on a 40 GB
# card is 14 GB: less than Qwen3-8B's ~16.4 GB of bf16 weights. 0.60 = 24 GB leaves room for weights + a 2k-token
# KV cache for 32 seqs, and ~16 GB for clm-serve's heads/action cache (2% of the device by default) and CUDA contexts.
# UNVERIFIED: 0.60 is our sizing, not a documented value (https://github.com/Contrastive-LM/CLM/blob/main/serve_qwen3_8b.sh).
VLLM_UTIL=0.60
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # README: pip install contrastive-lm (pulls torch, fastapi, uvicorn and vllm>=0.6). vllm is unpinned; current
    # vLLM 0.28-0.30 pin torch==2.13.0 (CUDA 13.0 wheels, driver >= 580). Installing from the pinned commit.
    # UNVERIFIED: vLLM version is not pinned by CLM; `--runner pooling` needs a recent vLLM (it is the documented flag).
    uv pip install "contrastive-lm[hf] @ git+https://github.com/Contrastive-LM/CLM@${CLM_COMMIT}" || return 1
    CLM_HEAD_DIR="$CLM_HEAD_DIR" python - <<'PY' || return 1
import os
from huggingface_hub import hf_hub_download, snapshot_download
snapshot_download("Qwen/Qwen3-8B")                                   # encoder served by vLLM
hf_hub_download("Contrastive-LM/CLM-v0.1-8B", "CLM_v0.1-8B.pt", local_dir=os.environ["CLM_HEAD_DIR"])
PY
}
serve() {
    . "$ENV/bin/activate"
    local me=$BASHPID vpid t0
    VLLM_PORT=$(( VLLM_PORT + 10 * ${REPLICA:-0} ))  # replicas of this model run side by side
    # 1. encoder, flags from serve_qwen3_8b.sh ("LAST-token pooling + prefix cache, same as the precompute").
    # UNVERIFIED: that vLLM's default pooler for Qwen3ForCausalLM under --runner pooling is LAST-token (the script
    # relies on the default and says so; no explicit pooler flag is documented).
    vllm serve Qwen/Qwen3-8B --served-model-name qwen3-8b --runner pooling --enforce-eager \
        --enable-prefix-caching --max-model-len 2048 --gpu-memory-utilization "$VLLM_UTIL" --max-num-seqs 32 \
        --host 127.0.0.1 --port "$VLLM_PORT" &
    vpid=$!
    # run_model.sh's EXIT trap kills this process first and only then its children, so vLLM would be orphaned;
    # this watchdog stops vLLM when the serve process (clm-serve after exec, same PID) goes away.
    ( while kill -0 "$me" 2>/dev/null; do sleep 5; done; kill "$vpid" 2>/dev/null; sleep 15; kill -9 "$vpid" 2>/dev/null ) &
    t0=$(date +%s)
    until curl -sf -m 5 "http://127.0.0.1:$VLLM_PORT/health" >/dev/null; do
        kill -0 "$vpid" 2>/dev/null || { echo "vLLM exited"; return 1; }
        [ $(( $(date +%s) - t0 )) -gt 1500 ] && { echo "vLLM not healthy after 1500s"; kill "$vpid"; return 1; }
        sleep 5
    done
    # 2. CLM API. Documented: `clm-serve` (defaults :8700, emb-url http://127.0.0.1:8090/v1/embeddings, qwen3-8b).
    exec clm-serve --host 127.0.0.1 --port "$PORT" \
        --emb-url "http://127.0.0.1:$VLLM_PORT/v1/embeddings" --emb-model qwen3-8b --max-tokens 2048 \
        --ckpt "$CLM_HEAD_DIR/CLM_v0.1-8B.pt" --device cuda --no-ui
}
