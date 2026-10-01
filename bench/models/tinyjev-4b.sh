# TinyJev-4B (AnkitAI / ankit-aglawe): https://github.com/ankit-aglawe/tinyjev  weights: AnkitAI/TinyJev-4B (MIT; base Qwen3-4B-Base Apache-2.0)  Qwen3-4B-Base + LoRA r16 (merged) + pointer head (Kev design, Kev decision-v7 data), temperature 1.0  4.0B params
# Sources checked: HF model card ("Use it"), tinyjev/cli.py, tinyjev/serve.py, tinyjev/agent.py, tinyjev/registry.py,
# tinyjev/backends/torch_backend.py (repo main b49b43b2), PyPI tinyjev 0.1.3 (2026-09-25, same day as the 4B).
# MLX-first, but the card documents `pip install 'tinyjev[torch]'` for "everything else"; the torch backend picks
# cuda when available and loads the backbone in fp16. `--quantize` is MLX-only (cli help), so it is not used.
# Wire format: POST /v1/systemone (stdlib HTTPServer, single-threaded). noul -> {"noul": p}; choice ->
# choice/confidence/probabilities; score -> score/legend/probabilities. "model" is echoed, never checked.
# UNVERIFIED: score "probabilities" keys (index "0".. vs level text) come from the pointer head's result and were not
# traced (https://github.com/ankit-aglawe/tinyjev/blob/main/tinyjev/agent.py); JevBench accepts either.
NAME=tinyjev-4b
SERVED=TinyJev-4B
PORT=8113
PYTHON=3.12
TJ_WEIGHTS_REV=29c6fb10a28c5da2f0e7cf12fe52c9373baa41db
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # [torch] = torch>=2.2, transformers>=4.45 (unpinned torch -> CUDA 13.0 wheel from PyPI, driver >= 580).
    uv pip install "tinyjev[torch]==0.1.3" || return 1
    TJ_WEIGHTS_REV="$TJ_WEIGHTS_REV" python - <<'PY' || return 1
import os
from huggingface_hub import snapshot_download
snapshot_download("AnkitAI/TinyJev-4B", revision=os.environ["TJ_WEIGHTS_REV"])
PY
}
serve() {
    . "$ENV/bin/activate"
    # Documented: tinyjev serve TinyJev-4B --quantize 8 (POST /v1/systemone on 127.0.0.1:8077). The registry alias
    # TinyJev-4B resolves to AnkitAI/TinyJev-4B; --backend/--device are the documented torch-backend flags.
    exec tinyjev serve TinyJev-4B --backend torch --device cuda --host 127.0.0.1 --port "$PORT"
}
