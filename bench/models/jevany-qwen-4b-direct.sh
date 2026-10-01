# JevAny (JevAny-Qwen3.5-4B-Direct-Token-LoRA, SimpleJev): https://github.com/SimpleJev/JevAny  weights: SimpleJev/JevAny-Qwen3.5-4B-Direct-Token-LoRA (Apache-2.0 LICENSE file; base Qwen/Qwen3.5-4B)
# LoRA SFT on 1.77M records (2.18M decisions) with a direct-token readout (<= 255 options); the three JevAny 4B releases share the data, so they
# isolate the readout (Qwen pointer vs direct-token) and the backbone (Qwen vs Gemma).
# Sources checked: README.md (Deployment: pip install -e '.[serve,multimodal]'; jevany serve --checkpoint <id> --device cuda
# --dtype bf16 --port 8008), pyproject.toml (jevany 0.3.0, python >=3.12, torch>=2.6,<2.9, transformers>=5.17,<6),
# jevany/serve.py (--checkpoint/--run, --device, --dtype, --host, --port; POST /v1/systemone), jevany/api.py (Noul criteria
# optional; "model" is any non-empty string), HF adapter_config.json (base_model_name_or_path Qwen/Qwen3.5-4B).
# Wire format: native POST /v1/systemone, contract-tested upstream against the TypeSafe SDK.
NAME=jevany-qwen-4b-direct
SERVED=jevany-qwen-4b-direct
PORT=8117
PYTHON=3.12
JEVANY_COMMIT=fc4f78be59028fe06d267d8052484cf3f3b2a8fa   # repo main on 2026-09-30
CKPT_REV=4c7fd2539994f37f5db3130704f528f011e448d1                                             # HF main on 2026-09-30
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    uv pip install "jevany[serve,multimodal] @ git+https://github.com/SimpleJev/JevAny@${JEVANY_COMMIT}" || return 1
    python - <<PY || return 1
from huggingface_hub import snapshot_download
print(snapshot_download("SimpleJev/JevAny-Qwen3.5-4B-Direct-Token-LoRA", revision="$CKPT_REV"))
snapshot_download("Qwen/Qwen3.5-4B")   # the loader fetches the base on first use; pre-fetch it (UNVERIFIED: base revision not pinned upstream)
PY
}
serve() {
    . "$ENV/bin/activate"
    ckpt=$(python -c "from huggingface_hub import snapshot_download; print(snapshot_download('SimpleJev/JevAny-Qwen3.5-4B-Direct-Token-LoRA', revision='$CKPT_REV'))")
    exec python -m jevany.serve --checkpoint "$ckpt" --model-name "$SERVED" --device cuda --dtype bf16 \
        --host 127.0.0.1 --port "$PORT"
}
