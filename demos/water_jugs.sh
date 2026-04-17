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

export PYTHONPATH="$HERE:${PYTHONPATH:-}"

# Step 1: Build the full reachability graph.
echo "[(0, 0)],
make_rules($CAP_A, $CAP_B),
None,
tags={'highlight': lambda s: s[0]==$TARGET or s[1]==$TARGET}" \
  | visiter build --import water_jugs:make_rules \
  > "$OUT/water_jugs.json"

NODES=$(python3 -c "import json; print(len(json.load(open('$OUT/water_jugs.json'))['nodes']))")

# Step 2: Render the full graph with HTML-table node labels.
visiter to-dot \
  --import water_jugs:make_node_label \
  "node_label=make_node_label($TARGET)" \
  < "$OUT/water_jugs.json" \
  | dot -Tsvg -o "$OUT/water_jugs.svg"
echo "wrote $OUT/water_jugs.svg (${CAP_A}L + ${CAP_B}L, target=${TARGET}L, $NODES nodes)"

# Step 3: Find shortest path(s) via NetworkX, render the subgraph.
visiter analyze \
  --import water_jugs:shortest_path_subgraph \
  "shortest_path_subgraph(graph, '(0, 0)', $TARGET)" \
  < "$OUT/water_jugs.json" \
  | visiter to-dot \
    --import water_jugs:make_node_label \
    "node_label=make_node_label($TARGET)" \
  | dot -Tsvg -o "$OUT/water_jugs_path.svg"
echo "wrote $OUT/water_jugs_path.svg"
