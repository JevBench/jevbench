# Open-Jev-9B (Zefan Cai): https://github.com/Zefan-Cai/Open-Jev  weights: ZefanCai/Open-Jev-9B (adapter+head Apache-2.0, code MIT)  rank-8 LoRA + scalar decision head on Qwen/Qwen3.5-9B@c2022362, independent-candidate NLL+Brier training, saved temperature 1.897  ~9.7B params (base) + adapter
# Sources checked: HF model card ("Download and run"), package/checkpoint/model.json; repo pyproject.toml (open-jev
# 0.1.0.dev0, extra train = torch>=2.8, transformers==5.10.2, peft==0.19.1, accelerate==1.13.0, datasets==5.0.0,
# safetensors), jev/server.py, jev/serving.py, jev/api.py (repo main 3308a15c).
# Wire format: POST /v1/systemone (also /v1/inference, /api/jev); requires Content-Type: application/json.
# noul -> {"noul": p}; choice -> probabilities by key; score -> probabilities "0".."n-1" + legend. "model" is
# optional; if given it must be open-jev, jev-latest or the predictor's model name. Inputs over 4,096 tokens per
# candidate are rejected (422), not truncated.
NAME=open-jev-9b
SERVED=open-jev
PORT=8111
PYTHON=3.12
OJ_COMMIT=3308a15ccd7eea1df7a37d6ddc39b023b801ba16      # repo main on 2026-09-23 (latest on 2026-09-29)
OJ_WEIGHTS_REV=47e966881e489511c0c7f5633a9e1960a676a551
OJ_DIR="$HF_HOME/local/open-jev-9b"
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # Card: git clone ... && pip install -e '.[train]' ("the train extra supplies inference dependencies too").
    # torch>=2.8 unpinned -> CUDA 13.0 wheel from PyPI (driver >= 580).
    uv pip install "open-jev[train] @ git+https://github.com/Zefan-Cai/Open-Jev@${OJ_COMMIT}" || return 1
    OJ_DIR="$OJ_DIR" OJ_WEIGHTS_REV="$OJ_WEIGHTS_REV" python - <<'PY' || return 1
import os
from huggingface_hub import snapshot_download
snapshot_download("ZefanCai/Open-Jev-9B", revision=os.environ["OJ_WEIGHTS_REV"], local_dir=os.environ["OJ_DIR"])
snapshot_download("Qwen/Qwen3.5-9B", revision="c202236235762e1c871ad0ccb60c8ee5ba337b9a")  # pinned in model.json
PY
}
serve() {
    . "$ENV/bin/activate"
    cd "$ENV" || return 1
    # Exactly the card's command (bf16 9B ~19 GB fits on a 40 GB A100; --batch-size 1, prefix cache off).
    exec python -m jev.server --checkpoint "$OJ_DIR/package/checkpoint" \
        --device cuda:0 --max-length 4096 --batch-size 1 --no-prefix-cache \
        --host 127.0.0.1 --port "$PORT"
}
