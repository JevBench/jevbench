"""Test a model loaded in this Python process, one replica per GPU.

Any package works the same way: load one copy of the model per device, wrap each in a function
`(state, questions) -> answers` (the System One wire format), and pass the list. JevBench calls
each function from one thread at a time, so the functions need not be thread-safe, and the
answers are those of a sequential run.

Here with the `laya` package (`pip install laya`):

    python examples/in_process_model.py cuda:0 cuda:1
"""

import json
import sys

import laya

import jevbench as jb

MODEL_ID = "convaiinnovations/laya"


def replica(device):
    agent = laya.load(MODEL_ID, device=device)

    def ask(state, questions):
        text = state if isinstance(state, str) else json.dumps(state)
        return agent.system_one(text, questions)["answers"]

    return ask


devices = sys.argv[1:] or ["cuda:0"]
model = jb.from_callable([replica(d) for d in devices], name=f"laya:{MODEL_ID}")  # the name keys the cache
report = jb.evaluate(model, domains=["finance_ops"], progress=True)
print(report.table("dimension"))
