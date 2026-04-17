#!/usr/bin/env bash
# Iteration on `fractions.Fraction` values, classified as "number" via
# build's `key_type=` override. Runs as a pure CLI pipeline: the
# `visiter build` subcommand binds `Fraction` and `Decimal` into its
# eval namespace by default, so no --import or Python heredoc is
# needed for stdlib numeric types.
#
# The iteration is the continued-fraction recurrence for the golden
# ratio:  x ↦ 1 + 1/x, starting at 1. With exact rational arithmetic
# the trajectory is 1, 2, 3/2, 5/3, 8/5, 13/8, 21/13, 34/21, … —
# Fibonacci-ratio convergents to φ.
#
# Why this demo needs key_type:
#   json_type(Fraction(1, 2)) falls back to "string" because Fraction
#   isn't one of the JSON-native Python types. The data *is* numeric,
#   so we override with key_type="number" so downstream consumers
#   (other tools, schema validators, this project's own renderer
#   heuristics) see the values for what they are.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

EXPR='
start=[Fraction(1)],
rules=[Rule(lambda x: True, Op(lambda x: 1 + 1/x, label="1 + 1/x"))],
default=None,
max_depth=7,
key_type="number"'

echo "$EXPR" | visiter build > "$OUT/golden_ratio_convergents.json"

visiter to-dot '' \
  < "$OUT/golden_ratio_convergents.json" \
  | dot -Tsvg -o "$OUT/golden_ratio_convergents.svg"
echo "wrote $OUT/golden_ratio_convergents.svg"

# Evidence that the override took effect: every node declares
# key_type="number", not the default "string" fallback for Fraction.
types=$(python3 -c '
import json, sys
g = json.load(open(sys.argv[1]))
print(sorted({info["key_type"] for info in g["nodes"].values()}))
' "$OUT/golden_ratio_convergents.json")
echo "node key_types present: $types"
