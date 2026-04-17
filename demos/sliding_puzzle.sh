#!/usr/bin/env bash
# Sliding puzzle (generalized 15-puzzle): tiles on a W×H grid,
# one gap, slide a neighbour into the gap. Every move is reversible,
# so the graph has cycles everywhere — the main point of this demo.
#
# Usage:
#   bash demos/sliding_puzzle.sh           # default 2×2 (12 reachable states)
#   bash demos/sliding_puzzle.sh 3 2       # 3 wide, 2 tall (360 states)
#   bash demos/sliding_puzzle.sh 2 3       # 2 wide, 3 tall (360 states)
#   bash demos/sliding_puzzle.sh 3 3       # 3×3 = 8-puzzle (181440 states — large!)
#
# The start state is the goal (1,2,…,N-1,gap); iterate explores
# every reachable state from there. The goal node is highlighted.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

W=${1:-2}
H=${2:-2}

PYTHON="$(head -1 "$(command -v visiter)" | sed 's/^#! *//')"

PYTHONPATH="$HERE:${PYTHONPATH:-}" "$PYTHON" - "$W" "$H" <<'PY' > "$OUT/sliding_puzzle.json"
import json, sys
from sliding_puzzle import goal_board, make_rules, board_label
from visiter import iterate

W, H = int(sys.argv[1]), int(sys.argv[2])
start = goal_board(W, H)

graph = iterate(
    [start],
    make_rules(W, H),
    None,
    tags={"highlight": lambda b: b == start},
)

for key, info in graph["nodes"].items():
    # Recover the tuple from the string key for display formatting.
    board = tuple(int(x) for x in key.strip("()").split(", "))
    info["display"] = board_label(board, W)

# Normalize edge endpoints: iterate stores raw tuples in from/to,
# but json.dump serialises tuples as JSON arrays ([1,2,3,0]) which
# don't match the node keys (str(tuple) = "(1, 2, 3, 0)").
for e in graph["edges"]:
    e["from"] = str(e["from"])
    e["to"] = str(e["to"])
for pe in graph.get("pseudo_edges", []):
    pe["from"] = str(pe["from"])

json.dump(graph, sys.stdout, default=str)
PY

NODES=$(python3 -c "import json; print(len(json.load(open('$OUT/sliding_puzzle.json'))['nodes']))")
visiter to-dot 'node_label_attr="display"' < "$OUT/sliding_puzzle.json" \
  | dot -Tsvg -o "$OUT/sliding_puzzle.svg"
echo "wrote $OUT/sliding_puzzle.svg (${W}x${H}, $NODES nodes)"
