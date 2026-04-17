#!/usr/bin/env bash
# Water jug problem: two jugs with capacities A and B (default 3 and
# 5). Six actions: fill, empty, pour A→B, pour B→A. Start: both
# empty. The graph has non-trivial cycles because the actions are
# not self-inverse (fill ≠ empty, pour ≠ unpour).
#
# Classic puzzle: "How do you measure exactly 4L with a 3L and 5L
# jug?" — the answer is the shortest path from (0,0) to any node
# where either jug holds the target amount.
#
# Produces two SVGs:
#   water_jugs.svg       — full reachability graph (structure + cycles)
#   water_jugs_path.svg  — only the shortest path(s) to a target state
#
# Two visual channels in the path SVG:
#   - Bold cell value: this jug holds the target (label-level marker)
#   - Darkened fill (highlight): target state reached
#
# Usage:
#   bash demos/water_jugs.sh             # default: 3L + 5L, target 4
#   bash demos/water_jugs.sh 3 5 4       # same, explicit
#   bash demos/water_jugs.sh 4 7 5       # 4L + 7L jugs, measure 5
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

CAP_A=${1:-3}
CAP_B=${2:-5}
TARGET=${3:-4}

PYTHON="$(head -1 "$(command -v visiter)" | sed 's/^#! *//')"

# Step 1: Build the full reachability graph.
PYTHONPATH="$HERE:${PYTHONPATH:-}" "$PYTHON" - "$CAP_A" "$CAP_B" "$TARGET" <<'PY' > "$OUT/water_jugs.json"
import json, sys
from water_jugs import make_rules, state_label
from visiter import iterate

cap_a, cap_b, target = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])

graph = iterate(
    [(0, 0)],
    make_rules(cap_a, cap_b),
    None,
)

for key, info in graph["nodes"].items():
    state = tuple(int(x) for x in key.strip("()").split(", "))
    info["display"] = state_label(state, target=target)

# Normalize edge endpoints (tuples → str) for JSON round-trip.
for e in graph["edges"]:
    e["from"] = str(e["from"])
    e["to"] = str(e["to"])

json.dump(graph, sys.stdout, default=str)
PY

NODES=$(python3 -c "import json; print(len(json.load(open('$OUT/water_jugs.json'))['nodes']))")

# Step 2: Highlight target states in the full graph, then render.
python3 -c '
import json, sys
target = int(sys.argv[2])
graph = json.load(open(sys.argv[1]))
for key, info in graph["nodes"].items():
    state = tuple(int(x) for x in key.strip("()").split(", "))
    if state[0] == target or state[1] == target:
        info.setdefault("tags", []).append("highlight")
json.dump(graph, sys.stdout)
' "$OUT/water_jugs.json" "$TARGET" \
  | visiter to-dot 'node_label_attr="display"' \
  | dot -Tsvg -o "$OUT/water_jugs.svg"
echo "wrote $OUT/water_jugs.svg (${CAP_A}L + ${CAP_B}L, target=${TARGET}L, $NODES nodes)"

# Step 3: Find ALL shortest paths to any target state via NetworkX,
# build a subgraph containing only those nodes and edges, highlight
# the target nodes, and render as a separate "solution" SVG.
python3 - "$OUT/water_jugs.json" "$TARGET" <<'PY' \
  | visiter to-dot 'node_label_attr="display"' \
  | dot -Tsvg -o "$OUT/water_jugs_path.svg"
import json, sys
import networkx as nx

graph = json.load(open(sys.argv[1]))
target = int(sys.argv[2])

# Rebuild the NX digraph from the JSON.
g = nx.DiGraph()
for key in graph["nodes"]:
    g.add_node(key)
for e in graph["edges"]:
    g.add_edge(str(e["from"]), str(e["to"]), op=e["op"])

source = "(0, 0)"
target_nodes = [n for n in g.nodes
                if any(int(x) == target
                       for x in n.strip("()").split(", "))]

# Collect all shortest paths to the nearest target(s).
best_len = None
all_paths = []
for t in target_nodes:
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

# Build a subgraph from the union of all shortest paths.
path_nodes = set()
path_edges = set()
for path in all_paths:
    for node in path:
        path_nodes.add(node)
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
    # Highlight target nodes (the endpoints of the path).
    if key in set(target_nodes) & path_nodes:
        info.setdefault("tags", []).append("highlight")
    sub["nodes"][key] = info

for src, dst in path_edges:
    # Find the edge op from the original graph.
    edge_data = g.edges[src, dst]
    sub["edges"].append({"from": src, "to": dst, "op": edge_data["op"]})

json.dump(sub, sys.stdout, default=str)
PY

PATH_INFO=$(python3 -c "
import json
paths = []  # we don't have the paths file anymore, read from SVG node count
sub = json.load(open('$OUT/water_jugs.json'))
# Just report the step count from the path SVG
import subprocess, os
")
PATH_NODES=$(python3 -c "
import json
# Count nodes in path subgraph by parsing the path SVG
import re
svg = open('$OUT/water_jugs_path.svg').read()
print(len(re.findall(r'class=\"node\"', svg)))
")
echo "wrote $OUT/water_jugs_path.svg (shortest path: $PATH_NODES nodes = $((PATH_NODES - 1)) steps)"
