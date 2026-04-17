#!/usr/bin/env bash
# Per-node fill is driven by the set of OUTGOING op labels, not by
# the node's identity:
#   0 outgoing ops  → no fill (leaf, default white)
#   1 outgoing op   → solid fill in that op's color
#   ≥2 outgoing ops → wedged-pie fill, one slice per op label
#
# This iteration uses three rules that can fire for the same value
# (multiples of 30 match all three), plus a default. Many nodes have
# 2–4 outgoing edges with distinct op labels — those nodes show up in
# the SVG with multi-colored pie-slice fills.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

EXPR='
start=range(1, 50),
rules=[
    Rule(lambda x: x % 2 == 0, Op(lambda x: x // 2, label="÷2")),
    Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, label="÷3")),
    Rule(lambda x: x % 5 == 0, Op(lambda x: x // 5, label="÷5")),
],
default=Op(lambda x: x + 1, label="+1"),
max_depth=4'

visiter build "$EXPR" \
  | visiter to-dot 'anchor=1, radius=10, direction="backward"' \
  | dot -Tsvg -o "$OUT/wedged_fills.svg"
echo "wrote $OUT/wedged_fills.svg"
echo "  → look at e.g. node 30: divisible by 2, 3 AND 5 → three"
echo "    outgoing edges (÷2, ÷3, ÷5) → three-slice wedged fill."
