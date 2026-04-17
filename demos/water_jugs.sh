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
#   water_jugs.svg       — full reachability graph (target states
#                          highlighted via iterate's tags=)
#   water_jugs_path.svg  — only the shortest path(s) to a target
#                          (found via visiter analyze + NetworkX)
#
# Visual channels:
#   - Bold cell value: this jug holds the target (via node_label)
#   - Darkened fill (highlight): target state in full graph;
#     goal node in path graph
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

# Step 1: Build the full reachability graph. Target states are
# highlighted directly via iterate's tags= — no post-processing.
PYTHONPATH="$HERE:${PYTHONPATH:-}" "$PYTHON" - "$CAP_A" "$CAP_B" "$TARGET" <<'PY' > "$OUT/water_jugs.json"
import json, sys
from water_jugs import make_rules
from visiter import iterate

cap_a, cap_b, target = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])

graph = iterate(
    [(0, 0)],
    make_rules(cap_a, cap_b),
    None,
    tags={"highlight": lambda s: s[0] == target or s[1] == target},
)

json.dump(graph, sys.stdout, default=str)
PY

NODES=$(python3 -c "import json; print(len(json.load(open('$OUT/water_jugs.json'))['nodes']))")

# Step 2: Render the full graph. node_label callback formats state
# tuples as HTML tables with bold target values — no need to
# pre-populate a "display" attribute in the graph dict.
PYTHONPATH="$HERE:${PYTHONPATH:-}" "$PYTHON" -c "
import sys, json
from water_jugs import state_label
target = int(sys.argv[1])
graph = json.load(sys.stdin)
# Provide the node_label callable as a to_dot kwarg via the CLI
# eval namespace — it receives (key, info) and returns an HTML label.
from visiter import to_dot
dot = to_dot(graph, node_label=lambda k, i: state_label(
    tuple(int(x) for x in k.strip('()').split(', ')), target=target))
sys.stdout.write(dot.source)
" "$TARGET" < "$OUT/water_jugs.json" \
  | dot -Tsvg -o "$OUT/water_jugs.svg"
echo "wrote $OUT/water_jugs.svg (${CAP_A}L + ${CAP_B}L, target=${TARGET}L, $NODES nodes)"

# Step 3: Find ALL shortest paths to any target state via NetworkX,
# build a subgraph, and render as a separate "solution" SVG.
visiter analyze '
[p for t in [n for n in graph.nodes
             if any(int(x) == '$TARGET'
                    for x in n.strip("()").split(", "))]
 for p in nx.all_shortest_paths(graph, source="(0, 0)", target=t)]
' < "$OUT/water_jugs.json" > "$OUT/water_jugs_paths.json"

PYTHONPATH="$HERE:${PYTHONPATH:-}" "$PYTHON" - "$OUT/water_jugs.json" "$OUT/water_jugs_paths.json" "$TARGET" <<'PY' \
  | dot -Tsvg -o "$OUT/water_jugs_path.svg"
import json, sys
from water_jugs import state_label
from visiter import to_dot

graph = json.load(open(sys.argv[1]))
all_paths = json.load(open(sys.argv[2]))
target = int(sys.argv[3])

# Keep only the globally shortest paths.
if all_paths:
    min_len = min(len(p) for p in all_paths)
    all_paths = [p for p in all_paths if len(p) == min_len]

path_nodes = set()
path_edges = set()
for path in all_paths:
    path_nodes.update(path)
    for i in range(len(path) - 1):
        path_edges.add((path[i], path[i + 1]))

# Build a subgraph from the union of all shortest paths.
targets = set(p[-1] for p in all_paths)
sub = {
    "schema_version": "1",
    "roots": graph["roots"],
    "nodes": {k: dict(graph["nodes"][k]) for k in path_nodes},
    "edges": [],
    "pseudo_edges": [],
    "op_order": graph.get("op_order", []),
    "op_labels": graph.get("op_labels", {}),
}

# Highlight only the goal node(s) in the path subgraph.
for key in targets & path_nodes:
    sub["nodes"][key].setdefault("tags", []).append("highlight")

# Collect edges from the original graph that connect path nodes.
for e in graph["edges"]:
    if (str(e["from"]), str(e["to"])) in path_edges:
        sub["edges"].append(e)

dot = to_dot(sub, node_label=lambda k, i: state_label(
    tuple(int(x) for x in k.strip("()").split(", ")), target=target))
sys.stdout.write(dot.source)
PY

PATH_NODES=$(python3 -c "
import re
svg = open('$OUT/water_jugs_path.svg').read()
print(len(re.findall(r'class=\"node\"', svg)))
")
echo "wrote $OUT/water_jugs_path.svg (shortest path: $PATH_NODES nodes = $((PATH_NODES - 1)) steps)"
