# jevhome/jevhome-ettin-1b (Jibril Frej): https://github.com/Jibril-Frej/jev-at-home  weights: jevhome/jevhome-ettin-1b (CC-BY-NC-4.0: research use only)
# Ettin-encoder-1B cross-encoder, ~1.0B, fp32 ONNX; distilled from an open teacher (Qwen3.5-4B option-letter distribution) plus gold labels on
# 37 public datasets and Qwen-written synthetic data; one temperature per question type and option count.
# Sources checked: HF model card ("Run it": cargo build --release; jevhome serve <model_dir>), jev-at-home README (Rust
# binary, prebuilt ONNX Runtime 1.28 fetched at build time; serve flags --threads 4 --port 8009 --host 127.0.0.1;
# "model" is echoed back; choice 1-255 options).
# Runs on CPU (no GPU needed). One request at a time, questions in order; --threads sets cores per decision.
# Rust is installed under $JEVBENCH_ROOT with the official rustup installer (never into $HOME).
NAME=jevhome-ettin-1b
SERVED=jevhome-ettin-1b
PORT=8119
PYTHON=3.11
JEVHOME_COMMIT=2eea9ee41701feff996e23284c2d4444529b2e66   # repo main on 2026-09-30
MODEL_REPO=jevhome/jevhome-ettin-1b
MODEL_REV=3d0d41ceb990f0b92874bfd4c128617ad34d62c8                                            # HF main on 2026-09-30
export RUSTUP_HOME="$JEVBENCH_ROOT/cache/rustup" CARGO_HOME="$JEVBENCH_ROOT/cache/cargo"
RUST_TOOLCHAIN=1.98.1   # rustc stable on 2026-09-30
JEVHOME_SRC="$JEVBENCH_ROOT/src/jev-at-home-$JEVHOME_COMMIT"   # one build shared by the jevhome specs
setup() {
    uv venv --allow-existing --python "$PYTHON" "$ENV" || return 1   # reuse the env of an interrupted setup
    . "$ENV/bin/activate"
    # onnxruntime supplies libonnxruntime.so for the "dynamic" build: the static build links a prebuilt ONNX
    # Runtime made with a newer libstdc++ than some Linux systems ship (undefined std::__cxx11 symbols); upstream checked
    # the dynamic build against Python onnxruntime 1.26 (same answers to 1e-6)
    uv pip install "huggingface_hub>=0.34" "onnxruntime==1.26.*" || return 1
    if [ ! -f "$JEVHOME_SRC/.dynamic-build" ]; then
        [ -x "$CARGO_HOME/bin/rustup" ] || { curl -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path --profile minimal --default-toolchain none || return 1; }
        # a pinned toolchain in its own directory (an interrupted install left "stable" without cargo)
        "$CARGO_HOME/bin/rustup" toolchain install "$RUST_TOOLCHAIN" --profile minimal || return 1
        mkdir -p "$(dirname "$JEVHOME_SRC")"
        [ -d "$JEVHOME_SRC/.git" ] || git clone https://github.com/Jibril-Frej/jev-at-home "$JEVHOME_SRC" || return 1
        ( cd "$JEVHOME_SRC" && git checkout -q "$JEVHOME_COMMIT" && "$CARGO_HOME/bin/cargo" "+$RUST_TOOLCHAIN" build --release --no-default-features --features dynamic ) || return 1
    fi
    touch "$JEVHOME_SRC/.dynamic-build"
    python - <<PY || return 1
from huggingface_hub import snapshot_download
# a plain directory, not the symlinked HF cache: ONNX Runtime refuses external data (model.onnx.data)
# that resolves outside the model directory
print(snapshot_download("$MODEL_REPO", revision="$MODEL_REV", ignore_patterns=["pytorch/*"],
                        local_dir="$ENV/model-$MODEL_REV"))
PY
}
serve() {
    . "$ENV/bin/activate"
    dir=$(python -c "from huggingface_hub import snapshot_download; print(snapshot_download('$MODEL_REPO', revision='$MODEL_REV', ignore_patterns=['pytorch/*'], local_dir='$ENV/model-$MODEL_REV'))")
    ORT_DYLIB_PATH=$(python -c "import glob, os, onnxruntime; print(sorted(glob.glob(os.path.join(os.path.dirname(onnxruntime.__file__), 'capi', 'libonnxruntime.so*')))[0])")
    export ORT_DYLIB_PATH
    exec "$JEVHOME_SRC/target/release/jevhome" serve "$dir" --threads "${JEVHOME_THREADS:-16}" --host 127.0.0.1 --port "$PORT"
}
