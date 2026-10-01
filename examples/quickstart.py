"""Evaluate a Jev-compatible model served at a System One endpoint.

    python examples/quickstart.py http://127.0.0.1:8000/v1/systemone open-jev
"""

import sys

import jevbench as jb

url, model_name = sys.argv[1], sys.argv[2]
model = jb.systemone(url, model=model_name)            # several replicas: "http://a/...,http://b/..."

print(jb.estimate(domains=["finance_ops"]))             # requests the run below will send

report = jb.evaluate(model, domains=["finance_ops"], concurrency=16, progress=True)
print(report.table("dimension"))
print(report.table("group"))
report.save(f"runs/{model_name}-finance_ops.json")
report.radar(f"runs/{model_name}-finance_ops.svg")
