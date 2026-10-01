# RSI-Jev v3.0 2B (Shanghua Gao): https://github.com/Shanghua-Gao/RSI-Jev  weights: shgao/rsi-jev-v3.0-qwen3.5-2b (code MIT, weights Apache-2.0)  Qwen3.5-2B-Base tower + trained readout/scorer head, SFT then RL, fitted calibration  ~2.3B params
# Sources checked: README.md, serve/README.md, scripts/serve.py, scripts/load_release.py, serve/app.py,
# requirements.txt, requirements-repro.txt (repo main 1767f6e7), HF shgao/rsi-jev-v3.0-qwen3.5-2b (meta.json, card).
# Wire format: native POST /v1/systemone, copied from the TypeSafe reference. noul -> {"noul": p} only; choice ->
# probabilities by key; score -> probabilities "0".."n-1" + legend. Differences that can bite JevBench:
#   * "model" IS checked: must be the served name, the alias (default jev-latest) or an --accept-model name,
#     otherwise an error ("Unknown model"). We set --served-model-name to $SERVED.
#   * request schema is strict (extra="forbid", strict=True, no type coercion); criteria must be strings or null
#     (structured criteria objects are rejected with 422); up to 160 options (v3.0); 1-64 questions per request.
#   * states longer than 2,048 tokens are cut from the START with no warning (rsijev/encode.py).
# The repo is not a pip package: it is run from a checkout (`pip install -r requirements.txt`).
NAME=rsi-jev-2b
SERVED=rsi-jev-2b
PORT=8105
PYTHON=3.12
RSI_COMMIT=1767f6e75a5fa93a9f0b30939844405311a6fabb   # repo main on 2026-09-29
RSI_WEIGHTS_REV=c778b68dd5c20e67ac7ca8d8ef1f9a1258a687a5
RSI_CKPT="$HF_HOME/local/rsi-jev-v3.0-qwen3.5-2b"     # dir name is where serve.py reads the version ("v3.0") from
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    mkdir -p "$ENV/src" || return 1
    curl -fsSL "https://codeload.github.com/Shanghua-Gao/RSI-Jev/tar.gz/${RSI_COMMIT}" | tar xz -C "$ENV/src" || return 1
    # requirements.txt: torch>=2.13, transformers>=5.17,<6, safetensors, huggingface_hub, fastapi, uvicorn, pytest, httpx.
    # torch>=2.13 means a CUDA 13.0 wheel from PyPI (driver >= 580).
    # UNVERIFIED: flash-linear-attention is not in requirements.txt; the v3.0 numbers were produced with
    # "fla-0.5.2/torch-2.7.1+cu128" (meta.json linear_attn_kernel). Without fla transformers uses its torch fallback
    # for the Qwen3.5 linear-attention layers (slower, possibly tiny numeric drift). Not added, to follow the docs.
    uv pip install -r "$ENV/src/RSI-Jev-${RSI_COMMIT}/requirements.txt" || return 1
    RSI_CKPT="$RSI_CKPT" RSI_WEIGHTS_REV="$RSI_WEIGHTS_REV" python - <<'PY' || return 1
import os
from huggingface_hub import snapshot_download
snapshot_download("shgao/rsi-jev-v3.0-qwen3.5-2b", revision=os.environ["RSI_WEIGHTS_REV"], local_dir=os.environ["RSI_CKPT"])
snapshot_download("Qwen/Qwen3.5-2B-Base")   # meta.json base_model; loaded by AutoModelForCausalLM.from_pretrained (no revision pin)
PY
}
serve() {
    . "$ENV/bin/activate"
    cd "$ENV/src/RSI-Jev-${RSI_COMMIT}" || return 1
    # Documented: python scripts/serve.py --ckpt DIR --port 8000. Tower bf16 on CUDA by default, scorer fp32.
    exec python scripts/serve.py --ckpt "$RSI_CKPT" --device cuda --host 127.0.0.1 --port "$PORT" \
        --served-model-name "$SERVED"
}
