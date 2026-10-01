"""Evaluate one served model on a bundled suite through the installed package's public API.

    python bench/evaluate.py --url http://127.0.0.1:8001/v1/systemone,http://127.0.0.1:8002/v1/systemone \
        --model open-jev --suite jevbench-mini --name open-jev-9b --out runs/jevbench-mini/open-jev-9b.json

Uses only the public API of `jevbench` as installed (pip install jevbench).
"""

import argparse
import sys
import time

import jevbench as jb

p = argparse.ArgumentParser()
p.add_argument("--url", required=True, help="the model's System One endpoint; comma-separated replicas")
p.add_argument("--model", required=True, help='the "model" field the server expects')
p.add_argument("--suite", default="jevbench-mini")
p.add_argument("--name", required=True)
p.add_argument("--out", required=True)
p.add_argument("--cache-dir", default=".jevbench-cache")
args = p.parse_args()

print(f"== jevbench {jb.__version__} from {jb.__file__}", flush=True)
model = jb.systemone(args.url, model=args.model)
print(f"== {args.name}: {model.replicas} replica(s); suite {args.suite}: {jb.estimate(args.suite)}", flush=True)
t0 = time.time()
report = jb.evaluate(model, suite=args.suite, name=args.name, cache=args.cache_dir, progress=True)
print(report.table("dimension"))
print(report.table("group"))
res = report.result
print(f"== {args.name}: {res['requests']} requests, {res['cache_hits']} from cache, "
      f"{time.time() - t0:.0f}s, {len(report.errors)} errors", flush=True)
print(f"wrote {report.save(args.out)}")
if res.get("backend_down"):
    print(f"== {args.name}: STOPPED, the model server is down: {res['backend_down']}", flush=True)
sys.exit(1 if report.errors or res.get("backend_down") else 0)
