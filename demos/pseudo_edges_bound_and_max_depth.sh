#!/usr/bin/env bash
# Pseudo-edges have two distinct sources, both rendered as the same
# dashed ghost stub:
#   (a) `Rule.bound` returned False — "the op IS applicable, but we
#       chose to stop here" (a structural decision baked into the
#       rule).
#   (b) `max_depth` was reached — "BFS topology says: don't expand
#       further from depth N onward" (a graph-shape decision made at
#       call time).
#
# This demo runs the SAME iteration (a doubling-and-tripling cascade)
# twice — once with bound, once with max_depth — to make plain that
# the visual vocabulary is identical even though the semantic source
# differs.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

# Two starts (1 and 5) with two rules (×2, ×3). Because 5 is coprime
# with 2 and 3, the two subtrees stay disjoint and grow uniformly —
# the ghost-stub mechanic is the only thing competing for the
# reader's attention.

# (a) Rule.bound: doubling stops when 2x would exceed 16; tripling at 18.
visiter build '
start=[1, 5],
rules=[
    Rule(lambda x: True, Op(lambda x: 2*x, label="×2"),
         bound=lambda x: 2*x <= 16),
    Rule(lambda x: True, Op(lambda x: 3*x, label="×3"),
         bound=lambda x: 3*x <= 18),
],
default=None' \
  | visiter to-dot '' \
  | dot -Tsvg -o "$OUT/pseudo_via_bound.svg"
echo "wrote $OUT/pseudo_via_bound.svg (ghost stubs from Rule.bound)"

# (b) max_depth: same rules, no bounds; expansion stops at depth 2.
#     Every node at depth 2 has both rules ready to fire — both become
#     pseudo-edges, rendered identically to the bound case above.
visiter build '
start=[1, 5],
rules=[
    Rule(lambda x: True, Op(lambda x: 2*x, label="×2")),
    Rule(lambda x: True, Op(lambda x: 3*x, label="×3")),
],
default=None,
max_depth=2' \
  | visiter to-dot '' \
  | dot -Tsvg -o "$OUT/pseudo_via_max_depth.svg"
echo "wrote $OUT/pseudo_via_max_depth.svg (ghost stubs from max_depth=2)"
