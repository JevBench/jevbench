"""The README figure: every model's five dimension scores on jevbench-mini.

    python bench/analysis/readme_figure.py --data ../JevBench.github.io/data --out docs/assets/dimensions.png

Reads the leaderboard and model table written by site_data.py (the website's data/ directory).
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

NAVY, CORAL = "#16213A", "#E8603F"
DIMS = [("REP", "Representation"), ("BAT", "Batch"), ("MEA", "Probability\nmeasure"), ("LOG", "Logical\norder"),
        ("CHO", "Choice set")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../JevBench.github.io/data")
    ap.add_argument("--out", default="docs/assets/dimensions.png")
    args = ap.parse_args()
    lb = json.loads((Path(args.data) / "leaderboard.json").read_text())
    facts = json.loads((Path(args.data) / "models.json").read_text())
    rows = lb["models"]
    M = np.array([[100 * r["dimensions"][d] for d, _ in DIMS] for r in rows])

    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
                         "text.color": NAVY, "xtick.color": NAVY, "ytick.color": NAVY})
    fig, ax = plt.subplots(figsize=(7.6, 6.4), dpi=220)
    ax.imshow(M, cmap="viridis", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(DIMS)), [f"{d}\n{t}" for d, t in DIMS], fontsize=10.5)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(rows)), [facts[r["model"]]["display"] for r in rows], fontsize=9.5)
    ax.tick_params(length=0, pad=5)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=9.5,
                    color="white" if v < 55 else NAVY, fontweight="bold" if DIMS[j][0] == "MEA" else "normal")
    mea = [d for d, _ in DIMS].index("MEA")
    ax.add_patch(plt.Rectangle((mea - 0.5, -0.5), 1, len(rows), fill=False, ec=CORAL, lw=3, zorder=5))
    for s in ax.spines.values():
        s.set_visible(False)
    fig.tight_layout(pad=0.4)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor="white")
    print("wrote", out)


if __name__ == "__main__":
    main()
