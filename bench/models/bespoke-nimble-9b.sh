# Bespoke-Nimble-9B (Bespoke Labs): https://github.com/bespokelabsai/nimble  weights: bespokelabs/Bespoke-Nimble-9B (Apache-2.0)  LoRA on Qwen/Qwen3.5-9B@c2022362 scoring the allowed one-letter answer tokens at one slot, T=1.0 (2026-09-24 checkpoint, 8,192-token context, <=255 choices)  ~9.7B params (base) + 165 MiB adapter
# Sources checked: HF model card ("Loading and scoring"), inference.py, serving_schema.py, parallel_schema.py,
# requirements.txt (HF main bd792f44); GitHub README.md, docs/MODAL_SERVING.md, docs/TRY_NIMBLE.md,
# nimble/serving/server.py, nimble/serving/compiler.py (repo main 62076b4f). Bespoke-Nimble-9B-v2 is a separate repo.
# INCOMPATIBLE (no locally runnable /v1/systemone server; shim below):
#   * The only /v1/systemone server (nimble/serving/server.py) is the Modal deployment: it hard-codes
#     /opt/sglang/bin/python for SGLang 0.5.19, binds 0.0.0.0:8000, needs a merged-LoRA model directory with a
#     READY.json written by the Modal build (deploy/modal_app.py), imports openjev-sglang@7f84bedc, and serves the
#     OLD adapter revision 93ec5d6f (2,676 examples), not the current checkpoint.
#   * The documented local CUDA path is the Python API in the model card: NimbleModel(model_dir).score(context=str,
#     schema={field: {"type": "boolean"|"enum", "description": str, "choices": [...], "choice_descriptions": {...}}},
#     score_fields=[...]) -> {"output": {field: prediction}, "fields": {field: {"prediction", "probabilities": {key: p},
#     "logits", "probability_true" (boolean), "expected_score" (score fields)}}, "temperature", "temperature_fitted"}.
#     Booleans are keyed "true"/"false"; enums by the choice string; score fields must be integer-valued enum strings.
#   * serve() therefore runs a small FastAPI shim that maps the Jev wire format onto that API, using the same mapping
#     as Nimble's own compiler (nimble/serving/compiler.py): noul -> boolean with choice_descriptions
#     {"false": criteria.false or "No", "true": criteria.true or "Yes"}; choice -> enum of the option keys with
#     descriptions (key itself when null); score -> enum ["0".."n-1"] with the level texts, listed in score_fields;
#     non-string state/instructions/descriptions are JSON-serialised. The question id is the schema field name, which
#     the trained prompt shows to the model.
# CHECKED (2026-10-01) against compiler.py@62076b4f: the shim is ours, not Bespoke's, but it builds the same request: all
# questions of a request become one schema, passed once to prepare_prompts (serving_schema.py / parallel_schema.py),
# so every field's prompt shows the whole schema, as in Bespoke's own server; type mappings are the same. Differences:
# the current checkpoint (Bespoke's Modal server pins 93ec5d6f); the PyTorch reference runner instead of SGLang; the
# model's own max_length instead of the server's 2048-token prompt limit (longer requests are answered, not refused);
# empty instructions fall back to the question id (no JevBench test sends empty instructions). Fields are scored one per
# forward pass (reference runner), so multi-question requests are slower than the SGLang deployment.
NAME=bespoke-nimble-9b
SERVED=nimble-latest
PORT=8112
PYTHON=3.12
NIMBLE_REV=bd792f44ec8e265be861bfcdf4e05967ffe0e858
NIMBLE_DIR="$HF_HOME/local/Bespoke-Nimble-9B"
setup() {
    uv venv --python "$PYTHON" "$ENV" || return 1
    . "$ENV/bin/activate"
    # Card: "The original run used PyTorch 2.8.0 with CUDA 12.8 ... then the remaining pinned requirements"
    # (requirements.txt: transformers==5.17.0 peft==0.21.0 accelerate==1.15.0 sentencepiece==0.2.2 pillow==12.3.0
    # huggingface_hub>=0.34). fastapi/uvicorn are for the shim only. No flash-linear-attention: the reference runner
    # loads Qwen3_5ForConditionalGeneration with attn_implementation="sdpa" (torch fallback for linear attention).
    uv pip install "torch==2.8.0" "transformers==5.17.0" "peft==0.21.0" "accelerate==1.15.0" \
        "sentencepiece==0.2.2" "pillow==12.3.0" "huggingface_hub>=0.34" fastapi uvicorn || return 1
    NIMBLE_DIR="$NIMBLE_DIR" NIMBLE_REV="$NIMBLE_REV" python - <<'PY' || return 1
import os
from huggingface_hub import snapshot_download
snapshot_download("bespokelabs/Bespoke-Nimble-9B", revision=os.environ["NIMBLE_REV"], local_dir=os.environ["NIMBLE_DIR"])
snapshot_download("Qwen/Qwen3.5-9B", revision="c202236235762e1c871ad0ccb60c8ee5ba337b9a")  # schema_config.json base
PY
    cat > "$ENV/nimble_shim.py" <<'PY' || return 1
"""Jev /v1/systemone -> Bespoke-Nimble NimbleModel.score() shim (jevbench). Not part of Nimble."""
import json, os, sys
import uvicorn
from fastapi import FastAPI, HTTPException

MODEL_DIR = os.environ["NIMBLE_MODEL_DIR"]
SERVED = os.environ.get("NIMBLE_SERVED", "nimble-latest")
sys.path.insert(0, MODEL_DIR)
from inference import NimbleModel  # noqa: E402  (model-card import; checks prompt-code hashes itself)

model = NimbleModel(MODEL_DIR)
app = FastAPI(title="nimble-shim")


def text(v):
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, allow_nan=False)


@app.get("/health")
def health():
    return {"ok": True, "model": SERVED}


@app.post("/v1/systemone")
def systemone(body: dict):
    try:
        state, questions = body["state"], body["questions"]
        if not isinstance(questions, dict) or not questions:
            raise ValueError("questions must be a non-empty object")
        schema, score_fields, kinds = {}, [], {}
        for qid, q in questions.items():
            kind, crit = q.get("type"), q.get("criteria")
            desc = text(q.get("instructions")) if q.get("instructions") is not None else ""
            if not desc.strip():
                desc = qid
            if kind == "noul":
                crit = crit or {}
                f = {"type": "boolean", "choices": [False, True], "description": desc,
                     "choice_descriptions": {"false": text(crit.get("false") or "No"),
                                             "true": text(crit.get("true") or "Yes")}}
            elif kind == "choice":
                if isinstance(crit, list):
                    crit = {k: None for k in crit}
                f = {"type": "enum", "description": desc, "choices": list(crit),
                     "choice_descriptions": {k: (text(v) if v is not None else k) for k, v in crit.items()}}
            elif kind == "score":
                keys = [str(i) for i in range(len(crit))]
                f = {"type": "enum", "description": desc, "choices": keys,
                     "choice_descriptions": {k: text(v) for k, v in zip(keys, crit)}}
                score_fields.append(qid)
            else:
                raise ValueError(f"{qid}: unknown question type {kind!r}")
            schema[qid], kinds[qid] = f, kind
        res = model.score(context=text(state), schema=schema, score_fields=score_fields)
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(422, f"invalid request: {e}")
    answers = {}
    for qid, kind in kinds.items():
        r = res["fields"][qid]
        p = r["probabilities"]
        if kind == "noul":
            answers[qid] = {"type": "noul", "noul": p["true"]}
        elif kind == "choice":
            answers[qid] = {"type": "choice", "choice": r["prediction"], "probabilities": p}
        else:
            answers[qid] = {"type": "score", "score": r["expected_score"], "probabilities": p,
                            "legend": {k: text(v) for k, v in zip(schema[qid]["choices"], questions[qid]["criteria"])}}
    return {"model": SERVED, "answers": answers}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ["NIMBLE_PORT"]))
PY
}
serve() {
    . "$ENV/bin/activate"
    cd "$ENV" || return 1
    NIMBLE_MODEL_DIR="$NIMBLE_DIR" NIMBLE_SERVED="$SERVED" NIMBLE_PORT="$PORT" exec python "$ENV/nimble_shim.py"
}
