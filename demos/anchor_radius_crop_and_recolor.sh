#!/usr/bin/env bash
# Generate one iteration graph, then render it three different ways:
#   (a) full backward neighborhood of the cycle attractor at 1
#   (b) a tight 2-hop crop around 1 (shows the ghost-stub mechanism)
#   (c) full graph with custom op_colors
# All three views share the same input data (descent.json), proving
# that iterate and to_dot are decoupled by the documented graph dict.
#
# Paths printed below are relative to the caller's cwd when the script
# itself was invoked relatively, so the output is copy-pasteable.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

DATA="$OUT/descent.json"
EXPR="$(cat "$HERE/data/descent.expr")"

echo "$EXPR" | visiter build > "$DATA"
echo "wrote $DATA"

visiter to-dot 'anchor=1, radius=10, direction="backward"' \
  < "$DATA" > "$OUT/descent_full.dot"
dot -Tsvg "$OUT/descent_full.dot" -o "$OUT/descent_full.svg"
echo "wrote $OUT/descent_full.svg"

visiter to-dot 'anchor=1, radius=2, direction="backward"' \
  < "$DATA" > "$OUT/descent_tight.dot"
dot -Tsvg "$OUT/descent_tight.dot" -o "$OUT/descent_tight.svg"
echo "wrote $OUT/descent_tight.svg (tight crop — note the ghost stubs)"

visiter to-dot 'op_colors={"x // 3": "#a83232", "x + 2": "#3266a8"}' \
  < "$DATA" > "$OUT/descent_recolored.dot"
dot -Tsvg "$OUT/descent_recolored.dot" -o "$OUT/descent_recolored.svg"
echo "wrote $OUT/descent_recolored.svg (custom palette)"
