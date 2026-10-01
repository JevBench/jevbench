# OneJev-4B (OmniJev): https://github.com/OmniJev/OneJev  weights: OmniJev/OneJev-4B (Apache-2.0)  full-parameter fine-tune of Qwen3.5-4B (vision tower frozen), option-letter probability at the last position, multimodal  5.2B params (HF safetensors total)
# Sources checked: README.md, pyproject.toml (qev 0.1.0, requires-python >=3.10), qev/cli.py, qev/server.py,
# qev/answers.py, qev/mm_engine.py (repo main 50d897d3), HF OmniJev/OneJev-4B.
# Wire format: native POST /v1/systemone (TypeSafe request + optional "media"). noul -> {"noul": p}; choice ->
# probabilities by option key; score -> probabilities "0".."n-1" + legend. "model" IS checked: it must be the
# served name (--name) or one of the aliases jev-latest, jev-preview, qev-latest, else HTTP 404.
NAME=onejev-4b
SERVED=onejev-4b
PORT=8106
PYTHON=3.12
ONEJEV_COMMIT=50d897d38d0262970220fe6b01b0fae3cc4f2016   # repo main on 2026-09-29 (no tags)
ONEJEV_WEIGHTS_REV=c88e18653ceb7a8770716287f55fdefc79d6b588
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # README: pip install "qev[torch] @ git+https://github.com/OmniJev/OneJev.git" (pinned to a commit here).
    # [torch] = torch>=2.6, torchvision>=0.21, accelerate, safetensors; unpinned torch -> CUDA 13.0 wheel from PyPI.
    # flash-linear-attention is not mentioned by OneJev; not added.
    uv pip install "qev[torch] @ git+https://github.com/OmniJev/OneJev.git@${ONEJEV_COMMIT}" || return 1
    ONEJEV_WEIGHTS_REV="$ONEJEV_WEIGHTS_REV" python - <<'PY' || return 1
import os
from huggingface_hub import snapshot_download
snapshot_download("OmniJev/OneJev-4B", revision=os.environ["ONEJEV_WEIGHTS_REV"])
PY
}
serve() {
    . "$ENV/bin/activate"
    # Documented: qev serve --model OmniJev/OneJev-4B --port 8000. --device default cuda:0, --dtype bfloat16,
    # CUDA graphs on; config.json has vision_config so the multimodal engine is used even for text.
    exec qev serve --model OmniJev/OneJev-4B --name "$SERVED" --device cuda:0 --host 127.0.0.1 --port "$PORT"
}
