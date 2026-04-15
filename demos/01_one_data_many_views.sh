#!/usr/bin/env bash
# Generate one iteration graph, then render it three different ways:
#   (a) full backward neighborhood of the cycle attractor at 1
#   (b) a tight 2-hop crop around 1 (shows the ghost-stub mechanism)
#   (c) full graph with custom op_colors
# All three views share the same input data (descent.json), proving
# that iterate and to_dot are decoupled by the documented graph dict.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out

DATA="out/descent.json"
EXPR="$(cat data/descent.expr)"

visiter iterate "$EXPR" > "$DATA"
echo "wrote $DATA"

visiter to-dot 'anchor=1, radius=10, direction="backward"' \
  < "$DATA" > out/descent_full.dot
dot -Tsvg out/descent_full.dot -o out/descent_full.svg
echo "wrote out/descent_full.svg"

visiter to-dot 'anchor=1, radius=2, direction="backward"' \
  < "$DATA" > out/descent_tight.dot
dot -Tsvg out/descent_tight.dot -o out/descent_tight.svg
echo "wrote out/descent_tight.svg (tight crop — note the ghost stubs)"

visiter to-dot 'op_colors={"÷3": "#a83232", "+2": "#3266a8"}' \
  < "$DATA" > out/descent_recolored.dot
dot -Tsvg out/descent_recolored.dot -o out/descent_recolored.svg
echo "wrote out/descent_recolored.svg (custom palette)"
