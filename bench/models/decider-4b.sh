# decider-4b v2.1 (Mapika): https://github.com/Mapika/decider  weights: Mapika/decider-4b (Apache-2.0)  Qwen3.5-4B-Base full fine-tune + LoRA stage (v2.1), option-letter logit readout, per-type temperatures  4.2B params
# Sources checked: README.md, MODEL_CARD_4B.md, docs/SERVING.md, scripts/serve.sh, decider/serve.py, pyproject.toml
# (decider-ai 1.6.0 on PyPI = repo main), HF Mapika/decider-4b (main = v2.1; tags v2, v1).
# Wire format: native POST /v1/systemone ("TypeSafe's wire format"). choice -> probabilities keyed by option key;
# score -> probabilities keyed "0".."n-1" (plus level_fit, fit_mass); noul -> {"noul": p}. The request "model"
# field is not checked (serve.py never reads it) and the response names "decider-<version>" from decider_config.json.
# Requirements per the model card: torch, transformers>=5, flash-linear-attention (Triton kernels for the Qwen3.5
# linear-attention layers; "runs without it but several times slower"). decider-ai declares all three.
# Not used here: decider.serve_vllm (vLLM 0.29.0 in its own env) is documented for large *stock* chat-layout models,
# not for these checkpoints; the torch server is the documented path for decider-4b.
NAME=decider-4b
SERVED=decider-4b
PORT=8102
PYTHON=3.12
DECIDER_REPO=Mapika/decider-4b
DECIDER_REV=main          # v2.1 (HF commit eb5fbdfc9448473ec25e399882912863afbdb70e on 2026-09-29); tags v2, v1 also exist
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # [serve] = fastapi, uvicorn[standard], httpx. decider-ai pins numpy<2 and leaves torch unpinned
    # (PyPI torch>=2.11 wheels are CUDA 13.0 builds; driver >= 580).
    uv pip install "decider-ai[serve]==1.6.0" || return 1
    DECIDER_REPO="$DECIDER_REPO" DECIDER_REV="$DECIDER_REV" python - <<'PY' || return 1
import os
from huggingface_hub import snapshot_download
snapshot_download(os.environ["DECIDER_REPO"], revision=os.environ["DECIDER_REV"])
PY
}
serve() {
    . "$ENV/bin/activate"
    # docs/SERVING.md: start from a directory without another decider/ package (uvicorn's --app-dir . wins).
    cd "$ENV" || return 1
    local model_dir
    model_dir="$(DECIDER_REPO="$DECIDER_REPO" DECIDER_REV="$DECIDER_REV" python -c 'import os; from huggingface_hub import snapshot_download as s; print(s(os.environ["DECIDER_REPO"], revision=os.environ["DECIDER_REV"]))')"
    # scripts/serve.sh is: DECIDER_MODEL=<id|dir> uvicorn decider.serve:app --host 0.0.0.0 --port <port>.
    # CUDA graphs for every (batch, length) bucket are captured at start-up, so readiness takes a while.
    DECIDER_MODEL="$model_dir" DECIDER_DEVICE=cuda PYTHONSAFEPATH=1 \
        exec uvicorn decider.serve:app --host 127.0.0.1 --port "$PORT"
}
