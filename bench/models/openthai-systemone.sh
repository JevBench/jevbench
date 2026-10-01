# OpenThai-SystemOne (iApp Technology): https://github.com/iapp-technology/openthai-systemone  weights: iapp/OpenThai-SystemOne (Apache-2.0)
# Qwen3.5-0.8B-Base text tower (hybrid Gated-DeltaNet/attention), continued-pretrained on ~5B Thai tokens, 256-slot
# decision head (slot 255 = abstain), SFT on ~2-3M public and synthetic Thai/English decisions, then calibrated. 0.75B.
# Sources checked: HF model card (Usage: pip package, uvicorn server), PyPI openthai-systemone 0.1.0 (requires torch>=2.4,
# transformers>=5.0; extra "server" = fastapi, uvicorn), wheel sources server.py, client.py, types.py.
# Wire format: native POST /v1/systemone (TypeSafe contract). Noul criteria may be null; choice probabilities are
# renormalised over the real options (the abstain slot is reported separately); score probabilities "0".."n-1".
# The "model" field is echoed back, never checked. Device: cuda if available, bf16.
NAME=openthai-systemone
SERVED=openthai-systemone
PORT=8115
PYTHON=3.11
OT_REV=f3709948b5e3cc9606a57e74ba62b7a639d17dd3   # HF main on 2026-09-30
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    uv pip install "openthai-systemone[server]==0.1.0" || return 1
    python - <<PY || return 1
from huggingface_hub import snapshot_download
print(snapshot_download("iapp/OpenThai-SystemOne", revision="$OT_REV"))
PY
}
serve() {
    . "$ENV/bin/activate"
    path=$(python -c "from huggingface_hub import snapshot_download; print(snapshot_download('iapp/OpenThai-SystemOne', revision='$OT_REV'))")
    OPENTHAI_SYSTEMONE_MODEL="$path" OPENTHAI_SYSTEMONE_NAME="$SERVED" \
        exec uvicorn openthai_systemone.server:app --host 127.0.0.1 --port "$PORT"
}
