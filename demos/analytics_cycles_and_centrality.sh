#!/usr/bin/env bash
# Pure *inspection*: use `visiter analyze` to ask NetworkX questions
# about a VisIter graph. No rendering here — the point is that once
# you have the JSON data, NetworkX's whole toolbox is one pipe away.
#
#   (a) How many nodes / edges?
#   (b) Which cycles exist?  (shows the 1 ↔ 3 cycle and the 2→4→6→2 cycle)
#   (c) Which nodes are most "central" by in-degree centrality —
#       i.e. which values get reached the most often from others?
#
# All three questions use the same input data; no custom Python code,
# just stock NetworkX calls inside the eval'd argument.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

DATA="$OUT/descent.json"
EXPR="$(cat "$HERE/data/descent.expr")"

echo "$EXPR" | visiter build > "$DATA"

visiter to-dot '' < "$DATA" | dot -Tsvg -o "$OUT/descent.svg"
echo "wrote $OUT/descent.svg"

echo "=== node and edge counts ==="
visiter analyze '{"nodes": nx.number_of_nodes(graph), "edges": nx.number_of_edges(graph)}' \
  < "$DATA"

echo
echo "=== simple cycles ==="
visiter analyze 'list(nx.simple_cycles(graph))' < "$DATA"

echo
echo "=== top 5 by in-degree centrality ==="
visiter analyze '
sorted(nx.in_degree_centrality(graph).items(), key=lambda kv: -kv[1])[:5]
' < "$DATA"

echo
echo "wrote $DATA"
