#!/usr/bin/env bash
# Structural simplification via NetworkX: `nx.condensation(graph)`
# collapses every strongly connected component into a single node,
# producing a directed *acyclic* graph that shows the macro-structure
# of the iteration. Because `analyze` detects that the expression
# returned a NetworkX graph, it re-emits it as a VisIter-schema JSON,
# and the pipeline continues straight into `to-dot` / `dot`.
#
# Two SVGs side by side:
#   descent_full.svg       — the original orbit graph, with all cycles
#   descent_condensed.svg  — the DAG of components, one node per cycle
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

DATA="$OUT/descent.json"
EXPR="$(cat "$HERE/data/descent.expr")"

visiter iterate "$EXPR" > "$DATA"

# Original graph.
visiter to-dot 'anchor=1, radius=10, direction="backward"' \
  < "$DATA" | dot -Tsvg -o "$OUT/descent_full.svg"
echo "wrote $OUT/descent_full.svg"

# Same data, but condensed first. Each condensed node is labelled by
# the frozenset of members NetworkX assigns; render without tricks.
visiter analyze 'nx.condensation(graph)' < "$DATA" \
  | visiter to-dot '' \
  | dot -Tsvg -o "$OUT/descent_condensed.svg"
echo "wrote $OUT/descent_condensed.svg"
