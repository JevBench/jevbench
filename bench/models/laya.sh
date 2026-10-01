# Laya (Convai Innovations): ModernBERT-large encoder, option markers, RLCD. Apache-2.0.
# https://github.com/NandhaKishorM/laya  weights: convaiinnovations/laya ("english" checkpoint, 421M)
# Serving per the README: LAYA_HOST/LAYA_PORT/LAYA_DEVICE/LAYA_PRELOAD/LAYA_MODELS env vars; POST /v1/systemone;
# a request's "model" field selects the checkpoint (english | multilingual | typed-decisions).
NAME=laya
SERVED=english
PORT=8100
PYTHON=3.11
setup() {
    uv venv --python "$PYTHON" "$ENV"
    . "$ENV/bin/activate"
    uv pip install "laya[serve]==0.3.21"
}
serve() {
    . "$ENV/bin/activate"
    LAYA_HOST=127.0.0.1 LAYA_PORT="$PORT" LAYA_DEVICE=cuda LAYA_PRELOAD=1 LAYA_MODELS="$SERVED" exec laya-serve
}
