#!/usr/bin/env bash
# Water jug problem: two jugs with capacities A and B (default 3 and
# 5). Six actions: fill, empty, pour A→B, pour B→A. Start: both
# empty. The graph has non-trivial cycles because the actions are
# not self-inverse (fill ≠ empty, pour ≠ unpour).
#
# Classic puzzle: "How do you measure exactly 4L with a 3L and 5L
# jug?" — the shortest path from (0,0) to any node containing 4
# is the answer. Nodes where either jug holds the target are
# highlighted.
#
# Usage:
#   bash demos/water_jugs.sh             # default: 3L + 5L, target 4
#   bash demos/water_jugs.sh 3 5 4       # same, explicit
#   bash demos/water_jugs.sh 4 7 5       # 4L + 7L jugs, measure 5
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

CAP_A=${1:-3}
CAP_B=${2:-5}
TARGET=${3:-4}

PYTHON="$(head -1 "$(command -v visiter)" | sed 's/^#! *//')"

PYTHONPATH="$HERE:${PYTHONPATH:-}" "$PYTHON" - "$CAP_A" "$CAP_B" "$TARGET" <<'PY' > "$OUT/water_jugs.json"
import json, sys
from water_jugs import make_rules, state_label
from visiter import iterate

cap_a, cap_b, target = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])

graph = iterate(
    [(0, 0)],
    make_rules(cap_a, cap_b),
    None,
    tags={"highlight": lambda s: s[0] == target or s[1] == target},
)

for key, info in graph["nodes"].items():
    state = tuple(int(x) for x in key.strip("()").split(", "))
    info["display"] = state_label(state)

# Normalize edge endpoints (tuples → str) for JSON round-trip.
for e in graph["edges"]:
    e["from"] = str(e["from"])
    e["to"] = str(e["to"])

json.dump(graph, sys.stdout, default=str)
PY

NODES=$(python3 -c "import json; print(len(json.load(open('$OUT/water_jugs.json'))['nodes']))")
visiter to-dot 'node_label_attr="display"' < "$OUT/water_jugs.json" \
  | dot -Tsvg -o "$OUT/water_jugs.svg"
echo "wrote $OUT/water_jugs.svg (${CAP_A}L + ${CAP_B}L jugs, target=${TARGET}L, $NODES nodes)"
