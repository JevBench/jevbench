"""Test your own model: any function (state, questions) -> answers in the System One wire format.

A Noul answer is {"noul": p}; a Choice or Score answer is {"probabilities": {option: p, ...}}
(Score options are the level indices "0", "1", ...).
"""

import jevbench as jb


def uniform(state, questions):
    out = {}
    for key, q in questions.items():
        if q["type"] == "noul":
            out[key] = {"type": "noul", "noul": 0.5}
        else:
            options = list(q["criteria"]) if q["type"] == "choice" else [str(i) for i in range(len(q["criteria"]))]
            out[key] = {"type": q["type"], "probabilities": {o: 1 / len(options) for o in options}}
    return out


report = jb.evaluate(jb.from_callable(uniform, name="uniform", concurrent=True), domains=["finance_ops"])
print(report.table("relation"))
