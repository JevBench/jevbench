# Kev-4B (Jared Palmer): https://github.com/jaredpalmer/kev  weights: jaredpalmer/kev-4b (Apache-2.0)  rank-16 LoRA + pointer head on Qwen/Qwen3.5-4B-Base@1001bb4d, fitted temperature 2.41  ~4.7B params (33.8M trainable)
# Sources checked: README.md ("Run It Locally", "API"), pyproject.toml (kev 0.1.0, requires-python >=3.12,<3.14,
# torch>=2.6,<2.9), .python-version (3.13), kev/serve.py, kev/api.py, kev/fused_qwen35.py (FLA_VERSION = "0.5.2"),
# docs/model-cards/kev-4b.md, HF jaredpalmer/kev-4b (training_config.json base_revision).
# Wire format: native POST /v1/systemone. choice -> probabilities keyed by option name; score -> probabilities keyed
# "0".."n-1" plus legend; noul -> {"noul": p}. The "model" field is echoed back, never checked.
# The PyPI project named "kev" is an unrelated package: install from git.
NAME=kev-4b
SERVED=kev-latest
PORT=8104
PYTHON=3.12
KEV_COMMIT=0fe8fc97c2bcc247fa3efb6e5c32af4e99770e91   # repo main on 2026-09-29 (only tag: v0.1.0, older)
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # README: `uv sync --extra serve` in a clone; this is the same package + extra, installed from a pinned commit
    # (the repo is ~150 MB because of runs/; pip clones it once). torch<2.9 -> torch 2.8 (CUDA 12.8 wheels).
    # flash-linear-attention==0.5.2: kev/serve.py turns the fused Qwen3.5 kernels on only when fla equals
    # FLA_VERSION ("install the flash-linear-attention version kev/fused_qwen35.py pins"); without it it still serves.
    uv pip install "kev[serve] @ git+https://github.com/jaredpalmer/kev@${KEV_COMMIT}" "flash-linear-attention==0.5.2" || return 1
    # "The first run downloads the adapter and the base model": pre-fetch both.
    python - <<'PY' || return 1
from huggingface_hub import snapshot_download
snapshot_download("jaredpalmer/kev-4b")
snapshot_download("Qwen/Qwen3.5-4B-Base", revision="1001bb4d826a52d1f399e183466143f4da7b741b")
PY
}
serve() {
    . "$ENV/bin/activate"
    cd "$ENV" || return 1   # --fallback defaults to the relative runs/smoke; keep cwd predictable
    # Documented: uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b --port 8009.
    # Device is automatic (cuda first); bf16 + CUDA graphs + fused kernels are the CUDA serving defaults.
    # UNVERIFIED: --run accepts "id@revision" (documented with a tag, jaredpalmer/kev-4b@qwen3); not pinned to the HF
    # commit (139fdd94f1b6a6ad80cc15e08fcb99cac885a101 on 2026-09-29) because a sha there was not documented.
    exec python -m kev.serve --run jaredpalmer/kev-4b --host 127.0.0.1 --port "$PORT"
}
