"""Text tables and dependency-free SVG radars of scores and coherence cards."""

from __future__ import annotations

import html
import math
from statistics import mean

from jevbench import taxonomy
from jevbench.relations import REGISTRY


# ------------------------------------------------------------------ score tables

def _pct(v):
    return "-" if v is None else f"{100 * v:.1f}"


def format_scores(named: dict[str, dict], level: str = "group") -> str:
    """Side-by-side scores: level "dimension" (dimensions only), "group" (and their groups) or "relation"."""
    if not named:
        raise ValueError("no reports to compare")
    names = list(named)
    w = max(16, *(len(n) + 2 for n in names))
    lines = [f"{'':<36}" + "".join(f"{n:>{w}}" for n in names)]

    def row(label, values):
        lines.append(f"{label:<36}" + "".join(f"{v:>{w}}" for v in values))

    def with_ci(v, ci):
        return _pct(v) + (f" [{100 * ci[0]:.0f}-{100 * ci[1]:.0f}]" if ci else "")

    row("OVERALL, dimensions weighted", [with_ci(s["overall"], s["ci"].get("overall")) for s in named.values()])
    row("OVERALL, graded (dimensions)", [with_ci(s["graded"]["overall"], s["ci"].get("graded_overall"))
                                      for s in named.values()])
    for p in taxonomy.PILLARS:
        row(f"{p.id} {p.title}", [_pct(s["pillars"][p.id]) for s in named.values()])
        for g in taxonomy.GROUPS:
            if g.pillar != p.id or level == "dimension":
                continue
            row(f"  {g.id} {g.title}", [_pct(s["groups"][g.id]) for s in named.values()])
            if level == "relation":
                for e in taxonomy.IMPLEMENTED:
                    if e.group == g.id:
                        row(f"    {e.name}", [_pct(s["relations"].get(e.name)) for s in named.values()])
    row("mean repeat noise (TV)", ["-" if s["mean_repeat_noise"] is None else f"{s['mean_repeat_noise']:.3f}"
                                   for s in named.values()])
    row("cases / scored relations", [f"{s['n_cases']} / {s['n_checks']}" for s in named.values()])
    first = next(iter(named.values()))
    lines.append(f"scores in %, 100 = no violation; tolerance {first['tolerance']}; brackets: 95% bootstrap "
                 f"interval over cases ({first['bootstrap']} draws)")
    low = sorted({c for s in named.values() for c in s["excluded"]["low_n"]})
    for kind, label in (("exploratory", "exploratory"), ("diagnostic", "diagnostics")):
        found = sorted({c for s in named.values() for c in s["excluded"].get(kind, [])})
        if found:
            lines.append(f"{label}, not in the means: " + ", ".join(
                f"{c} ({' / '.join(_pct(s['checks'][c]['score']) if c in s['checks'] else '-' for s in named.values())})"
                for c in found))
    if low:
        lines.append(f"fewer than {first['min_n']} tests for some model, not in its means: " + ", ".join(low))
    return "\n".join(lines)


# ------------------------------------------------------------------ SVG radars

PALETTE = ("#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#be185d", "#4d7c0f",
           "#a16207", "#475569", "#e11d48", "#0d9488")


def _axes(level):
    return ([(g.id, g.title) for g in taxonomy.GROUPS] if level == "group"
            else [(p.id, p.title) for p in taxonomy.PILLARS])


def _values(s, level, metric):
    src = s["graded"] if metric == "graded" else s
    return src["groups"] if level == "group" else src["pillars"]


def _overall(s, metric):
    return s["graded"]["overall"] if metric == "graded" else s["overall"]


def _radar(out, named, axes, level, metric, cx, cy, r, font, labels=True, colors=None):
    n = len(axes)

    def point(i, v):
        a = -math.pi / 2 + 2 * math.pi * i / n
        return cx + r * v * math.cos(a), cy + r * v * math.sin(a)

    for ring in (0.2, 0.4, 0.6, 0.8, 1.0):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (point(i, ring) for i in range(n)))
        out.append(f'<polygon points="{pts}" fill="none" stroke="#d4d4d8" stroke-width="1"/>')
    x, y = point(0, 1.0)
    out.append(f'<text x="{x + 3:.1f}" y="{y + 3:.1f}" font-size="{font - 2}" fill="#71717a">100</text>')
    for i, (aid, label) in enumerate(axes):
        x, y = point(i, 1.0)
        out.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#d4d4d8" stroke-width="1"/>')
        if labels:
            lx, ly = point(i, 1.14)
            anchor = "middle" if abs(lx - cx) < r * 0.1 else ("start" if lx > cx else "end")
            out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="{font}">'
                       f'<tspan font-weight="bold">{html.escape(aid)}</tspan>'
                       f'<tspan x="{lx:.1f}" dy="{font + 2}" fill="#52525b">{html.escape(label)}</tspan></text>')
        else:
            lx, ly = point(i, 1.1)
            anchor = "middle" if abs(lx - cx) < r * 0.1 else ("start" if lx > cx else "end")
            out.append(f'<text x="{lx:.1f}" y="{ly + 3:.1f}" text-anchor="{anchor}" font-size="{font}" '
                       f'fill="#52525b">{html.escape(aid.split(".")[-1])}</text>')
    for k, (name, s) in enumerate(named.items()):
        color = (colors or {}).get(name, PALETTE[k % len(PALETTE)])
        vals = [_values(s, level, metric)[aid] for aid, _ in axes]
        pts = [point(i, v) for i, v in enumerate(vals) if v is not None]
        if len(pts) >= 3:
            poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            out.append(f'<polygon points="{poly}" fill="{color}" fill-opacity="0.12" stroke="{color}" '
                       f'stroke-width="2"/>')
        for i, v in enumerate(vals):
            if v is not None:
                x, y = point(i, v)
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{2.5 if not labels else 3}" fill="{color}"/>')


def _svg(width, height, body):
    return "\n".join([f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                      f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">',
                      '<rect width="100%" height="100%" fill="#ffffff"/>', *body, "</svg>"])


def radar_svg(named: dict[str, dict], level: str = "group", title: str = "JevBench coherence",
              metric: str = "binary") -> str:
    """One radar with every model overlaid; legend above the chart."""
    size, cx, r = 720, 360, 230
    legend_h = 22 * len(named)
    cy = 110 + legend_h + r + 40
    out = [f'<text x="{cx}" y="36" text-anchor="middle" font-size="20" font-weight="bold">{html.escape(title)}</text>']
    for k, (name, s) in enumerate(named.items()):
        ly = 56 + 22 * k
        out.append(f'<rect x="40" y="{ly}" width="14" height="14" fill="{PALETTE[k % len(PALETTE)]}"/>')
        out.append(f'<text x="62" y="{ly + 12}" font-size="13">{html.escape(name)}: overall '
                   f'{_pct(_overall(s, metric))} ({html.escape(s["tolerance"])}, {metric})</text>')
    _radar(out, named, _axes(level), level, metric, cx, cy, r, 11)
    return _svg(size, cy + r + 90, out)


def radar_grid_svg(named: dict[str, dict], level: str = "group", title: str = "JevBench coherence by model",
                   metric: str = "binary", cols: int = 4, family: dict | None = None) -> str:
    """Small multiples: one radar per model, same axes and scale; optional family label per model."""
    cell, r = 300, 92
    rows = math.ceil(len(named) / cols)
    width, height = cols * cell, 70 + rows * (cell + 20) + 40
    out = [f'<text x="{width / 2}" y="34" text-anchor="middle" font-size="20" font-weight="bold">'
           f'{html.escape(title)}</text>',
           f'<text x="{width / 2}" y="56" text-anchor="middle" font-size="12" fill="#52525b">'
           f'{html.escape(level)} scores, {html.escape(next(iter(named.values()))["tolerance"])}, {metric}; '
           f'axis order as in the taxonomy, starting at the top, clockwise</text>']
    colors = {}
    fams = sorted({(family or {}).get(n, "") for n in named} - {""})
    for i, (name, s) in enumerate(named.items()):
        col, row = i % cols, i // cols
        x0, y0 = col * cell, 70 + row * (cell + 20)
        fam = (family or {}).get(name, "")
        color = PALETTE[fams.index(fam) % len(PALETTE)] if fam in fams else PALETTE[0]
        colors[name] = color
        out.append(f'<text x="{x0 + cell / 2}" y="{y0 + 18}" text-anchor="middle" font-size="14" '
                   f'font-weight="bold">{html.escape(name)}</text>')
        sub = f"overall {_pct(_overall(s, metric))}" + (f" · {fam}" if fam else "")
        out.append(f'<text x="{x0 + cell / 2}" y="{y0 + 34}" text-anchor="middle" font-size="11" '
                   f'fill="#52525b">{html.escape(sub)}</text>')
        _radar(out, {name: s}, _axes(level), level, metric, x0 + cell / 2, y0 + 50 + cell / 2 - 20, r, 9,
               labels=False, colors=colors)
    return _svg(width, height, out)


# ------------------------------------------------------------------ coherence card

def format_card(result: dict, tolerance="fixed", fixed: float = 0.05) -> str:
    from jevbench.results import card

    rows = card(result, tolerance=tolerance, fixed=fixed)
    head = (f"JevBench {result['jevbench_version']}  backend={result['backend']}  cases={len(result['cases'])}  "
            f"requests={result['requests']} (+{result['cache_hits']} cached)  seed={result['seed']}")
    if result.get("truncated_by_budget"):
        head += "  [TRUNCATED BY BUDGET]"
    noise = [v for b in result["bases"].values() for v in b["noise"].values()]
    lines = [head, f"repeat-noise TV: mean {mean(noise):.3f}, max {max(noise):.3f}" if noise else "",
             f"{'group':<17}{'relation / check':<44}{'n':>5}{'viol%':>7}{'95% CI':>15}{'mean dev':>10}"
             f"{'flip%':>7}{'no-batch%':>10}"]
    for r in rows:
        lo, hi = r["violation_rate_95ci"]
        flip = f"{100 * r['flip_rate']:.0f}" if r["flip_rate"] is not None else "-"
        pers = f"{100 * r['persists_without_batch_rate']:.0f}" if r["persists_without_batch_rate"] is not None else "-"
        lines.append(f"{r['group']:<17}{r['relation'] + ' / ' + r['check']:<44}{r['n']:>5}"
                     f"{100 * r['violation_rate']:>7.1f}  [{100 * lo:>4.1f},{100 * hi:>5.1f}]"
                     f"{r['mean_deviation']:>10.3f}{flip:>7}{pers:>10}")
        if r["by_variant"] and REGISTRY[r["relation"]].templates:
            parts = "  ".join(f"t{v}: {100 * x['violation_rate']:.0f}% (n={x['n']})" for v, x in r["by_variant"].items())
            lines.append(f"{'':<17}  by template  {parts}")
    if result["errors"]:
        lines.append(f"{len(result['errors'])} errors (see JSON)")
    return "\n".join(line for line in lines if line is not None)
