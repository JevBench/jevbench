# Von 1.3 (wfzyx): https://github.com/wfzyx/von  weights: wfzyx/von (Apache-2.0)  ModernBERT-large encoder + option-marker head, listwise CE+Brier, post-hoc temperature map  395M params
# Sources checked: README.md, pyproject.toml (von-sdk 1.3.1, requires-python >=3.12), src/von/cli.py,
# src/von/server.py, src/von/engine.py, src/von/backends/option_marker_backend.py (repo master, 2026-09-29).
# Wire format: native POST /v1/systemone. noul -> {"noul": p}; choice -> {"choice", "probabilities": {key: p}};
# score -> {"score", "probabilities": {"0": p, ...}} (keys are level indices). The "model" field is accepted
# (any string, pydantic default "von-latest") and ignored: engine.evaluate() always stamps "von-1.3.0".
# Chain-of-options (deterministic date/amount sub-decisions) is ON by default in 1.3; add --no-chains for the
# plain 1.2 path.
NAME=von
SERVED=von-latest
PORT=8101
PYTHON=3.12
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # torch is unpinned by von-sdk (torch>=2.0); PyPI torch>=2.11 wheels are CUDA 13.0 builds (driver >= 580).
    uv pip install "von-sdk==1.3.1" || return 1
    # Weights are otherwise fetched lazily on the first request (hf_hub_download of option_marker.pt and
    # marker_calibration.json plus the backbone from wfzyx/von); pre-fetch so the first probe does not time out.
    python - <<'PY' || return 1
from huggingface_hub import snapshot_download
snapshot_download("wfzyx/von")
PY
}
serve() {
    . "$ENV/bin/activate"
    # --device cuda is documented in the README table (--device / VON_DEVICE); host default is 0.0.0.0, so pin it.
    exec von serve --device cuda --host 127.0.0.1 --port "$PORT"
}
