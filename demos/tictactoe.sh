#!/usr/bin/env bash
# Tic-Tac-Toe: game tree from the empty board, with symmetry
# reduction (8 rigid symmetries of the square). Every rotationally
# equivalent position is merged into a single node, so the graph
# shows the true strategic structure without visual noise.
#
# Highlighted nodes are terminal positions where someone has won.
# Edge labels use the a1–c3 coordinate system (column a–c, row 1–3).
#
# The helper module tictactoe.py lives next to this script and
# provides the game logic (canonical form, win detection, move
# generation).
#
# max_depth controls how many half-moves deep the tree goes.
# Default is 9 (full game — 765 nodes with symmetry reduction).
# Pass a smaller number for a compact preview:
#   bash demos/tictactoe.sh 3
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

DEPTH=${1:-9}

PYTHON="$(head -1 "$(command -v visiter)" | sed 's/^#! *//')"

PYTHONPATH="$HERE:${PYTHONPATH:-}" "$PYTHON" - "$DEPTH" \
  2>"$OUT/.tictactoe_nodes" <<'PY' \
  | dot -Tsvg -o "$OUT/tictactoe.svg"
import sys
from tictactoe import empty_board, make_rules, has_winner, board_label
from visiter import iterate, to_dot

depth = int(sys.argv[1])

graph = iterate(
    [empty_board()],
    make_rules(),
    None,
    max_depth=depth,
    tags={"highlight": has_winner},
)

print(len(graph["nodes"]), file=sys.stderr)
dot = to_dot(graph, node_label=lambda k, i: board_label(k))
sys.stdout.write(dot.source)
PY

NODES=$(cat "$OUT/.tictactoe_nodes")
rm -f "$OUT/.tictactoe_nodes"
echo "wrote $OUT/tictactoe.svg (depth=$DEPTH, $NODES nodes)"
