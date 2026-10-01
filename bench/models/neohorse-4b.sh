# NeoHorse-Jev-4B (TokenRhythm): https://github.com/TokenRhythm/NeoHorse (jev/)  weights: TokenRhythm/NeoHorse-Jev-4B (Apache-2.0)  NeoHorse-1-4B (from Qwen3.5-4B) backbone + separate pointer decision head (code adapted from Kev), multimodal  ~4B params (9.08 GB bf16 backbone)
# Sources checked: HF model card README.md, DEPLOYMENT.md, environment.json, package/pyproject.toml,
# package/src/neohorse_decision/{cli.py,systemone.py} (HF main 434cb21d).
# Three documented paths: vLLM 0.28.0 (infer/vllm/launch.py in the GitHub repo), SGLang 0.5.17, and the native
# neohorse_decision runtime. The native runtime is used here: it ships in the HF bundle and has its own
# `neohorse-decision serve` with POST /v1/systemone (the vLLM/SGLang launchers need the GitHub checkout; their HTTP
# surface was not checked).
# Wire format: POST /v1/systemone. noul -> {"type","noul"}; choice -> choice/probabilities/confidence; score ->
# score/legend/probabilities (levels indexed from 0). "model" IS checked: must be one of NeoHorse-Jev-4B,
# TokenRhythm/NeoHorse-Jev-4B, neohorse-jev, NeoHorse-JEV-4B, TokenRhythm/NeoHorse-JEV-4B ("not a Jev model alias").
# Limits (rejected, never truncated): state 2,048 tokens; 16 questions per request; Score 2-10 levels; 529 when busy.
NAME=neohorse-4b
SERVED=NeoHorse-Jev-4B
PORT=8110
PYTHON=3.12
NH_REV=434cb21d3a994a953d3ae5788405fcb2c4970554
NH_DIR="$HF_HOME/local/NeoHorse-Jev-4B"
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    uv pip install huggingface_hub || return 1
    NH_DIR="$NH_DIR" NH_REV="$NH_REV" python - <<'PY' || return 1
import os
from huggingface_hub import snapshot_download
snapshot_download("TokenRhythm/NeoHorse-Jev-4B", revision=os.environ["NH_REV"], local_dir=os.environ["NH_DIR"])
PY
    # Recorded environment (environment.json): Python 3.12, torch 2.8.0 (CUDA 12.8), transformers 5.17.0,
    # safetensors 0.8.0, pydantic 2.13.5, peft 0.21.0, triton 3.7.1, flash-linear-attention 0.5.2, tokenizers 0.23.2,
    # huggingface-hub 1.32.0, einops 0.8.2. The docs install the wheel with --no-deps into that prepared env.
    uv pip install "torch==2.8.0" "transformers==5.17.0" "safetensors==0.8.0" "pydantic==2.13.5" "peft==0.21.0" \
        "flash-linear-attention==0.5.2" "tokenizers==0.23.2" "huggingface-hub==1.32.0" "einops==0.8.2" \
        "fastapi==0.141.1" "uvicorn==0.53.0" "starlette==1.6.0" "httpx==0.28.1" "pillow==12.3.0" || return 1
    # UNVERIFIED: torch 2.8.0 declares triton==3.4.0, but the recorded env has triton 3.7.1 (installed separately;
    # DEPLOYMENT.md: "check whether dependency resolution changes the Triton version"). Forcing 3.7.1 without deps
    # to match; drop this line if torch/inductor complains (source: environment.json on the HF repo).
    uv pip install --no-deps "triton==3.7.1" || return 1
    uv pip install --no-deps "$NH_DIR/dist/neohorse_decision-1.0.0-py3-none-any.whl" || return 1
}
serve() {
    . "$ENV/bin/activate"
    # Documented: CUDA_VISIBLE_DEVICES=0 neohorse-decision serve --model-dir "$MODEL_DIR" --port 8080 (binds 127.0.0.1).
    exec neohorse-decision serve --model-dir "$NH_DIR" --device cuda --host 127.0.0.1 --port "$PORT"
}
