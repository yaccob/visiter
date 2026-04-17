#!/usr/bin/env bash
# Reachability / routing question: from an arbitrary starting value,
# how many rule applications does it take to reach the cycle attractor
# at 1? NetworkX's shortest-path answers that in one call.
#
# Produces two artifacts:
#   shortest_paths.json  — a dict of {start: path-to-1-as-list}
#   descent_paths.svg    — the orbit graph, with every node on a shortest
#                          path to 1 highlighted (via a tag that to_dot
#                          darkens).
#
# The trick in the second step: we build once to get the orbit graph,
# use analyze to compute which nodes lie on a shortest path to 1, then
# enrich the JSON with a "highlight" tag on those nodes before handing
# it to to-dot. The enrichment is a tiny shell/python hop on stdin.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

DATA="$OUT/descent.json"
EXPR="$(cat "$HERE/data/descent.expr")"

echo "$EXPR" | visiter build > "$DATA"

# (a) emit raw shortest-path data as JSON
visiter analyze '
{start: nx.shortest_path(graph, source=start, target="1")
 for start in graph.nodes if nx.has_path(graph, start, "1")}
' < "$DATA" > "$OUT/shortest_paths.json"
echo "wrote $OUT/shortest_paths.json"

# (b) tag every node that lies on any shortest path to 1, then render.
python3 - "$DATA" "$OUT/shortest_paths.json" <<'PY' \
  | visiter to-dot 'anchor=1, radius=20, direction="backward"' \
  | dot -Tsvg -o "$OUT/descent_paths.svg"
import json, sys
graph_path, paths_path = sys.argv[1], sys.argv[2]
graph = json.load(open(graph_path))
paths = json.load(open(paths_path))
on_path = {node for path in paths.values() for node in path}
for key, info in graph["nodes"].items():
    if key in on_path:
        info.setdefault("tags", []).append("highlight")
json.dump(graph, sys.stdout)
PY
echo "wrote $OUT/descent_paths.svg"
