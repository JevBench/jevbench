# Verdict 1.4 (Heman10x) via OpenJev: https://github.com/Heman10x-NGU/Verdict-open-jev  weights: heman10x/rlcd-modernbert-151m (Apache-2.0; GitHub reports the repo LICENSE as NOASSERTION but its text is Apache-2.0)  ModernBERT-base + GLiClass bi-encoder head, RLCD/Brier calibration, v1.4 inference engine  151M params
# Server: https://github.com/razorback16/openjev (Apache-2.0), OPENJEV_BACKEND=verdict, which loads the checkpoint
# in-process with gliclass and reimplements Verdict's v1.4 prompt format and temperatures.
# Sources checked: Verdict README.md + pyproject.toml (package "rlcd": Python SDK and ONNX, no HTTP server);
# OpenJev README.md ("Encoder models" section), pyproject.toml (openjev 0.5.0, extra verdict = gliclass==0.1.20),
# openjev/__main__.py, openjev/config.py, openjev/encoders.py, openjev/api.py, docker/Dockerfile.verdict,
# docker/Dockerfile.base (repo main a0ddd7d9).
# Run without Docker as documented for the encoder backends: pip install -e '.[<backend>]' && OPENJEV_BACKEND=<b>
# python -m openjev. Env vars: OPENJEV_BACKEND, OPENJEV_HOST (default 127.0.0.1), OPENJEV_PORT (default 8080),
# OPENJEV_DEVICE (empty = cuda if available), OPENJEV_VERDICT_MODEL (default heman10x/rlcd-modernbert-151m),
# OPENJEV_ENCODER_BATCH (16), OPENJEV_WARMUP (1).
# Wire format: POST /v1/systemone, Jev shapes: choice probabilities by key, score probabilities "0".."n-1", noul
# {"noul": p}. "model" IS checked: verdict-1.4, jev-latest or jev-preview; otherwise 400 "Unknown model".
# Behaviour notes (OpenJev README): Verdict's extra "insufficient evidence" option is removed and the rest renormalised;
# noul criteria are ignored; state cut to 512 tokens silently; up to 24 choices; bf16 on GPU.
NAME=verdict
SERVED=verdict-1.4
PORT=8109
PYTHON=3.12
OPENJEV_COMMIT=a0ddd7d928298eccef2c17153b00b5636b6d996a   # repo main on 2026-09-29 (no tags)
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # The verdict extra does not list torch itself ("both need PyTorch"); the Docker base installs torch==2.13.0
    # (CUDA 13.0 wheel, driver >= 580), so the same pin is used here. gliclass 0.1.20 needs transformers>=5.
    uv pip install "torch==2.13.0" "openjev[verdict] @ git+https://github.com/razorback16/openjev@${OPENJEV_COMMIT}" || return 1
    python - <<'PY' || return 1
from huggingface_hub import snapshot_download
snapshot_download("heman10x/rlcd-modernbert-151m")
PY
}
serve() {
    . "$ENV/bin/activate"
    cd "$ENV" || return 1
    OPENJEV_BACKEND=verdict OPENJEV_HOST=127.0.0.1 OPENJEV_PORT="$PORT" OPENJEV_DEVICE=cuda \
        exec python -m openjev
}
