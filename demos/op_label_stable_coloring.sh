#!/usr/bin/env bash
# Op labels are the identity for color assignment: two renders of the
# same op label get the same color, so a graph stays visually
# coherent as you evolve it across runs.
#
# Three SVGs:
#   (a) baseline — two rules + default (÷3, +2).
#   (b) rule appended at the end — adds a third rule (÷5). The
#       pre-existing op colors stay where they were, ÷5 takes the
#       next palette slot.
#   (c) rule inserted in the middle, plus op_colors override — when
#       a rule lands BEFORE existing ones, the auto-assigned palette
#       indices shift; pin colors with op_colors to keep the legend
#       stable across edits.
set -euo pipefail
HERE="$(dirname "$0")"
OUT="$HERE/out"
mkdir -p "$OUT"

# (a) Baseline: ÷3 + +2 default.
visiter iterate '
range(1, 30),
[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
default=Op(lambda x: x + 2, "+2")' \
  | visiter to-dot 'anchor=1, radius=10, direction="backward"' \
  | dot -Tsvg -o "$OUT/stable_a_baseline.svg"
echo "wrote $OUT/stable_a_baseline.svg     (÷3=blue, +2=orange)"

# (b) Append a third rule: ÷5 for multiples of 5.
visiter iterate '
range(1, 30),
[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3")),
 Rule(lambda x: x % 5 == 0, Op(lambda x: x // 5, "÷5"))],
default=Op(lambda x: x + 2, "+2")' \
  | visiter to-dot 'anchor=1, radius=10, direction="backward"' \
  | dot -Tsvg -o "$OUT/stable_b_appended.svg"
echo "wrote $OUT/stable_b_appended.svg     (÷3 still blue, ÷5 next slot, +2 last)"

# (c) Insert ÷5 BEFORE ÷3, with op_colors pinning to keep the
#     pre-existing colors in place. Without the pin, ÷3 would shift
#     palette slots; with it, the visual identity holds.
visiter iterate '
range(1, 30),
[Rule(lambda x: x % 5 == 0, Op(lambda x: x // 5, "÷5")),
 Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
default=Op(lambda x: x + 2, "+2")' \
  | visiter to-dot 'op_colors={
      "÷3": ("#ccddff", "#6688bb"),
      "+2": ("#ffddcc", "#ddbb99"),
      "÷5": ("#cceecc", "#77aa77"),
    }, anchor=1, radius=10, direction="backward"' \
  | dot -Tsvg -o "$OUT/stable_c_inserted_with_pin.svg"
echo "wrote $OUT/stable_c_inserted_with_pin.svg (colors pinned via op_colors)"
