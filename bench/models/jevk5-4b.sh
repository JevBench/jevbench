# JevK5 v0.3 4B (allebee / alibiserikbay): https://github.com/allebee/jevk5  weights: alibiserikbay/JevK5 (Apache-2.0)  Qwen3.5-4B + distilled LoRA (merged), SemIf-style option-letter logit readout, temperature 1.22 / knockout 0.93  4.2B params
# Sources checked: README.md ("Install and use", "As a server"), CHANGELOG.md, pyproject.toml, jevk5/server.py and
# jevk5/runtime.py at tag v0.3.0 (later tags v0.3.1-v0.3.3 change only JevK5-Lite / the 9B, "the runtime and the 4B are
# unchanged"), HF alibiserikbay/JevK5 (main c4f7fdb3 = "JevK5 v0.3 (4B)").
# Wire format: native POST /v1/systemone (stdlib ThreadingHTTPServer, one request at a time). noul -> {"noul": p}
# (+confidence); choice -> probabilities by option key; score -> probabilities keyed "0".."n-1". "model" is echoed,
# never checked. Errors are HTTP 400 {"error": ...}; choice needs >=2 options, score >=2 levels; >16 options are
# answered with ceil(n/16)+1 passes ("knockout").
NAME=jevk5-4b
SERVED=jevk5
PORT=8107
PYTHON=3.12
JEVK5_TAG=v0.3.0
JEVK5_WEIGHTS_REV=c4f7fdb3aeab5582336406e78d3bef11bf98833d
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # README: pip install "jevk5[fast] @ git+https://github.com/allebee/jevk5@v0.3.0"; [fast] = flash-linear-attention>=0.5, einops.
    # torch>=2.7 unpinned -> CUDA 13.0 wheel from PyPI (driver >= 580). Server needs no web framework (stdlib).
    uv pip install "jevk5[fast] @ git+https://github.com/allebee/jevk5@${JEVK5_TAG}" || return 1
    JEVK5_WEIGHTS_REV="$JEVK5_WEIGHTS_REV" python - <<'PY' || return 1
import os
from huggingface_hub import snapshot_download
snapshot_download("alibiserikbay/JevK5", revision=os.environ["JEVK5_WEIGHTS_REV"])
PY
}
serve() {
    . "$ENV/bin/activate"
    local model_dir
    model_dir="$(JEVK5_WEIGHTS_REV="$JEVK5_WEIGHTS_REV" python -c 'import os; from huggingface_hub import snapshot_download as s; print(s("alibiserikbay/JevK5", revision=os.environ["JEVK5_WEIGHTS_REV"]))')"
    # Documented: jevk5-serve --model alibiserikbay/JevK5 --port 8090 (JevK5(<local dir>) is documented too).
    # Runtime defaults to device="cuda" and captures one CUDA graph per padded input length.
    exec jevk5-serve --model "$model_dir" --host 127.0.0.1 --port "$PORT"
}
