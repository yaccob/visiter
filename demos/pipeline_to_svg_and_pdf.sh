#!/usr/bin/env bash
# Full pipe composition: build a graph, render to DOT, hand to `dot` for
# layout + format conversion. Two output formats demonstrate that the
# downstream stage is just a Graphviz invocation.
#
# Side effects worth noticing in the rendered SVG:
#   - Every interior node (e.g. 2, 3, 4, ...) has TWO outgoing edges
#     with different op labels (×2 and ×2+1) → it gets a wedged-pie
#     fill split between the two ops' colors. Showcased explicitly
#     in wedged_multi_op_fills.sh.
#   - The boundary leaves (where 2x or 2x+1 would exceed the ceiling)
#     carry dashed *ghost stubs* — visual marker that `Rule.bound`
#     suppressed expansion. The same vocabulary is reused for
#     `max_depth` cutoffs and render-time crops; see
#     pseudo_edges_bound_and_max_depth.sh.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

# Reverse binary tree: from 1, doubling and double-plus-one until 64.
EXPR='start=[1], rules=[
    Rule(lambda x: True, Op(lambda x: 2*x, "×2"),
         bound=lambda x: 2*x <= 64),
    Rule(lambda x: True, Op(lambda x: 2*x+1, "×2+1"),
         bound=lambda x: 2*x+1 <= 64),
], default=None'

visiter build "$EXPR" \
  | visiter to-dot 'show_binary=True' \
  | tee "$OUT/binary_tree.dot" \
  | dot -Tsvg -o "$OUT/binary_tree.svg"
echo "wrote $OUT/binary_tree.svg"

# Same data, PDF instead of SVG.
dot -Tpdf "$OUT/binary_tree.dot" -o "$OUT/binary_tree.pdf"
echo "wrote $OUT/binary_tree.pdf"
