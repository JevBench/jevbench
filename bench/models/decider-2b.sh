# decider-2b v10 (Mapika): https://github.com/Mapika/decider  weights: Mapika/decider-2b@v10 (Apache-2.0)  Qwen3.5-2B-Base fine-tune (v8) + 384 steps calibration-aware RL (v10), option-letter logit readout  1.9B params
# Sources checked: README.md (News: "2026-09-19 decider-2b v10 ... The v8 weights plus 384 steps of calibration-aware
# RL"; "v10 stay[s] under the Hub tag v10"), MODEL_CARD_4B.md (loading a Hub tag: snapshot_download(revision=...) then
# DECIDER_MODEL=<folder>), docs/SERVING.md, scripts/serve.sh, decider/serve.py, HF refs of Mapika/decider-2b.
# NOTE: Hub main of Mapika/decider-2b is now v11 (v10 + a LoRA stage, 2026-09-24; better on hard sets, 2.2 points lower
# on human-labelled sets). This spec serves the v10 tag as requested; set DECIDER_REV=main for v11.
# Wire format: native POST /v1/systemone, same as decider-4b (choice/score probabilities, noul {"noul": p});
# "model" field ignored.
NAME=decider-2b
SERVED=decider-2b
PORT=8103
PYTHON=3.12
DECIDER_REPO=Mapika/decider-2b
DECIDER_REV=v10           # HF tag v10 -> f972cbfcd707533d19a7bee11cf8617f5932b7c0 (main 533964da = v11)
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # UNVERIFIED: that decider-ai 1.6.0 serves the v10 config exactly as the v10-era package did. The 4B card says
    # 1.4.0+ reads the per-type temperature map and older configs fall back to the single "temperature"
    # (https://github.com/Mapika/decider/blob/main/MODEL_CARD_4B.md); v10 predates the map.
    uv pip install "decider-ai[serve]==1.6.0" || return 1
    DECIDER_REPO="$DECIDER_REPO" DECIDER_REV="$DECIDER_REV" python - <<'PY' || return 1
import os
from huggingface_hub import snapshot_download
snapshot_download(os.environ["DECIDER_REPO"], revision=os.environ["DECIDER_REV"])
PY
}
serve() {
    . "$ENV/bin/activate"
    cd "$ENV" || return 1   # keep a stray decider/ checkout off sys.path (docs/SERVING.md)
    local model_dir
    model_dir="$(DECIDER_REPO="$DECIDER_REPO" DECIDER_REV="$DECIDER_REV" python -c 'import os; from huggingface_hub import snapshot_download as s; print(s(os.environ["DECIDER_REPO"], revision=os.environ["DECIDER_REV"]))')"
    DECIDER_MODEL="$model_dir" DECIDER_DEVICE=cuda PYTHONSAFEPATH=1 \
        exec uvicorn decider.serve:app --host 127.0.0.1 --port "$PORT"
}
