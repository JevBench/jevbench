# Jebadiah 9B v2 (Frontier Infra): https://github.com/getainode/jebadiah  weights: frontier-infra/jebadiah-9b-v2 (Apache-2.0)  LoRA r16 merged into Qwen/Qwen3.5-9B@c2022362 (chat model, thinking off), label-token distribution at the last position, per-type temperatures.json  9.65B params
# Sources checked: HF model card ("Standalone server", "Versioning and license"), server/pyproject.toml
# (jebadiah-server 0.1.0, requires-python >=3.12,<3.13, torch==2.14.0, transformers==5.17.0, accelerate==1.15.0,
# extra cuda = flash-linear-attention>=0.5), server/src/jebadiah_server/{cli.py,app.py} (repo main 63cc7367).
# Wire format: native POST /v1/systemone (also AINode's /v1/decide). choice -> choice/confidence/probabilities per key;
# noul -> {"noul": P(true)}; score -> score/legend/probabilities; plus a "calibration" block. "model" IS checked
# when given: the HF id, its short name (jebadiah-9b-v2) or an --alias; otherwise a 400. Choice capped at 20 options.
NAME=jebadiah-9b
SERVED=jebadiah-9b-v2
PORT=8114
PYTHON=3.12
JEB_COMMIT=63cc7367ee77871ec598dde1a7bdc94254a11966   # repo main on 2026-09-29
JEB_WEIGHTS_REV=df20afa4ffe145128b9342815ba31662158202b0
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # Card: cd jebadiah/server && uv sync (--extra cuda on a CUDA box). Same package + extra from a pinned commit.
    # torch==2.14.0 is a CUDA 13.0 wheel on PyPI (driver >= 580).
    uv pip install "jebadiah-server[cuda] @ git+https://github.com/getainode/jebadiah@${JEB_COMMIT}#subdirectory=server" || return 1
    JEB_WEIGHTS_REV="$JEB_WEIGHTS_REV" python - <<'PY' || return 1
import os
from huggingface_hub import snapshot_download
snapshot_download("frontier-infra/jebadiah-9b-v2", revision=os.environ["JEB_WEIGHTS_REV"])
PY
}
serve() {
    . "$ENV/bin/activate"
    # Documented: uv run jebadiah-serve --model frontier-infra/jebadiah-9b-v2 (default 127.0.0.1:8000).
    # --device/--dtype default "auto"; bf16 9.65B ~19 GB fits a 40 GB A100.
    exec jebadiah-serve --model frontier-infra/jebadiah-9b-v2 --revision "$JEB_WEIGHTS_REV" \
        --device cuda --host 127.0.0.1 --port "$PORT"
}
