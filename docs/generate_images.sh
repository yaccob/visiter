#!/usr/bin/env bash
# Regenerate all SVGs embedded in tutorial.md and manual.md.
# Each image illustrates exactly one teaching point — no more, no less.
# Re-run this script after any change that would affect what those
# points should look like (renderer defaults, color palette, etc.).

set -euo pipefail
cd "$(dirname "$0")"
mkdir -p images
OUT=images

have() { command -v "$1" >/dev/null 2>&1; }
have viter || { echo "viter not on PATH" >&2; exit 2; }
have dot   || { echo "graphviz (dot) not on PATH" >&2; exit 2; }

# run_vit OUT_FILE <<VIT … VIT
# Run a .vit script (stdin) via viter and write stdout to OUT_FILE.
run_vit() {
    local out="$1"
    local tmp
    tmp=$(mktemp -t visiter_img.XXXXXX.vit)
    cat > "$tmp"
    viter "$tmp" > "$out"
    rm -f "$tmp"
}

# --- README quickstart ---

run_vit "$OUT/readme_quickstart.svg" <<'VIT'
(viter(range(1, 10))
 .case(lambda x: x % 3 == 0, lambda x: x // 3)
 .default(lambda x: x + 2)
 .render())
VIT

# --- tutorial ---

# simplest — auto-derived labels ("x // 3", "x + 2"), no manual labels.
run_vit "$OUT/simplest.svg" <<'VIT'
(viter([1])
 .case(lambda x: x % 3 == 0, lambda x: x // 3)
 .default(lambda x: x + 2)
 .render())
VIT

# custom_labels — same iteration, explicit short labels.
run_vit "$OUT/custom_labels.svg" <<'VIT'
(viter([1])
 .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
 .default(lambda x: x + 2, label="+2")
 .render())
VIT

# default_op — default fires when no case matches (4→2→1→2 cycle via +1).
run_vit "$OUT/default_op.svg" <<'VIT'
(viter([4])
 .case(lambda x: x % 2 == 0, lambda x: x // 2)
 .default(lambda x: x + 1)
 .render())
VIT

# default_none — no case, no default → the value is a leaf (1 is white).
run_vit "$OUT/default_none.svg" <<'VIT'
(viter([4])
 .case(lambda x: x % 2 == 0, lambda x: x // 2)
 .render())
VIT

# bound_ghost — case bound=False → pseudo-edge → dashed ghost stub at the ceiling.
run_vit "$OUT/bound_ghost.svg" <<'VIT'
(viter([1])
 .case(lambda x: True, lambda x: 2 * x, bound=lambda x: 2 * x <= 8)
 .render())
VIT

# fan_in — two paths enter the same node (3 is reached from 1 via +2
# and from 9 via //3).
run_vit "$OUT/fan_in.svg" <<'VIT'
(viter([1, 9])
 .case(lambda x: x % 3 == 0, lambda x: x // 3)
 .default(lambda x: x + 2)
 .render())
VIT

# crop_forward / crop_backward — same graph, same anchor, two directions.
# Reused by both the tutorial ("how do I show only a slice?") and the
# manual ("direction + cycle").
run_vit "$OUT/crop_forward.svg" <<'VIT'
(viter(range(1, 30))
 .case(lambda x: x % 3 == 0, lambda x: x // 3)
 .default(lambda x: x + 2)
 .build()
 .to_dot(anchor=1, radius=8, direction="forward")
 .render())
VIT

run_vit "$OUT/crop_backward.svg" <<'VIT'
(viter(range(1, 30))
 .case(lambda x: x % 3 == 0, lambda x: x // 3)
 .default(lambda x: x + 2)
 .build()
 .to_dot(anchor=1, radius=8, direction="backward")
 .render())
VIT

# node_styles — one graph covering every vocabulary element AND showing
# wedge-grade 2, 3, and 4 with *mixed* highlight (so wedged pies appear
# both highlighted and not). Reused by tutorial and manual.
run_vit "$OUT/node_styles.svg" <<'VIT'
(viter([6, 12, 24], tags={"highlight": lambda x: x in (4, 12)})
 .case(lambda x: x > 1 and x % 2 == 0, lambda x: x // 2, label="÷2")
 .case(lambda x: x > 1 and x % 3 == 0, lambda x: x // 3, label="÷3")
 .case(lambda x: x > 1 and x % 4 == 0, lambda x: x // 4, label="÷4")
 .case(lambda x: x > 1 and x % 6 == 0, lambda x: x // 6, label="÷6")
 .render())
VIT

# strings — non-numeric values. Drop the trailing character while it is
# a vowel; words ending in a consonant are leaves.
run_vit "$OUT/strings.svg" <<'VIT'
(viter(["banana", "garage", "queue"])
 .case(lambda s: len(s) > 0 and s[-1] in set("aeiou"),
       lambda s: s[:-1], label="drop-vowel")
 .render())
VIT

# dashed_arrows — pseudo-edge (bound) and a cropped incoming boundary
# edge, rendered with the same dashed stub vocabulary.
run_vit "$OUT/dashed_arrows.svg" <<'VIT'
(viter([1, 5])
 .case(lambda x: True, lambda x: 2 * x, label="×2",
       bound=lambda x: 2 * x <= 8)
 .build()
 .to_dot(anchor=2, radius=2, direction="both")
 .render())
VIT

# --- manual: build examples (§2) ---

# iterate_descent — descent example, rendered (forward ref to §3).
run_vit "$OUT/iterate_descent.svg" <<'VIT'
(viter(range(1, 30))
 .case(lambda x: x % 3 == 0, lambda x: x // 3)
 .default(lambda x: x + 2)
 .render())
VIT

# iterate_reverse_binary — reverse binary tree with ceiling + max_depth.
run_vit "$OUT/iterate_reverse_binary.svg" <<'VIT'
(viter([1], max_depth=5)
 .case(lambda x: True, lambda x: 2 * x, label="×2",
       bound=lambda x: 2 * x <= 64)
 .case(lambda x: True, lambda x: 2 * x + 1, label="×2+1",
       bound=lambda x: 2 * x + 1 <= 64)
 .render())
VIT

# iterate_multiway — conjunctive cases with highlight on powers of two.
run_vit "$OUT/iterate_multiway.svg" <<'VIT'
(viter(range(1, 30),
       tags={"highlight": lambda x: x > 0 and (x & (x - 1)) == 0})
 .case(lambda x: x % 15 == 0, lambda x: x // 15, label="÷15")
 .case(lambda x: x % 3 == 0 and x % 15 != 0, lambda x: x // 3, label="÷3")
 .case(lambda x: x % 5 == 0 and x % 15 != 0, lambda x: x // 5, label="÷5")
 .default(lambda x: x + 1)
 .render())
VIT

# --- manual: coloring model (§3) — one minimal SVG per bullet point ---

# coloring_palette — two ops ⇒ two palette slots.
run_vit "$OUT/coloring_palette.svg" <<'VIT'
(viter([1])
 .case(lambda x: x % 2 == 0, lambda x: x // 2, label="a")
 .default(lambda x: x + 1, label="b")
 .render())
VIT

# coloring_node_fill — leaf (white) / solid (one op) / wedged (two ops).
run_vit "$OUT/coloring_node_fill.svg" <<'VIT'
(viter([4])
 .case(lambda x: x % 2 == 0 and x > 1, lambda x: x // 2, label="a")
 .case(lambda x: x % 2 == 0 and x > 1, lambda x: x - 2, label="b")
 .render())
VIT

# coloring_highlight — same op, one node tagged → darkened fill.
run_vit "$OUT/coloring_highlight.svg" <<'VIT'
(viter([2, 3], tags={"highlight": lambda x: x == 2})
 .case(lambda x: True, lambda x: x + 1, label="+1",
       bound=lambda x: x + 1 <= 4)
 .render())
VIT

# coloring_roots — one root (bold border) next to one non-root.
run_vit "$OUT/coloring_roots.svg" <<'VIT'
(viter([3])
 .case(lambda x: x > 0, lambda x: x - 1, label="-1")
 .render())
VIT

# --- manual: to_dot examples (§3) ---

# example_show_factors — reverse binary tree with prime-factor annotations.
run_vit "$OUT/example_show_factors.svg" <<'VIT'
(viter([1], max_depth=4)
 .case(lambda x: True, lambda x: 2 * x, label="×2",
       bound=lambda x: 2 * x <= 32)
 .case(lambda x: True, lambda x: 2 * x + 1, label="×2+1",
       bound=lambda x: 2 * x + 1 <= 32)
 .build()
 .to_dot(show_factors=True)
 .render())
VIT

# example_pinned_colors — descent with explicit ids + op_colors pin.
run_vit "$OUT/example_pinned_colors.svg" <<'VIT'
(viter([1, 5, 7])
 .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3", id="div3")
 .default(lambda x: x + 2, label="+2", id="inc2")
 .build()
 .to_dot(op_colors={
     "div3": ("#ccddff", "#6688bb"),
     "inc2": "#ffdddd",
 })
 .render())
VIT

# --- manual: recipe — depth-gradient coloring (§5) ---

run_vit "$OUT/depth_gradient.svg" <<'VIT'
import graphviz
from visiter import darken

graph = (viter([1], max_depth=6)
         .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
         .default(lambda x: x + 2, label="+2")
         .build())
max_d = max(info["depth"] for info in graph["nodes"].values()) or 1
base = "#ffccaa"
roots = {str(v) for v in graph["roots"]}

dot = graphviz.Digraph(format="svg")
dot.attr(rankdir="TB")
dot.attr("node", fontsize="11", shape="ellipse", style="filled")
dot.attr("edge", fontsize="9")
for k, info in graph["nodes"].items():
    factor = 1.0 - (info["depth"] / max_d) * 0.55
    dot.node(f"n{k}", label=k,
             fillcolor=darken(base, factor),
             penwidth="3" if k in roots else "1")
for e in graph["edges"]:
    dot.edge(f"n{e['from']}", f"n{e['to']}", label=f" {e['op']} ")
import sys
sys.stdout.write(dot.pipe().decode("utf-8"))
VIT

# --- manual: recipe — custom key_type with Fraction (§5) ---

run_vit "$OUT/golden_ratio_convergents.svg" <<'VIT'
(viter([Fraction(1)], max_depth=7, key_type="number")
 .case(lambda x: True, lambda x: 1 + 1 / x, label="1 + 1/x")
 .render())
VIT

# --- manual: §7 NetworkX — water jug example ---
# Two SVGs: full reachability graph (target states highlighted) and
# shortest-path subgraph (solution). Mirrors the water_jugs demo.

run_vit "$OUT/water_jugs_full.svg" <<'VIT'
A, B, T = 3, 5, 4
(viter([(0, 0)],
       max_depth=None, max_nodes=None,
       tags={"highlight": lambda s: s[0] == T or s[1] == T})
 .case(lambda s: s[0] < A, lambda s: (A, s[1]),       label=f"fill {A}L")
 .case(lambda s: s[1] < B, lambda s: (s[0], B),       label=f"fill {B}L")
 .case(lambda s: s[0] > 0, lambda s: (0, s[1]),       label=f"empty {A}L")
 .case(lambda s: s[1] > 0, lambda s: (s[0], 0),       label=f"empty {B}L")
 .case(lambda s: s[0] > 0 and s[1] < B,
       lambda s: (max(0, s[0]-(B-s[1])), min(B, s[0]+s[1])),
       label=f"{A}L→{B}L")
 .case(lambda s: s[1] > 0 and s[0] < A,
       lambda s: (min(A, s[0]+s[1]), max(0, s[1]-(A-s[0]))),
       label=f"{B}L→{A}L")
 .render())
VIT

run_vit "$OUT/water_jugs_path.svg" <<'VIT'
import networkx as nx
from visiter.analytics import to_networkx, from_networkx

A, B, T = 3, 5, 4
g = (viter([(0, 0)],
           max_depth=None, max_nodes=None,
           tags={"highlight": lambda s: s[0] == T or s[1] == T})
     .case(lambda s: s[0] < A, lambda s: (A, s[1]),       label=f"fill {A}L")
     .case(lambda s: s[1] < B, lambda s: (s[0], B),       label=f"fill {B}L")
     .case(lambda s: s[0] > 0, lambda s: (0, s[1]),       label=f"empty {A}L")
     .case(lambda s: s[1] > 0, lambda s: (s[0], 0),       label=f"empty {B}L")
     .case(lambda s: s[0] > 0 and s[1] < B,
           lambda s: (max(0, s[0]-(B-s[1])), min(B, s[0]+s[1])),
           label=f"{A}L→{B}L")
     .case(lambda s: s[1] > 0 and s[0] < A,
           lambda s: (min(A, s[0]+s[1]), max(0, s[1]-(A-s[0]))),
           label=f"{B}L→{A}L")
     .build())

nxg = to_networkx(g)
source = "(0, 0)"
goals = [n for n in nxg.nodes
         if any(int(x) == T for x in n.strip("()").split(", "))]
best = None
edges_keep = set()
goal_nodes = set()
for goal in goals:
    if not nx.has_path(nxg, source, goal):
        continue
    for path in nx.all_shortest_paths(nxg, source, goal):
        plen = len(path)
        if best is not None and plen > best:
            continue
        if best is None or plen < best:
            best = plen
            edges_keep.clear()
            goal_nodes.clear()
        goal_nodes.add(path[-1])
        for i in range(len(path) - 1):
            edges_keep.add((path[i], path[i + 1]))

sub = nxg.edge_subgraph(edges_keep).copy()
for n in goal_nodes:
    tags = list(sub.nodes[n].get("tags", []))
    if "highlight" not in tags:
        tags.append("highlight")
    sub.nodes[n]["tags"] = tags

Graph(from_networkx(sub)).to_dot().render()
VIT

echo "Regenerated $(ls "$OUT"/*.svg | wc -l | tr -d ' ') SVGs in $OUT/"
