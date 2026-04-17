#!/usr/bin/env bash
# Structural simplification via NetworkX: `nx.condensation(graph)`
# computes the strongly-connected components (SCCs) — clusters of
# mutually reachable nodes — and collapses each SCC into a single
# node in a new, acyclic graph. The descent graph has two cycles
# (1 ↔ 3 and 2 → 4 → 6 → 2); condensation folds each cycle into one
# node, so the resulting graph shows macroscopic flow toward those
# attractor cycles without the cycle details.
#
# NetworkX labels each condensation node 0, 1, 2, … (opaque indices)
# and stashes the frozenset of each SCC's original members as the
# node attribute `members`. `visiter.analytics.from_networkx` passes
# that attribute through into the graph dict, and `to-dot`'s
# `node_label_attr` kwarg tells the renderer to display it instead
# of the node key — no custom post-processing needed.
#
# Two SVGs:
#   descent_full_forward.svg — the original orbit graph, cycles intact
#   descent_condensed.svg    — cycles collapsed into single nodes;
#                              each SCC-node labelled with its members
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

DATA="$OUT/descent.json"
EXPR="$(cat "$HERE/data/descent.expr")"

echo "$EXPR" | visiter build > "$DATA"

visiter to-dot 'direction="forward"' < "$DATA" \
  | dot -Tsvg -o "$OUT/descent_full_forward.svg"
echo "wrote $OUT/descent_full_forward.svg"

visiter analyze 'nx.condensation(graph)' < "$DATA" \
  | visiter to-dot 'node_label_attr="members"' \
  | dot -Tsvg -o "$OUT/descent_condensed.svg"
echo "wrote $OUT/descent_condensed.svg"
