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
have visiter || { echo "visiter not on PATH" >&2; exit 2; }
have dot     || { echo "graphviz (dot) not on PATH" >&2; exit 2; }

# --- tutorial ---

# simplest — auto-derived labels ("x // 3", "x + 2"), no manual labels.
visiter iterate '[1],
  [Rule(lambda x: x%3==0, Op(lambda x: x//3))],
  default=Op(lambda x: x+2)' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/simplest.svg"

# custom_labels — same iteration, explicit short labels.
visiter iterate '[1],
  [Rule(lambda x: x%3==0, Op(lambda x: x//3, "÷3"))],
  default=Op(lambda x: x+2, "+2")' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/custom_labels.svg"

# default_op — default fires when no rule matches (4→2→1→2 cycle via +1).
visiter iterate '[4],
  [Rule(lambda x: x%2==0, Op(lambda x: x//2))],
  default=Op(lambda x: x+1)' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/default_op.svg"

# default_none — no rule, no default → the value is a leaf (1 is white).
visiter iterate '[4],
  [Rule(lambda x: x%2==0, Op(lambda x: x//2))],
  default=None' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/default_none.svg"

# bound_ghost — Rule.bound → pseudo-edge → dashed ghost stub at the ceiling.
visiter iterate '[1],
  [Rule(lambda x: True, Op(lambda x: 2*x), bound=lambda x: 2*x<=8)],
  default=None' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/bound_ghost.svg"

# fan_in — two paths enter the same node (3 is reached from 1 via +2
# and from 9 via //3).
visiter iterate '[1, 9],
  [Rule(lambda x: x%3==0, Op(lambda x: x//3))],
  default=Op(lambda x: x+2)' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/fan_in.svg"

# crop_forward / crop_backward — same graph, same anchor, two directions.
# Reused by both the tutorial ("how do I show only a slice?") and the
# manual ("direction + cycle").
visiter iterate 'range(1, 30),
  [Rule(lambda x: x%3==0, Op(lambda x: x//3))],
  default=Op(lambda x: x+2)' > /tmp/visiter_crop.json
visiter to-dot 'anchor=1, radius=8, direction="forward"'  --input /tmp/visiter_crop.json | dot -Tsvg > "$OUT/crop_forward.svg"
visiter to-dot 'anchor=1, radius=8, direction="backward"' --input /tmp/visiter_crop.json | dot -Tsvg > "$OUT/crop_backward.svg"
rm -f /tmp/visiter_crop.json

# node_styles — one graph covering every vocabulary element AND showing
# wedge-grade 2, 3, and 4 with *mixed* highlight (so wedged pies appear
# both highlighted and not). Reused by tutorial and manual.
#   roots (bold): 6, 12, 24
#   leaf (white): 1
#   solid fill:   2, 3
#   2-wedge:      4 (highlighted), 8
#   3-wedge:      6
#   4-wedge:      12 (highlighted, root), 24 (root)
visiter iterate '[6, 12, 24],
  [Rule(lambda x: x>1 and x%2==0, Op(lambda x: x//2, "÷2")),
   Rule(lambda x: x>1 and x%3==0, Op(lambda x: x//3, "÷3")),
   Rule(lambda x: x>1 and x%4==0, Op(lambda x: x//4, "÷4")),
   Rule(lambda x: x>1 and x%6==0, Op(lambda x: x//6, "÷6"))],
  default=None,
  tags={"highlight": lambda x: x in (4, 12)}' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/node_styles.svg"

# strings — non-numeric values. Drop the trailing character while it is
# a vowel; words ending in a consonant are leaves.
visiter iterate '["banana", "garage", "queue"],
  [Rule(lambda s: len(s) > 0 and s[-1] in set("aeiou"),
        Op(lambda s: s[:-1], "drop-vowel"))],
  default=None' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/strings.svg"

# dashed_arrows — pseudo-edge (bound) and a cropped incoming boundary
# edge, rendered with the same dashed stub vocabulary.
visiter iterate '[1, 5],
  [Rule(lambda x: True, Op(lambda x: 2*x, "×2"), bound=lambda x: 2*x<=8)],
  default=None' > /tmp/visiter_dashed.json
visiter to-dot 'anchor=2, radius=2, direction="both"' --input /tmp/visiter_dashed.json | dot -Tsvg > "$OUT/dashed_arrows.svg"
rm -f /tmp/visiter_dashed.json

# --- manual: iterate examples (§2) ---

# iterate_descent — descent example, rendered (forward ref to §3).
visiter iterate 'range(1, 30),
  [Rule(lambda x: x%3==0, Op(lambda x: x//3))],
  default=Op(lambda x: x+2)' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/iterate_descent.svg"

# iterate_reverse_binary — reverse binary tree with ceiling + max_depth.
visiter iterate '[1],
  [Rule(lambda x: True, Op(lambda x: 2*x, "×2"), bound=lambda x: 2*x<=64),
   Rule(lambda x: True, Op(lambda x: 2*x+1, "×2+1"), bound=lambda x: 2*x+1<=64)],
  default=None,
  max_depth=5' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/iterate_reverse_binary.svg"

# iterate_multiway — conjunctive rules with highlight on powers of two.
visiter iterate 'range(1, 30),
  [Rule(lambda x: x%15==0, Op(lambda x: x//15, "÷15")),
   Rule(lambda x: x%3==0 and x%15!=0, Op(lambda x: x//3, "÷3")),
   Rule(lambda x: x%5==0 and x%15!=0, Op(lambda x: x//5, "÷5"))],
  default=Op(lambda x: x+1),
  tags={"highlight": lambda x: x>0 and (x & (x-1))==0}' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/iterate_multiway.svg"

# --- manual: coloring model (§3) — one minimal SVG per bullet point ---

# coloring_palette — two ops ⇒ two palette slots. Fill is light, edge
# is the saturated mid-tone of the same slot.
visiter iterate '[1],
  [Rule(lambda x: x%2==0, Op(lambda x: x//2, "a"))],
  default=Op(lambda x: x+1, "b")' > /tmp/visiter_cpal.json
visiter to-dot '' --input /tmp/visiter_cpal.json | dot -Tsvg > "$OUT/coloring_palette.svg"
rm -f /tmp/visiter_cpal.json

# coloring_node_fill — leaf (white) / solid (one op) / wedged (two ops)
# on one tiny graph.
visiter iterate '[4],
  [Rule(lambda x: x%2==0 and x>1, Op(lambda x: x//2, "a")),
   Rule(lambda x: x%2==0 and x>1, Op(lambda x: x-2, "b"))],
  default=None' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/coloring_node_fill.svg"

# coloring_highlight — same op fires from two nodes; only one carries
# the "highlight" tag, so the fill is darkened and the font becomes
# white for contrast.
visiter iterate '[2, 3],
  [Rule(lambda x: True, Op(lambda x: x+1, "+1"), bound=lambda x: x+1<=4)],
  default=None,
  tags={"highlight": lambda x: x==2}' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/coloring_highlight.svg"

# coloring_roots — one root (bold border) next to one non-root.
visiter iterate '[3],
  [Rule(lambda x: x>0, Op(lambda x: x-1, "-1"))],
  default=None' \
  | visiter to-dot '' | dot -Tsvg > "$OUT/coloring_roots.svg"

# --- manual: to_dot examples (§3) ---

# example_show_factors — reverse binary tree with prime-factor
# annotations toggled on.
visiter iterate '[1],
  [Rule(lambda x: True, Op(lambda x: 2*x, "×2"), bound=lambda x: 2*x<=32),
   Rule(lambda x: True, Op(lambda x: 2*x+1, "×2+1"), bound=lambda x: 2*x+1<=32)],
  default=None,
  max_depth=4' \
  | visiter to-dot 'show_factors=True' | dot -Tsvg > "$OUT/example_show_factors.svg"

# example_pinned_colors — same descent, but ÷3 and +2 pinned to
# explicit colors that override the palette.
visiter iterate '[1, 5, 7],
  [Rule(lambda x: x%3==0, Op(lambda x: x//3, "÷3"))],
  default=Op(lambda x: x+2, "+2")' \
  | visiter to-dot 'op_colors={"÷3": ("#ccddff", "#6688bb"), "+2": "#cc4422"}' \
  | dot -Tsvg > "$OUT/example_pinned_colors.svg"

# --- manual: recipe — depth-gradient coloring (§5) ---

python3 - > /tmp/visiter_gradient.dot <<'PY'
from visiter import iterate, Op, Rule, darken
import graphviz

graph = iterate(
    start=[1],
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
    default=Op(lambda x: x + 2, "+2"),
    max_depth=6,
)
max_d = max(info["depth"] for info in graph["nodes"].values()) or 1
base = "#ffccaa"
roots = {str(v) for v in graph["roots"]}

dot = graphviz.Digraph()
dot.attr(rankdir="TB")
dot.attr("node", fontsize="11", shape="ellipse", style="filled")
dot.attr("edge", fontsize="9")
for k, info in graph["nodes"].items():
    factor = 1.0 - (info["depth"] / max_d) * 0.55
    dot.node(
        f"n{k}",
        label=k,
        fillcolor=darken(base, factor),
        penwidth="3" if k in roots else "1",
    )
for e in graph["edges"]:
    dot.edge(f"n{e['from']}", f"n{e['to']}", label=f" {e['op']} ")
print(dot.source)
PY
dot -Tsvg < /tmp/visiter_gradient.dot > "$OUT/depth_gradient.svg"
rm -f /tmp/visiter_gradient.dot

echo "Regenerated $(ls "$OUT"/*.svg | wc -l | tr -d ' ') SVGs in $OUT/"
