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

# --- README quickstart ---

visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/readme_quickstart.svg"
range(1, 10),
[Rule(lambda x: x%3==0, Op(lambda x: x//3))],
Op(lambda x: x+2)
VIT

# --- tutorial ---

# simplest — auto-derived labels ("x // 3", "x + 2"), no manual labels.
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/simplest.svg"
[1],
[Rule(lambda x: x%3==0, Op(lambda x: x//3))],
Op(lambda x: x+2)
VIT

# custom_labels — same iteration, explicit short labels.
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/custom_labels.svg"
[1],
[Rule(lambda x: x%3==0, Op(lambda x: x//3, label="÷3"))],
Op(lambda x: x+2, label="+2")
VIT

# default_op — default fires when no rule matches (4→2→1→2 cycle via +1).
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/default_op.svg"
[4],
[Rule(lambda x: x%2==0, Op(lambda x: x//2))],
Op(lambda x: x+1)
VIT

# default_none — no rule, no default → the value is a leaf (1 is white).
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/default_none.svg"
[4],
[Rule(lambda x: x%2==0, Op(lambda x: x//2))],
None
VIT

# bound_ghost — Rule.bound → pseudo-edge → dashed ghost stub at the ceiling.
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/bound_ghost.svg"
[1],
[Rule(lambda x: True, Op(lambda x: 2*x), bound=lambda x: 2*x<=8)],
None
VIT

# fan_in — two paths enter the same node (3 is reached from 1 via +2
# and from 9 via //3).
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/fan_in.svg"
[1, 9],
[Rule(lambda x: x%3==0, Op(lambda x: x//3))],
Op(lambda x: x+2)
VIT

# crop_forward / crop_backward — same graph, same anchor, two directions.
# Reused by both the tutorial ("how do I show only a slice?") and the
# manual ("direction + cycle").
visiter build > /tmp/visiter_crop.json <<'VIT'
range(1, 30),
[Rule(lambda x: x%3==0, Op(lambda x: x//3))],
Op(lambda x: x+2)
VIT
visiter to-dot 'anchor=1, radius=8, direction="forward"'  --input /tmp/visiter_crop.json | dot -Tsvg > "$OUT/crop_forward.svg"
visiter to-dot 'anchor=1, radius=8, direction="backward"' --input /tmp/visiter_crop.json | dot -Tsvg > "$OUT/crop_backward.svg"
rm -f /tmp/visiter_crop.json

# node_styles — one graph covering every vocabulary element AND showing
# wedge-grade 2, 3, and 4 with *mixed* highlight (so wedged pies appear
# both highlighted and not). Reused by tutorial and manual.
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/node_styles.svg"
[6, 12, 24],
[Rule(lambda x: x>1 and x%2==0, Op(lambda x: x//2, label="÷2")),
 Rule(lambda x: x>1 and x%3==0, Op(lambda x: x//3, label="÷3")),
 Rule(lambda x: x>1 and x%4==0, Op(lambda x: x//4, label="÷4")),
 Rule(lambda x: x>1 and x%6==0, Op(lambda x: x//6, label="÷6"))],
None,
tags={"highlight": lambda x: x in (4, 12)}
VIT

# strings — non-numeric values. Drop the trailing character while it is
# a vowel; words ending in a consonant are leaves.
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/strings.svg"
["banana", "garage", "queue"],
[Rule(lambda s: len(s) > 0 and s[-1] in set("aeiou"),
      Op(lambda s: s[:-1], label="drop-vowel"))],
None
VIT

# dashed_arrows — pseudo-edge (bound) and a cropped incoming boundary
# edge, rendered with the same dashed stub vocabulary.
visiter build > /tmp/visiter_dashed.json <<'VIT'
[1, 5],
[Rule(lambda x: True, Op(lambda x: 2*x, label="×2"), bound=lambda x: 2*x<=8)],
None
VIT
visiter to-dot 'anchor=2, radius=2, direction="both"' --input /tmp/visiter_dashed.json | dot -Tsvg > "$OUT/dashed_arrows.svg"
rm -f /tmp/visiter_dashed.json

# --- manual: iterate examples (§2) ---

# iterate_descent — descent example, rendered (forward ref to §3).
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/iterate_descent.svg"
range(1, 30),
[Rule(lambda x: x%3==0, Op(lambda x: x//3))],
Op(lambda x: x+2)
VIT

# iterate_reverse_binary — reverse binary tree with ceiling + max_depth.
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/iterate_reverse_binary.svg"
[1],
[Rule(lambda x: True, Op(lambda x: 2*x, label="×2"), bound=lambda x: 2*x<=64),
 Rule(lambda x: True, Op(lambda x: 2*x+1, label="×2+1"), bound=lambda x: 2*x+1<=64)],
None,
max_depth=5
VIT

# iterate_multiway — conjunctive rules with highlight on powers of two.
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/iterate_multiway.svg"
range(1, 30),
[Rule(lambda x: x%15==0, Op(lambda x: x//15, label="÷15")),
 Rule(lambda x: x%3==0 and x%15!=0, Op(lambda x: x//3, label="÷3")),
 Rule(lambda x: x%5==0 and x%15!=0, Op(lambda x: x//5, label="÷5"))],
Op(lambda x: x+1),
tags={"highlight": lambda x: x>0 and (x & (x-1))==0}
VIT

# --- manual: coloring model (§3) — one minimal SVG per bullet point ---

# coloring_palette — two ops ⇒ two palette slots.
visiter build > /tmp/visiter_cpal.json <<'VIT'
[1],
[Rule(lambda x: x%2==0, Op(lambda x: x//2, label="a"))],
Op(lambda x: x+1, label="b")
VIT
visiter to-dot '' --input /tmp/visiter_cpal.json | dot -Tsvg > "$OUT/coloring_palette.svg"
rm -f /tmp/visiter_cpal.json

# coloring_node_fill — leaf (white) / solid (one op) / wedged (two ops).
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/coloring_node_fill.svg"
[4],
[Rule(lambda x: x%2==0 and x>1, Op(lambda x: x//2, label="a")),
 Rule(lambda x: x%2==0 and x>1, Op(lambda x: x-2, label="b"))],
None
VIT

# coloring_highlight — same op, one node tagged → darkened fill.
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/coloring_highlight.svg"
[2, 3],
[Rule(lambda x: True, Op(lambda x: x+1, label="+1"), bound=lambda x: x+1<=4)],
None,
tags={"highlight": lambda x: x==2}
VIT

# coloring_roots — one root (bold border) next to one non-root.
visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/coloring_roots.svg"
[3],
[Rule(lambda x: x>0, Op(lambda x: x-1, label="-1"))],
None
VIT

# --- manual: to_dot examples (§3) ---

# example_show_factors — reverse binary tree with prime-factor annotations.
visiter build <<'VIT' | visiter to-dot 'show_factors=True' | dot -Tsvg > "$OUT/example_show_factors.svg"
[1],
[Rule(lambda x: True, Op(lambda x: 2*x, label="×2"), bound=lambda x: 2*x<=32),
 Rule(lambda x: True, Op(lambda x: 2*x+1, label="×2+1"), bound=lambda x: 2*x+1<=32)],
None,
max_depth=4
VIT

# example_pinned_colors — descent with explicit ids + op_colors pin.
visiter build <<'VIT' | visiter to-dot 'op_colors={"div3": ("#ccddff", "#6688bb"), "inc2": "#ffdddd"}' | dot -Tsvg > "$OUT/example_pinned_colors.svg"
[1, 5, 7],
[Rule(lambda x: x%3==0, Op(lambda x: x//3, label="÷3", id="div3"))],
Op(lambda x: x+2, label="+2", id="inc2")
VIT

# --- manual: recipe — depth-gradient coloring (§5) ---

python3 - > /tmp/visiter_gradient.dot <<'PY'
from visiter import iterate, Op, Rule, darken
import graphviz

graph = iterate(
    start=[1],
    rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, label="÷3"))],
    default=Op(lambda x: x + 2, label="+2"),
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

# --- manual: recipe — custom key_type with Fraction (§5) ---

visiter build <<'VIT' | visiter to-dot '' | dot -Tsvg > "$OUT/golden_ratio_convergents.svg"
[Fraction(1)],
[Rule(lambda x: True, Op(lambda x: 1 + 1/x, label="1 + 1/x"))],
None,
max_depth=7,
key_type="number"
VIT

# --- manual: §7 NetworkX — water jug example ---
# Two SVGs: full reachability graph (target states highlighted) and
# shortest-path subgraph (solution). Re-uses the demo helpers.

PYTHONPATH="../demos:${PYTHONPATH:-}" python3 - <<'PY' > /tmp/visiter_jugs.json
import json, sys
from water_jugs import make_rules, state_label
from visiter import iterate

graph = iterate([(0, 0)], make_rules(3, 5), None)

for key, info in graph["nodes"].items():
    state = tuple(int(x) for x in key.strip("()").split(", "))
    info["display"] = state_label(state, target=4)
    if state[0] == 4 or state[1] == 4:
        info.setdefault("tags", []).append("highlight")

for e in graph["edges"]:
    e["from"] = str(e["from"])
    e["to"] = str(e["to"])

json.dump(graph, sys.stdout, default=str)
PY

visiter to-dot 'node_label_attr="display"' \
  < /tmp/visiter_jugs.json | dot -Tsvg > "$OUT/water_jugs_full.svg"

python3 - /tmp/visiter_jugs.json <<'PY' \
  | visiter to-dot 'node_label_attr="display"' \
  | dot -Tsvg > "$OUT/water_jugs_path.svg"
import json, sys
import networkx as nx

graph = json.load(open(sys.argv[1]))
g = nx.DiGraph()
for key in graph["nodes"]:
    g.add_node(key)
for e in graph["edges"]:
    g.add_edge(str(e["from"]), str(e["to"]), op=e["op"])

source = "(0, 0)"
targets = [n for n in g.nodes
           if any(int(x) == 4 for x in n.strip("()").split(", "))]
best_len = None
all_paths = []
for t in targets:
    try:
        paths = list(nx.all_shortest_paths(g, source, t))
    except nx.NetworkXNoPath:
        continue
    plen = len(paths[0])
    if best_len is None or plen < best_len:
        best_len = plen
        all_paths = paths
    elif plen == best_len:
        all_paths.extend(paths)

path_nodes = set()
path_edges = set()
for path in all_paths:
    path_nodes.update(path)
    for i in range(len(path) - 1):
        path_edges.add((path[i], path[i + 1]))

sub = {
    "schema_version": "1",
    "roots": [source],
    "nodes": {},
    "edges": [],
    "pseudo_edges": [],
    "op_order": graph.get("op_order", []),
    "op_labels": graph.get("op_labels", {}),
}
for key in path_nodes:
    info = dict(graph["nodes"][key])
    sub["nodes"][key] = info
for src, dst in path_edges:
    sub["edges"].append({"from": src, "to": dst, "op": g.edges[src, dst]["op"]})

json.dump(sub, sys.stdout, default=str)
PY

rm -f /tmp/visiter_jugs.json

echo "Regenerated $(ls "$OUT"/*.svg | wc -l | tr -d ' ') SVGs in $OUT/"
